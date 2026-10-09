import importlib.util
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location('ipv6_preflight', Path(__file__).with_name('ipv6_preflight.py'))
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def test_ipv6_auth_error_proves_transport_only():
    run = Mock(return_value=CompletedProcess([], 0, '401 2001:db8::1', ''))
    report = preflight.check_url('https://example.com/v2/', run=run)
    assert report['transport'] == 'passed'
    assert report['application'] == 'not_verified'
    command = run.call_args.args[0]
    assert '--ipv6' in command
    assert command[command.index('--noproxy') + 1] == '*'
    assert command[command.index('--proto-redir') + 1] == '=https'


@pytest.mark.parametrize('url', [
    'http://example.com', 'https://user:secret@example.com',
    'https://example.com/?key=secret', 'https://example.com/#secret',
])
def test_credentials_and_non_https_urls_rejected_before_network(url):
    run = Mock()
    with pytest.raises(ValueError):
        preflight.check_url(url, run=run)
    run.assert_not_called()


def test_ipv4_result_cannot_pass():
    run = Mock(return_value=CompletedProcess([], 0, '200 192.0.2.1', ''))
    with pytest.raises(RuntimeError, match='expected HTTPS response over IPv6'):
        preflight.check_url('https://example.com', run=run)


def test_network_error_preserves_exact_diagnostic():
    run = Mock(return_value=CompletedProcess([], 6, '000 ', 'Could not resolve host'))
    with pytest.raises(RuntimeError, match='curl exit 6: Could not resolve host'):
        preflight.check_url('https://example.com', run=run)
