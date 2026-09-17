#!/usr/bin/env python3
"""Run on the VPS as root: prepare secrets for the reviewed release without restarting anything."""
import json
import os
from pathlib import Path
import secrets
import subprocess
from urllib.parse import urlparse, unquote


def inspect(name):
    return json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]


def env(container):
    return dict(item.split('=', 1) for item in container['Config']['Env'])


def quote(value):
    if '\n' in value or '\r' in value:
        raise ValueError('Multiline environment values are not supported')
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def main():
    os.umask(0o077)
    root = Path('/etc/cardboarddex')
    if (root / 'app.env').exists():
        raise SystemExit('Refusing to overwrite an existing production configuration')
    root.mkdir(exist_ok=True, parents=True)
    backend = inspect('cardboarddex-backend')
    pg = inspect('cardboarddex-postgres')
    redis = inspect('cardboarddex-redis')
    tunnel = inspect('cardboarddex-cloudflared')
    values = env(backend)
    password = env(pg).get('POSTGRES_PASSWORD') or unquote(urlparse(values['DATABASE_URL']).password or '')
    if not password:
        raise RuntimeError('Could not identify existing database credential')
    volume = next(m['Name'] for m in pg['Mounts'] if m['Destination'] == '/var/lib/postgresql/data')
    values.update(POSTGRES_PASSWORD=password, POSTGRES_HOST='postgres', DATA_VOLUME=volume,
                  APP_ENV_FILE='/etc/cardboarddex/app.env', TUNNEL_TOKEN=env(tunnel)['TUNNEL_TOKEN'],
                  REDIS_URL='redis://redis:6379/0', CACHE_REDIS_URL='redis://redis-cache:6379/0')
    values.update(POSTGRES_DB='cardboarddex', POSTGRES_USER='cardboarddex')
    for name, obj in [('POSTGRES_IMAGE', pg), ('REDIS_IMAGE', redis), ('CLOUDFLARED_IMAGE', tunnel), ('BACKEND_IMAGE', backend)]:
        image = inspect(obj['Image'])
        digests = image['RepoDigests']
        if not digests:
            raise RuntimeError(f'No pinned image digest available: {name}')
        values[name] = digests[0]
    values['ADMIN_API_KEY'] = values.get('ADMIN_API_KEY') or secrets.token_hex(32)
    # Preserve the old password for rollback; rotation is a separate, controlled operation.
    (root / 'previous-password').write_text(password)
    (root / 'next-password').write_text(secrets.token_hex(32))
    contents = ''.join(f'{k}={quote(v)}\n' for k,v in values.items())
    (root / 'app.env').write_text(contents)
    subprocess.run(['chown', 'ubuntu:ubuntu', str(root / 'app.env')], check=True)
    subprocess.run(['chown', 'root:ubuntu', str(root)], check=True)
    root.chmod(0o750)
    legacy = Path('/opt/cardboarddex/releases/legacy')
    legacy.mkdir(parents=True, exist_ok=True)
    original = json.loads(subprocess.check_output([
        'docker', 'compose', '-p', 'app', '--env-file', '/home/ubuntu/app/.env',
        '-f', '/home/ubuntu/app/docker-compose.yml', 'config', '--format', 'json']))
    for service in original['services'].values():
        service['environment'] = {key: '${' + key + ':-}' for key in service.get('environment', {})}
    for service in ('backend', 'celery-worker'):
        original['services'][service]['image'] = values['BACKEND_IMAGE']
    original['services']['redis']['command'] = ['redis-server', '--maxmemory', '64mb', '--maxmemory-policy', 'noeviction', '--appendonly', 'yes', '--appendfsync', 'everysec', '--save', '']
    original['services']['redis']['volumes'] = ['redis_data:/data']
    original['volumes']['redis_data'] = {'external': True, 'name': 'app_redis_durable'}
    original['volumes']['postgres_data'] = {'external': True, 'name': volume}
    (legacy / 'docker-compose.prod.yml').write_text(json.dumps(original, indent=2))
    (legacy / 'image.txt').write_text(values['BACKEND_IMAGE'] + '\n')
    subprocess.run(['chown', '-R', 'ubuntu:ubuntu', '/opt/cardboarddex/releases'], check=True)
    subprocess.run(['chown', 'ubuntu:ubuntu', '/opt/cardboarddex'], check=True)
    subprocess.run(['ln', '-sfn', str(legacy), '/opt/cardboarddex/current'], check=True)
    print('Prepared private production configuration with preserved image and volume identities')


if __name__ == '__main__':
    import logging
    try:
        main()
    except Exception:
        logging.exception('Production configuration staging failed')
        raise SystemExit(1)
