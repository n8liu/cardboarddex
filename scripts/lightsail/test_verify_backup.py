import importlib.util
import os
from pathlib import Path
import subprocess
import uuid

import pytest

spec = importlib.util.spec_from_file_location('verify_backup', Path(__file__).with_name('verify_backup.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


@pytest.mark.skipif(os.environ.get('RUN_CONTAINER_TESTS') != '1', reason='requires disposable Docker containers')
def test_redis_restore_loads_rdb_and_rejects_corruption(tmp_path):
    name = 'cardboarddex-rdb-test-' + uuid.uuid4().hex[:10]
    image = 'redis:7-alpine'
    try:
        subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none', image], check=True)
        import time
        for _ in range(40):
            p = subprocess.run(['docker', 'exec', name, 'redis-cli', 'ping'], capture_output=True, text=True)
            if p.returncode == 0 and p.stdout.strip() == 'PONG':
                break
            time.sleep(0.25)
        else:
            pytest.fail('Disposable Redis not ready')
        subprocess.run(['docker', 'exec', name, 'redis-cli', 'set', 'restore-test', 'value'], check=True)
        subprocess.run(['docker', 'exec', name, 'redis-cli', 'save'], check=True)
        archive = tmp_path / 'redis.rdb'
        subprocess.run(['docker', 'cp', name + ':/data/dump.rdb', str(archive)], check=True)
        backup.restore_redis(archive, image)
        archive.write_bytes(b'corrupt RDB')
        with pytest.raises(RuntimeError):
            backup.restore_redis(archive, image)
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', name], check=True)
