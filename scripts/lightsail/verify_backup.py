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
import uuid
import boto3


def verify(bucket, restore=False, postgres_image='postgres:16-alpine'):
    s3 = boto3.client('s3')
    manifests = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix='six-hourly/'):
        manifests.extend(o['Key'] for o in page.get('Contents', []) if o['Key'].endswith('/manifest.json'))
    if not manifests:
        raise RuntimeError('No completed off-server backups found')
    key = max(manifests)
    manifest = json.loads(s3.get_object(Bucket=bucket, Key=key)['Body'].read())
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
            import time
            for attempt in range(30):
                if subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'cardboarddex'], stdout=subprocess.DEVNULL).returncode == 0:
                    break
                time.sleep(1)
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
    print('Off-server backup downloaded, checksum verified, and restored successfully')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--postgres-image', default='postgres:16-alpine')
    args = parser.parse_args()
    try:
        verify(args.bucket, args.restore, args.postgres_image)
    except Exception:
        logging.exception('Backup verification failed')
        raise SystemExit(1)
