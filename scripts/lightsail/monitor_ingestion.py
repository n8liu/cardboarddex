#!/usr/bin/env python3
"""Root systemd monitor: persist evidence and pause ingestion on instability."""
import json
import logging
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/var/lib/cardboarddex/ingestion-monitor')
PAUSE = Path('/opt/cardboarddex/ingestion.paused')
NAMES = ('backend', 'postgres', 'redis', 'redis-cache', 'cloudflared', 'celery-worker', 'celery-beat')


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed exit={result.returncode}: {result.stderr.strip()}')
    return result.stdout


def regression(previous, sample):
    """Pure threshold evaluation, with sustained pressure and failure hysteresis."""
    reasons = []
    old = previous.get('containers', {})
    for name, current in sample['containers'].items():
        before = old.get(name, {})
        if not current['running'] or current['oom'] or current['oom_kill'] > before.get('oom_kill', 0):
            reasons.append(f'{name}: stopped or OOM')
        if current['restarts'] > before.get('restarts', current['restarts']):
            reasons.append(f'{name}: restarted')
    failures = previous.get('api_failures', 0) + 1 if not sample['api_ready'] else 0
    sample['api_failures'] = failures
    if failures >= 3: reasons.append('API failed three consecutive probes')
    pressure = sample['available_mib'] < 150 or sample['swap_in_mib_s'] > 1 or sample['iowait_pct'] > 10
    since = previous.get('pressure_since') or sample['at'] if pressure else None
    sample['pressure_since'] = since
    if since is not None and sample['at'] - since >= 300:
        reasons.append('Memory/swap/I/O pressure persisted for five minutes')
    if sample['backup_age_seconds'] is None or sample['backup_age_seconds'] > 23400:
        reasons.append('No completed backup within 6.5 hours')
    return reasons


def sample(previous):
    now = time.time()
    memory = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    vm = {line.split()[0]: int(line.split()[1]) for line in Path('/proc/vmstat').read_text().splitlines()}
    cpu = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    elapsed = max(1, now - previous.get('at', now))
    delta_cpu = max(1, sum(cpu) - sum(previous.get('cpu_ticks', cpu)))
    result = {'at': now, 'available_mib': memory['MemAvailable'] / 1024,
              'swap_in_pages': vm['pswpin'], 'cpu_ticks': cpu,
              'swap_in_mib_s': max(0, vm['pswpin'] - previous.get('swap_in_pages', vm['pswpin'])) * os.sysconf('SC_PAGE_SIZE') / elapsed / 1048576,
              'iowait_pct': max(0, cpu[4] - previous.get('cpu_ticks', cpu)[4]) / delta_cpu * 100,
              'containers': {}}
    for name in NAMES:
        container = f'app-{name}-1'
        obj = json.loads(run(['docker', 'inspect', '--format', '{{json .}}', container]))
        state = obj['State']
        events = Path(f"/sys/fs/cgroup/system.slice/docker-{obj['Id']}.scope/memory.events")
        counts = dict(line.split() for line in events.read_text().splitlines()) if events.exists() else {}
        result['containers'][name] = {'running': state['Running'], 'oom': state['OOMKilled'],
                                     'oom_kill': int(counts.get('oom_kill', 0)), 'restarts': obj['RestartCount']}
    probe = subprocess.run(['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8000/ready'], capture_output=True)
    result['api_ready'] = probe.returncode == 0
    if probe.returncode:
        logging.error('API probe failed exit=%s error=%s', probe.returncode, probe.stderr.decode(errors='replace'))
    backups = list(Path('/var/backups/cardboarddex').glob('*/manifest.json'))
    result['backup_age_seconds'] = now - max(p.stat().st_mtime for p in backups) if backups else None
    keys = ['cardboarddex:passive:v2:cycle', 'cardboarddex:passive:v2:tcgapi', 'cardboarddex:passive:v2:ebay']
    values = run(['docker', 'exec', 'app-redis-1', 'redis-cli', '--raw', 'MGET', *keys]).splitlines()
    if len(values) >= 3 and all(values[:3]):
        cycle, *states = [json.loads(value) for value in values[:3]]
        result['coverage'] = {}
        for provider, progress in zip(('tcgapi', 'ebay'), states):
            checked = sum(progress['checked'].get(cid, 0) >= cycle['starts'] for cid in cycle['members'])
            result['coverage'][provider] = {'checked': checked, 'pool': len(cycle['members']),
                'deadline': cycle['ends'], 'overdue': len(cycle['members']) - checked if now >= cycle['ends'] else 0,
                'last_success': progress['last_success'], 'cursor': progress['cursor'],
                'catalog_advances': progress['catalog_advances'], 'retry_count': len(progress['retries'])}
        result['previous_cycles'] = cycle.get('history', [])[-2:]
    day = int(now // 86400)
    quota_keys = [f'cardboarddex:{p}:{kind}:{day}' for p in ('tcgapi', 'ebay') for kind in ('requests', 'scheduled_requests')]
    quota_values = run(['docker', 'exec', 'app-redis-1', 'redis-cli', '--raw', 'MGET', *quota_keys]).splitlines()
    result['quota'] = {key: int(value or 0) for key, value in zip(quota_keys, quota_values)}
    return result


def main():
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / 'latest.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    if PAUSE.exists():
        logging.info('Ingestion paused; monitor will not start services')
        return
    current = sample(previous)
    current['observation_started'] = previous.get('observation_started', current['at'])
    current['observe_until'] = current['observation_started'] + 48 * 3600
    reasons = regression(previous, current)
    current['regressions'] = reasons
    if reasons:
        PAUSE.touch()
        # Stop new dispatch first. Request graceful worker termination with a bounded
        # wait; a stuck provider must not prevent the memory protection action.
        run(['docker', 'update', '--restart', 'no', 'app-celery-beat-1', 'app-celery-worker-1'])
        run(['docker', 'stop', '-t', '5', 'app-celery-beat-1'])
        run(['docker', 'stop', '-t', '20', 'app-celery-worker-1'])
        logging.error('Ingestion paused for regression: %s', json.dumps(reasons))
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(current, indent=2)); temp.replace(path)
    # Journald retains timestamped samples; latest.json is the operator checkpoint.
    logging.info('ingestion_health %s', json.dumps(current, sort_keys=True))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        main()
    except Exception:
        logging.exception('Ingestion health monitor failed')
        raise SystemExit(1)
