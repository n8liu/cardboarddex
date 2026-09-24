"""Exercise the deployment preflight without opening connections or deploying."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


DEPLOY = Path(__file__).resolve().parents[1] / 'deploy_to_lightsail.sh'
AUTHENTICATED = 'Authenticated to 192.0.2.1 ([192.0.2.1]:22) using "publickey".\n'
STALLED = AUTHENTICATED + 'Timeout, server 192.0.2.1 not responding.\n'


def run_preflight(tmp_path, outcomes, **overrides):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    events = tmp_path / 'events.jsonl'
    scenarios = tmp_path / 'outcomes.json'
    scenarios.write_text(json.dumps(outcomes))
    mock = f'#!{sys.executable}\n' + '''
import json
import os
from pathlib import Path
import sys

command = Path(sys.argv[0]).name
with Path(os.environ['MOCK_EVENTS']).open('a') as stream:
    stream.write(json.dumps([command, *sys.argv[1:]]) + '\\n')
if command == 'ssh' and sys.argv[-1] == 'true':
    path = Path(os.environ['MOCK_OUTCOMES'])
    outcomes = json.loads(path.read_text())
    status, message = outcomes.pop(0)
    path.write_text(json.dumps(outcomes))
    sys.stderr.write(message)
    raise SystemExit(status)
if command == 'aws':
    # Stop at the first deployment action; never run the actual release.
    raise SystemExit(42)
if command == 'ssh':
    sys.stdin.read()
'''
    for name in ('ssh', 'ssh-keygen', 'aws', 'sleep'):
        path = bin_dir / name
        path.write_text(mock)
        path.chmod(0o755)
    # Run the real timeout wrapper with the current test interpreter.
    (bin_dir / 'python3').symlink_to(sys.executable)
    env = {
        **os.environ,
        'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
        'MOCK_EVENTS': str(events),
        'MOCK_OUTCOMES': str(scenarios),
        'LIGHTSAIL_HOST': '192.0.2.1',
        'LIGHTSAIL_USER': 'ubuntu',
        'KEY_PATH': str(tmp_path / 'dummy-key'),
        'KNOWN_HOSTS_FILE': str(tmp_path / 'dummy-known-hosts'),
        'BACKEND_IMAGE': '349558247779.dkr.ecr.us-west-2.amazonaws.com/cardboarddex-backend@sha256:' + 'a' * 64,
        'RELEASE_ID': 'b' * 40,
        'TMPDIR': str(tmp_path),
        **overrides,
    }
    result = subprocess.run(
        ['bash', str(DEPLOY)], env=env, capture_output=True, text=True, timeout=15,
    )
    calls = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    probes = [call for call in calls if call[0] == 'ssh' and call[-1] == 'true']
    for probe in probes:
        assert 'StrictHostKeyChecking=yes' in probe
        assert f'UserKnownHostsFile={env["KNOWN_HOSTS_FILE"]}' in probe
        assert 'ServerAliveCountMax=3' in probe
    return result, calls, probes


def test_authenticated_stall_retries_then_allows_deployment(tmp_path):
    result, calls, probes = run_preflight(tmp_path, [(255, STALLED), (0, AUTHENTICATED)])
    assert result.returncode == 42  # Reached the mocked deployment boundary.
    assert len(probes) == 2
    assert 'SSH connection verified successfully' in result.stdout
    assert 'authentication succeeded' in result.stderr
    assert 'Check LIGHTSAIL_SSH_KEY' not in result.stderr
    assert sum(call[0] == 'sleep' for call in calls) == 1


def test_persistent_authenticated_stall_stops_before_deployment(tmp_path):
    result, calls, probes = run_preflight(tmp_path, [(255, STALLED)] * 3)
    assert result.returncode == 1
    assert len(probes) == 3
    assert not any(call[0] == 'aws' for call in calls)
    assert sum(call[0] == 'sleep' for call in calls) == 2
    assert 'server memory/swap' in result.stderr
    assert result.stderr.count('Timeout, server') == 3


@pytest.mark.parametrize(('message', 'diagnostic'), [
    ('TargetNotConnected: managed node is not connected.\n', 'SSM cannot open a session'),
    ('Host key verification failed.\n', 'SSH host verification failed'),
    ('ubuntu@192.0.2.1: Permission denied (publickey).\n', 'SSH authentication failed'),
    ('ssh: connect to host 192.0.2.1 port 22: Connection timed out\n', 'SSH did not complete authentication'),
])
def test_pre_authentication_failure_does_not_retry_or_deploy(tmp_path, message, diagnostic):
    result, calls, probes = run_preflight(tmp_path, [(255, message)])
    assert result.returncode == 1
    assert len(probes) == 1
    assert diagnostic in result.stderr
    assert not any(call[0] in ('aws', 'sleep') for call in calls)


def test_successful_probe_does_not_retry(tmp_path):
    result, calls, probes = run_preflight(tmp_path, [(0, AUTHENTICATED)])
    assert result.returncode == 42
    assert len(probes) == 1
    assert not any(call[0] == 'sleep' for call in calls)


def test_remote_command_failure_is_not_retried_as_a_connection_stall(tmp_path):
    result, calls, probes = run_preflight(tmp_path, [(1, AUTHENTICATED + 'Session command failed\n')])
    assert result.returncode == 1
    assert len(probes) == 1
    assert 'remote session probe failed (exit 1)' in result.stderr
    assert not any(call[0] in ('aws', 'sleep') for call in calls)


def test_ipv6_destination_and_dualstack_registry_reach_deployment(tmp_path):
    result, calls, probes = run_preflight(
        tmp_path, [(0, AUTHENTICATED)], LIGHTSAIL_HOST='2001:db8::1',
        BACKEND_IMAGE='349558247779.dkr-ecr.us-west-2.on.aws/cardboarddex-backend@sha256:' + 'a' * 64,
    )
    assert result.returncode == 42
    assert probes[0][-2] == 'ubuntu@2001:db8::1'
    assert any('docker login' in call[-1] and 'dkr-ecr.us-west-2.on.aws' in call[-1] for call in calls)


@pytest.mark.parametrize('host', ['-oProxyCommand=bad', '2001:db8::invalid', 'fe80::1%en0', '[2001:db8::1]', 'host;command'])
def test_invalid_destination_fails_before_ssh(tmp_path, host):
    result, calls, probes = run_preflight(tmp_path, [], LIGHTSAIL_HOST=host)
    assert result.returncode != 0
    assert not calls and not probes


def test_unapproved_registry_fails_before_ssh(tmp_path):
    result, calls, probes = run_preflight(
        tmp_path, [],
        BACKEND_IMAGE='349558247779.dkr-ecr.us-west-2.on.aws.attacker.invalid/cardboarddex-backend@sha256:' + 'a' * 64,
    )
    assert result.returncode != 0
    assert not calls and not probes


def test_ssm_transport_preserves_host_verification_and_reuses_session(tmp_path):
    target = 'mi-' + 'a' * 17
    result, calls, probes = run_preflight(tmp_path, [(0, AUTHENTICATED)], LIGHTSAIL_SSM_TARGET=target)
    assert result.returncode == 42
    assert f'ProxyCommand=aws ssm start-session --target {target} --document-name AWS-StartSSHSession --parameters portNumber=%p --region us-west-2' in probes[0]
    assert 'ControlMaster=auto' in probes[0]
    assert any('-O' in call and 'exit' in call for call in calls)
