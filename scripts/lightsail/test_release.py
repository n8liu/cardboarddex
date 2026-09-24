"""Run the release orchestration against disposable paths and fake host services."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('backup_failure', ['', 'enable', 'inactive'])
def test_release_requires_active_backup_timer(tmp_path, backup_failure):
    root = tmp_path / 'cardboarddex'
    old = root / 'releases' / ('a' * 40)
    new = root / 'releases' / ('b' * 40)
    for release in (old, new):
        release.mkdir(parents=True)
        (release / 'image.txt').write_text('example.invalid/backend@sha256:' + 'c' * 64)
    (root / 'current').symlink_to(old)
    # Only relocate the absolute production directory; execute the real flow.
    script = tmp_path / 'release.sh'
    script.write_text(Path(__file__).with_name('release.sh').read_text().replace(
        '/opt/cardboarddex', str(root),
    ))
    events = tmp_path / 'events.jsonl'
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    mock = f'#!{sys.executable}\n' + '''
import json
import os
from pathlib import Path
import sys
command = Path(sys.argv[0]).name
args = sys.argv[1:]
with Path(os.environ['EVENTS']).open('a') as f:
    f.write(json.dumps([command, *args]) + '\\n')
if command == 'docker':
    if args[:2] == ['image', 'inspect']:
        print('amd64' if '{{.Architecture}}' in args else 'sha256:runtime')
    elif args[0] == 'inspect':
        print('sha256:runtime')
    elif 'ps' in args:
        print('beat' if args[-1] == 'celery-beat' else 'backend')
elif command == 'sudo':
    if args[:2] == ['-n', 'bash'] and args[-1].endswith('/scripts/lightsail/install_zram.sh'):
        raise SystemExit(0)
    assert args == ['-n', 'systemctl', 'enable', '--now', 'cardboarddex-backup.timer']
    if os.environ['BACKUP_FAILURE'] == 'enable':
        print('sudo: a password is required', file=sys.stderr)
        raise SystemExit(1)
elif command == 'systemctl':
    assert args == ['is-active', '--quiet', 'cardboarddex-backup.timer']
    if os.environ['BACKUP_FAILURE'] == 'inactive':
        raise SystemExit(3)
'''
    for name in ('docker', 'curl', 'flock', 'sudo', 'systemctl', 'sleep'):
        path = bin_dir / name
        path.write_text(mock)
        path.chmod(0o755)
    result = subprocess.run(
        ['bash', str(script), str(new)], capture_output=True, text=True, timeout=15,
        env={**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
             'EVENTS': str(events), 'BACKUP_FAILURE': backup_failure},
    )
    calls = [json.loads(line) for line in events.read_text().splitlines()]
    if backup_failure:
        assert result.returncode != 0
        assert (root / 'current').resolve() == old
        assert 'Deployment failed; restoring previous release' in result.stderr
        assert 'Verified deployment completed' not in result.stdout
        assert any(str(old / 'docker-compose.prod.yml') in call and 'up' in call for call in calls)
        if backup_failure == 'enable':
            assert 'sudo: a password is required' in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert (root / 'current').resolve() == new
        assert (root / 'previous').resolve() == old
        assert 'Verified deployment completed' in result.stdout
