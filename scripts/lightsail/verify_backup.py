#!/usr/bin/env python3
"""Check backup age; optionally download and restore on a disposable CI runner."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import boto3


def restore_redis(archive, image='redis:7-alpine'):
    """Load the actual RDB in an isolated container; never execute restored jobs."""
    name = f'cardboarddex-redis-restore-{uuid.uuid4().hex[:10]}'
    try:
        subprocess.run(['docker', 'create', '--name', name, '--network', 'none', image,
                        'redis-server', '--save', '', '--appendonly', 'no'],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['docker', 'cp', str(archive), f'{name}:/data/dump.rdb'], check=True)
        subprocess.run(['docker', 'start', name], check=True, stdout=subprocess.DEVNULL)
        for _ in range(60):
            probe = subprocess.run(['docker', 'exec', name, 'redis-cli', 'ping'],
                                   capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == 'PONG':
                info = subprocess.check_output(['docker', 'exec', name, 'redis-cli', 'INFO', 'keyspace'], text=True)
                # Report counts only; provider credentials and queued payloads stay private.
                print('Redis restored: ' + '; '.join(line for line in info.splitlines() if line.startswith('db')))
                return
            state = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Running}}', name], text=True).strip()
            if state != 'true':
                raise RuntimeError('Redis restore container exited before loading the backup')
            time.sleep(0.5)
        raise RuntimeError('Redis restore did not become ready')
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', name], check=False, stdout=subprocess.DEVNULL)


def verify(bucket, restore=False, postgres_image='postgres:16-alpine', manifest_key=None,
           redis_image='redis:7-alpine'):
    s3 = boto3.client('s3')
    manifests = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix='six-hourly/'):
        manifests.extend(o['Key'] for o in page.get('Contents', []) if o['Key'].endswith('/manifest.json'))
    if not manifests:
        raise RuntimeError('No completed off-server backups found')
    key = manifest_key or max(manifests)
    if key not in manifests:
        raise RuntimeError('Requested manifest is not a completed six-hourly backup')
    manifest = json.loads(s3.get_object(Bucket=bucket, Key=key)['Body'].read())
    objects = manifest['objects']
    if sorted(Path(obj['key']).name for obj in objects) != ['postgres.dump', 'redis.rdb']:
        raise RuntimeError('Manifest must contain exactly PostgreSQL and Redis archives')
    if any(obj['key'].rsplit('/', 1)[0] != key.rsplit('/', 1)[0] for obj in objects):
        raise RuntimeError('Archive and manifest prefixes differ')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(manifest['started_at'])).total_seconds()
    if age < 0 or age > 21600:
        raise RuntimeError(f'Latest backup exceeds six-hour recovery target: age={age:.0f}s')
    print(f'Latest backup age: {age / 3600:.2f}h; revision: {manifest["revision"]}')
    if not restore:
        return
    with tempfile.TemporaryDirectory(prefix='cardboarddex-restore-') as temp:
        root = Path(temp)
        for obj in manifest['objects']:
            destination = root / Path(obj['key']).name
            s3.download_file(bucket, obj['key'], str(destination))
            if hashlib.sha256(destination.read_bytes()).hexdigest() != obj['sha256']:
                raise RuntimeError(f'Checksum mismatch for {obj["key"]}')
        name = f'cardboarddex-restore-{uuid.uuid4().hex[:10]}'
        try:
            subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none',
                            '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_USER=cardboarddex',
                            '-e', 'POSTGRES_DB=cardboarddex', postgres_image], check=True, stdout=subprocess.DEVNULL)
            for attempt in range(60):
                logs = subprocess.run(['docker', 'logs', name], capture_output=True, text=True).stdout
                init_done = (
                    'PostgreSQL init process complete; ready for start up.' in logs
                    or 'PostgreSQL Database directory appears to contain a database' in logs
                    or logs.count('database system is ready to accept connections') >= 2
                )
                if init_done:
                    if subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'cardboarddex', '-d', 'cardboarddex'],
                                      capture_output=True).returncode == 0:
                        probe = subprocess.run(['docker', 'exec', name, 'psql', '-U', 'cardboarddex', '-d', 'cardboarddex',
                                                '-At', '-c', 'SELECT 1'], capture_output=True, text=True)
                        if probe.returncode == 0 and probe.stdout.strip() == '1':
                            break
                time.sleep(0.5)
            else:
                raise RuntimeError('Disposable PostgreSQL failed to start')
            import os
            subprocess.run(['bash', str(Path(__file__).with_name('restore.sh')), str(root / 'postgres.dump')],
                           env={**os.environ, 'RESTORE_CONTAINER': name}, check=True)
            revision = subprocess.check_output(['docker', 'exec', name, 'psql', '-U', 'cardboarddex', '-d', 'cardboarddex',
                                                '-Atc', 'SELECT version_num FROM alembic_version'], text=True).strip()
            if revision != manifest['revision']:
                raise RuntimeError('Restored schema revision differs from backup manifest')
        finally:
            subprocess.run(['docker', 'rm', '-f', '-v', name], check=False, stdout=subprocess.DEVNULL)
        restore_redis(root / 'redis.rdb', redis_image)
    print(f'PostgreSQL and Redis backup verified and restored: {key}')
    return {'bucket': bucket, 'manifest_key': key, 'revision': manifest['revision'],
            'verified_at': datetime.now(timezone.utc).isoformat(), 'postgres_restored': True,
            'redis_restored': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--postgres-image', default='postgres:16-alpine')
    parser.add_argument('--redis-image', default='redis:7-alpine')
    parser.add_argument('--manifest-key', help='Verify an exact backup instead of latest')
    parser.add_argument('--report', type=Path, help='Write a non-secret restore receipt; requires --restore')
    args = parser.parse_args()
    if args.report and not args.restore:
        parser.error('--report requires --restore')
    try:
        report = verify(args.bucket, args.restore, args.postgres_image, args.manifest_key, args.redis_image)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2) + '\n')
    except Exception:
        logging.exception('Backup verification failed')
        raise SystemExit(1)
