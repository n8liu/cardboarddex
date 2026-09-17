"""Integration check for broker durability and isolation from cache eviction."""
import os
import subprocess
import time
import uuid
import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RUN_CONTAINER_TESTS') != '1', reason='requires disposable Docker containers')


def test_restart_preserves_queue_quotas_and_checkpoint_while_cache_evicts():
    suffix = uuid.uuid4().hex[:10]
    durable, cache, volume = ('gc-durable-' + suffix, 'gc-cache-' + suffix, 'gc-redis-' + suffix)
    image = os.environ.get('TEST_REDIS_IMAGE', 'redis:7-alpine')
    def run(*args, **kwargs):
        return subprocess.run(args, check=True, capture_output=True, **kwargs)
    def redis(name, *args):
        return run('docker', 'exec', name, 'redis-cli', '--raw', *args).stdout.decode().strip()
    def wait(name):
        for _ in range(30):
            if subprocess.run(['docker','exec',name,'redis-cli','ping'],capture_output=True).stdout.strip() == b'PONG':
                return
            time.sleep(1)
        raise AssertionError('Redis did not become ready')
    try:
        run('docker','volume','create',volume)
        run('docker','run','-d','--name',durable,'--network','none','-v',volume+':/data',image,
            'redis-server','--appendonly','yes','--appendfsync','always','--maxmemory','8mb','--maxmemory-policy','noeviction','--save','')
        run('docker','run','-d','--name',cache,'--network','none',image,'redis-server','--maxmemory','2mb','--maxmemory-policy','allkeys-lru','--save','')
        wait(durable);wait(cache)
        redis(durable,'SET','quota','37','EX','3600')
        redis(durable,'SET','checkpoint','set-123','EX','3600')
        redis(durable,'LPUSH','celery','pending-job')
        payload=[]
        for i in range(500):
            key=f'cache-{i}'.encode(); value=b'x'*8192
            payload.append(b'*3\r\n$3\r\nSET\r\n$'+str(len(key)).encode()+b'\r\n'+key+b'\r\n$8192\r\n'+value+b'\r\n')
        run('docker','exec','-i',cache,'redis-cli','--pipe',input=b''.join(payload))
        stats=redis(cache,'INFO','stats')
        evicted=next(int(line.split(':')[1]) for line in stats.splitlines() if line.startswith('evicted_keys:'))
        assert evicted > 0
        run('docker','restart',durable)
        wait(durable)
        assert redis(durable,'GET','quota') == '37'
        assert redis(durable,'GET','checkpoint') == 'set-123'
        assert redis(durable,'RPOP','celery') == 'pending-job'
        assert int(redis(durable,'TTL','quota')) > 0
    finally:
        subprocess.run(['docker','rm','-f','-v',durable,cache],capture_output=True)
        subprocess.run(['docker','volume','rm',volume],capture_output=True)
