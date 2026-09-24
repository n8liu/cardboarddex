"""Exercise the SSM gate with no network access or real waiting."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).with_name('wait_for_ssm.sh')
TARGET = 'mi-' + 'a' * 17


def run_gate(tmp_path, outcomes, target=TARGET):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps(outcomes))
    events = tmp_path / 'events.jsonl'
    mock = f'#!{sys.executable}\n' + '''
import json
import os
from pathlib import Path
import sys
with Path(os.environ['EVENTS']).open('a') as f:
    f.write(json.dumps(sys.argv) + '\\n')
if Path(sys.argv[0]).name == 'aws':
    p = Path(os.environ['STATE'])
    outcomes = json.loads(p.read_text())
    code, message = outcomes.pop(0)
    p.write_text(json.dumps(outcomes))
    print(message, file=sys.stderr if code else sys.stdout)
    raise SystemExit(code)
'''
    for name in ('aws', 'sleep'):
        path = tmp_path / name
        path.write_text(mock)
        path.chmod(0o755)
    result = subprocess.run(
        ['bash', str(SCRIPT), target], capture_output=True, text=True, timeout=15,
        env={**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
             'STATE': str(state), 'EVENTS': str(events), 'AWS_REGION': 'us-west-2'},
    )
    calls = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    return result, calls


def test_online_does_not_wait(tmp_path):
    result, calls = run_gate(tmp_path, [(0, 'Online')])
    assert result.returncode == 0
    assert len(calls) == 1
    assert f'Key=InstanceIds,Values={TARGET}' in calls[0]


def test_recovers_after_offline_heartbeat(tmp_path):
    result, calls = run_gate(tmp_path, [(0, 'ConnectionLost'), (0, 'Online')])
    assert result.returncode == 0
    assert sum(Path(call[0]).name == 'sleep' for call in calls) == 1


@pytest.mark.parametrize('status', ['ConnectionLost', 'None'])
def test_offline_or_missing_node_fails_closed(tmp_path, status):
    result, calls = run_gate(tmp_path, [(0, status)] * 30)
    assert result.returncode == 1
    assert 'deployment stopped before SSH' in result.stderr
    assert sum(Path(call[0]).name == 'aws' for call in calls) == 30
    assert sum(Path(call[0]).name == 'sleep' for call in calls) == 29


def test_aws_error_is_visible_and_stops_immediately(tmp_path):
    result, calls = run_gate(tmp_path, [(254, 'AccessDeniedException: permission denied')])
    assert result.returncode == 1
    assert 'AccessDeniedException: permission denied' in result.stderr
    assert len(calls) == 1


def test_invalid_target_does_not_call_aws(tmp_path):
    result, calls = run_gate(tmp_path, [], target='--bad-target')
    assert result.returncode == 1
    assert not calls
