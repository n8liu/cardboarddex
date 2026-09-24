"""Verify safe zram initialization without root or real swap devices."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize(('active', 'size', 'expected'), [(True, '536870912', 0), (False, '0', 0), (False, '536870912', 1)])
def test_zram_never_reformats_initialized_swap(tmp_path, active, size, expected):
    sysfs = tmp_path / 'zram'
    sysfs.mkdir()
    (sysfs / 'disksize').write_text(size)
    script = tmp_path / 'zram.sh'
    script.write_text(Path(__file__).with_name('zram.sh').read_text().replace('/sys/block/zram0', str(sysfs)))
    events = tmp_path / 'events'
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    mock = f'#!{sys.executable}\n' + '''
import json
import os
from pathlib import Path
import sys
name = Path(sys.argv[0]).name
with Path(os.environ['EVENTS']).open('a') as f:
    f.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == 'id':
    print(0)
elif name == 'swapon' and '--show=NAME' in sys.argv and os.environ['ACTIVE'] == '1':
    print('/dev/zram0')
'''
    for name in ('id', 'modprobe', 'swapon', 'mkswap', 'sysctl'):
        path = bin_dir / name
        path.write_text(mock)
        path.chmod(0o755)
    result = subprocess.run(
        ['bash', str(script)], capture_output=True, text=True, timeout=10,
        env={**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
             'ACTIVE': '1' if active else '0', 'EVENTS': str(events)},
    )
    assert result.returncode == expected, result.stderr
    calls = [json.loads(line) for line in events.read_text().splitlines()]
    if active or size != '0':
        assert not any(call[0] == 'mkswap' for call in calls)
        assert (sysfs / 'disksize').read_text() == size
    else:
        assert ['mkswap', '/dev/zram0'] in calls
        assert ['swapon', '--priority', '100', '/dev/zram0'] in calls
        assert (sysfs / 'comp_algorithm').read_text().strip() == 'lz4'
    assert not any('swapoff' in call for call in calls)
