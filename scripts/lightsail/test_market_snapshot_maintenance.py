"""Exercise paused-mode maintenance with fake Docker, never a real host."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("locked", [False, True])
def test_market_maintenance_uses_isolated_worker_and_respects_deploy_lock(tmp_path, locked):
    root = tmp_path / "app"
    release = root / "releases" / "reviewed"
    release.mkdir(parents=True)
    (release / "image.txt").write_text("example.invalid/backend@sha256:" + "c" * 64)
    (root / "current").symlink_to(release)
    source = Path(__file__).with_name("refresh_market_snapshots.sh")
    script = tmp_path / "refresh.sh"
    script.write_text(source.read_text().replace("/opt/cardboarddex", str(root)))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    events = tmp_path / "events"
    mock = f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
with Path(os.environ["EVENTS"]).open("a") as output:
    output.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + "\\n")
if Path(sys.argv[0]).name == "flock" and os.environ["LOCKED"] == "1":
    raise SystemExit(1)
'''
    for name in ["docker", "flock"]:
        executable = bin_dir / name
        executable.write_text(mock)
        executable.chmod(0o755)
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=10,
        env={**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
             "EVENTS": str(events), "LOCKED": "1" if locked else "0"})
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in events.read_text().splitlines()]
    assert calls[0] == ["flock", "-sn", "9"]
    if locked:
        assert len(calls) == 1
    else:
        assert calls[1] == ["flock", "-n", "8"]
        run = next(call for call in calls if "run" in call)
        assert run[-4:] == ["celery-worker", "python", "-m", "jobs.refresh_market_snapshots"]
        assert "--no-deps" in run and "--name" in run
        assert not any("up" in call or "exec" in call for call in calls)
        assert calls[-1] == ["docker", "rm", "-f", "cardboarddex-market-snapshots-refresh"]
    unit = source.with_name("cardboarddex-market-snapshots.service").read_text()
    assert "ConditionPathExists=/opt/cardboarddex/ingestion.paused" in unit


def test_paused_maintenance_jobs_share_a_single_container_lock():
    for name in ("refresh_live_stats.sh", "refresh_market_snapshots.sh"):
        script = Path(__file__).with_name(name).read_text()
        assert "exec 8>/opt/cardboarddex/maintenance.lock" in script
        assert script.index("flock -n 8") < script.index("docker compose")
