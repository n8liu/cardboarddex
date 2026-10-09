import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).with_name('recover_services.sh')
IMAGE = '349558247779.dkr-ecr.us-west-2.on.aws/cardboarddex-backend@sha256:' + 'a' * 64


def run_recovery(tmp_path, ready=True, actual=IMAGE):
    release = tmp_path / 'release'
    release.mkdir()
    (release / 'image.txt').write_text(IMAGE)
    calls = tmp_path / 'calls.jsonl'
    stub = f'#!{sys.executable}\n' + '''
import os,sys,json
from pathlib import Path
with open(os.environ['CALLS'],'a') as f:
 f.write(json.dumps({'tool':Path(sys.argv[0]).name,'args':sys.argv[1:],'image':os.environ['BACKEND_IMAGE']})+'\\n')
if Path(sys.argv[0]).name=='curl':raise SystemExit(int(os.environ['READY_EXIT']))
if sys.argv[1]=='inspect':print(os.environ['ACTUAL'])
elif 'ps' in sys.argv:print('backend-id')
'''
    for command in ('docker', 'curl'):
        p = tmp_path / command
        p.write_text(stub)
        p.chmod(0o755)
    result = subprocess.run(['bash', str(SCRIPT), str(release), '--traffic'], capture_output=True, text=True,
                            env={**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
                                 'CALLS': str(calls), 'BACKEND_IMAGE': 'stale-image', 'ACTUAL': actual,
                                 'READY_EXIT': '0' if ready else '22'})
    return result, [json.loads(line) for line in calls.read_text().splitlines()]


def test_pins_release_and_opens_tunnel_only_after_readiness(tmp_path):
    result, calls = run_recovery(tmp_path)
    assert result.returncode == 0, result.stderr
    assert all(call['image'] == IMAGE for call in calls)
    assert calls[-2]['tool'] == 'curl'
    assert calls[-1]['args'][-1] == 'cloudflared'
    assert not any('celery-worker' in call['args'] or 'celery-beat' in call['args'] for call in calls)


def test_failed_readiness_keeps_tunnel_stopped(tmp_path):
    result, calls = run_recovery(tmp_path, ready=False)
    assert result.returncode != 0
    assert not any('cloudflared' in call['args'] for call in calls)


def test_wrong_running_image_keeps_tunnel_stopped(tmp_path):
    result, calls = run_recovery(tmp_path, actual='wrong-image')
    assert result.returncode != 0
    assert not any('cloudflared' in call['args'] for call in calls)
