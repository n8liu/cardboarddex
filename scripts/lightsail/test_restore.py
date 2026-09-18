"""Opt-in destructive tests restricted to unique disposable container names."""
import os
from pathlib import Path
import subprocess
import time
import uuid
import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RUN_CONTAINER_TESTS') != '1', reason='requires disposable Docker containers')


def test_restore_rejects_nonempty_and_rolls_back_corruption(tmp_path):
    name = 'gc-restore-test-' + uuid.uuid4().hex[:10]
    image = os.environ.get('TEST_POSTGRES_IMAGE', 'postgres:16-alpine')
    def run(*args, **kwargs):
        return subprocess.run(args, check=True, **kwargs)
    def sql(query):
        cmd = ['docker', 'exec', name, 'psql', '-U', 'cardboarddex', '-d', 'cardboarddex', '-At', '-v', 'ON_ERROR_STOP=1', '-c', query]
        for attempt in range(30):
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout
            err = (res.stderr or '') + (res.stdout or '')
            transient = [
                'terminating connection due to administrator command',
                'the database system is starting up',
                'the database system is shutting down',
                'could not connect to server',
                'Connection refused',
                'server closed the connection unexpectedly',
            ]
            if any(t in err for t in transient) and attempt < 29:
                time.sleep(0.5)
                continue
            raise subprocess.CalledProcessError(res.returncode, cmd, output=res.stdout, stderr=res.stderr)

    def wait_ready():
        for _ in range(60):
            logs = subprocess.run(['docker', 'logs', name], capture_output=True, text=True).stdout
            init_done = (
                'PostgreSQL init process complete; ready for start up.' in logs
                or 'PostgreSQL Database directory appears to contain a database' in logs
                or logs.count('database system is ready to accept connections') >= 2
            )
            if init_done:
                ready = subprocess.run(
                    ['docker', 'exec', name, 'pg_isready', '-U', 'cardboarddex', '-d', 'cardboarddex'],
                    capture_output=True
                ).returncode == 0
                if ready:
                    probe = subprocess.run(
                        ['docker', 'exec', name, 'psql', '-U', 'cardboarddex', '-d', 'cardboarddex', '-At', '-c', 'SELECT 1'],
                        capture_output=True,
                        text=True
                    )
                    if probe.returncode == 0 and probe.stdout.strip() == '1':
                        return
            time.sleep(0.5)
        raise AssertionError('PostgreSQL container failed to become ready within timeout')

    try:
        run('docker', 'run', '-d', '--name', name, '--network', 'none', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_USER=cardboarddex', '-e', 'POSTGRES_DB=cardboarddex', image)
        wait_ready()
        sql("CREATE TABLE cards(id text); CREATE TABLE sets(id text); CREATE TABLE alembic_version(version_num text); INSERT INTO cards VALUES ('test'); INSERT INTO sets VALUES ('test'); INSERT INTO alembic_version VALUES ('test');")
        archive = tmp_path / 'postgres.dump'
        with archive.open('wb') as out:
            run('docker', 'exec', name, 'pg_dump', '-U', 'cardboarddex', '-d', 'cardboarddex', '-Fc', stdout=out)
        env = {**os.environ, 'RESTORE_CONTAINER': name}
        cmd = ['bash', str(Path(__file__).with_name('restore.sh')), str(archive)]
        assert subprocess.run(cmd, env=env).returncode != 0
        assert sql('SELECT count(*) FROM cards').strip() == '1'
        sql('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')
        run(*cmd, env=env)
        assert sql('SELECT id FROM cards').strip() == 'test'
        sql('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')
        archive.write_bytes(archive.read_bytes()[:200])
        assert subprocess.run(cmd, env=env).returncode != 0
        assert sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'").strip() == '0'
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', name], check=False)
