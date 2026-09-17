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
        return subprocess.check_output(['docker', 'exec', name, 'psql', '-U', 'cardboarddex', '-d', 'cardboarddex', '-At', '-v', 'ON_ERROR_STOP=1', '-c', query], text=True)
    try:
        run('docker', 'run', '-d', '--name', name, '--network', 'none', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_USER=cardboarddex', '-e', 'POSTGRES_DB=cardboarddex', image)
        for _ in range(40):
            if subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'cardboarddex'], capture_output=True).returncode == 0:
                break
            time.sleep(1)
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
