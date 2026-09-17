#!/usr/bin/env python3
"""Six-hourly off-server backup; manifest is published only after all uploads succeed."""
import argparse
import base64
import configparser
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import boto3

log = logging.getLogger(__name__)


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def upload(s3, bucket, key, path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
            md5.update(chunk)
    checksum = base64.b64encode(sha.digest()).decode()
    with path.open('rb') as stream:
        result = s3.put_object(Bucket=bucket, Key=key, Body=stream,
                              ContentMD5=base64.b64encode(md5.digest()).decode(),
                              ChecksumSHA256=checksum, ServerSideEncryption='AES256')
    if result.get('ChecksumSHA256') != checksum:
        raise RuntimeError(f'S3 checksum verification failed for {key}')
    return {'key': key, 'sha256': sha.hexdigest(), 'bytes': path.stat().st_size}


def backup(config='/etc/cardboarddex/backup.env', release='/opt/cardboarddex/current'):
    os.umask(0o077)
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string('[backup]\n' + Path(config).read_text())
    values = parser['backup']
    for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION'):
        if values.get(key):
            os.environ[key] = values[key]
    bucket = values['BACKUP_BUCKET']
    root = Path(values.get('BACKUP_DIRECTORY', '/var/backups/cardboarddex'))
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = datetime.now(timezone.utc)
        stamp = started.strftime('%Y%m%dT%H%M%SZ')
        compose = ['docker', 'compose', '-p', 'app', '--env-file', values.get('APP_ENV_FILE', '/etc/cardboarddex/app.env'),
                   '-f', values.get('COMPOSE_FILE', str(Path(release) / 'docker-compose.prod.yml'))]
        stage = Path(tempfile.mkdtemp(prefix='.pending-', dir=root))
        # On any error keep the pending directory for diagnosis; never create a success marker.
        with (stage / 'postgres.dump').open('wb') as output:
            run(compose + ['exec', '-T', 'postgres', 'pg_dump', '-U', 'cardboarddex',
                           '-d', 'cardboarddex', '-Fc', '--no-owner', '--no-privileges'], stdout=output)
        with (stage / 'postgres.dump').open('rb') as source:
            run(compose + ['exec', '-T', 'postgres', 'pg_restore', '--list'], stdin=source, stdout=subprocess.DEVNULL)
        run(compose + ['exec', '-T', 'redis', 'redis-cli', '--rdb', '/tmp/backup.rdb'], stdout=subprocess.DEVNULL)
        redis_id = run(compose + ['ps', '-q', 'redis'], capture_output=True, text=True).stdout.strip()
        run(['docker', 'cp', f'{redis_id}:/tmp/backup.rdb', str(stage / 'redis.rdb')])
        revision = run(compose + ['exec', '-T', 'postgres', 'psql', '-U', 'cardboarddex', '-d', 'cardboarddex',
                                  '-Atc', 'SELECT version_num FROM alembic_version'], capture_output=True, text=True).stdout.strip()
        s3 = boto3.client('s3', region_name=values.get('AWS_DEFAULT_REGION', 'us-west-2'))
        prefixes = ['six-hourly']
        if started.weekday() == 6 and started.hour < 6:
            prefixes.append('weekly')
        manifest = {}
        for prefix in prefixes:
            objects = [upload(s3, bucket, f'{prefix}/{stamp}/{name}', stage / name)
                       for name in ('postgres.dump', 'redis.rdb')]
            manifest = {'started_at': started.isoformat(), 'completed_at': datetime.now(timezone.utc).isoformat(),
                        'revision': revision, 'objects': objects}
            (stage / 'manifest.json').write_text(json.dumps(manifest))
            upload(s3, bucket, f'{prefix}/{stamp}/manifest.json', stage / 'manifest.json')
        stage.rename(root / stamp)
        # Prune only successful local backups, never failed/pending artifacts.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        for path in root.iterdir():
            if path.is_dir() and not path.name.startswith('.') and (path / 'manifest.json').is_file():
                if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                    shutil.rmtree(path)
        log.info('Backup uploaded and verified: %s', stamp)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/cardboarddex/backup.env')
    parser.add_argument('--release', default='/opt/cardboarddex/current')
    args = parser.parse_args()
    try:
        backup(args.config, args.release)
    except Exception:
        log.exception('Backup failed; no success marker was published for the incomplete backup')
        raise SystemExit(1)
