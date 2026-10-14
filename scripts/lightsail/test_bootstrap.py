"""Dual-stack containers must retain outbound IPv4 connectivity."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('ipv6_only', [None, 'false', 'true'])
def test_ipv4_rejection_only_on_explicit_ipv6_host(tmp_path, ipv6_only):
    source = Path(__file__).with_name('bootstrap.sh').read_text()
    block = source[source.index('# Only IPv6-only'):source.index("cat << 'EOF' > /etc/systemd/system/cardboarddex-ipv6-tuning.service")]
    block = block.replace('/etc/systemd/system/', str(tmp_path) + '/')
    env = dict(os.environ)
    env.pop('IPV6_ONLY', None)
    if ipv6_only is not None:
        env['IPV6_ONLY'] = ipv6_only
    calls = tmp_path / 'calls'
    result = subprocess.run(['bash', '-euc', 'systemctl() { echo "$*" >> "$CALLS"; };\n' + block],
                            env={**env, 'CALLS': str(calls)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'cardboarddex-firewall.service').exists() == (ipv6_only == 'true')
    assert calls.exists() == (ipv6_only == 'true')
