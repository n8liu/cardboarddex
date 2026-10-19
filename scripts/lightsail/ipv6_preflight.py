#!/usr/bin/env python3
"""Read-only IPv6 HTTPS transport checks. No credentials or provider calls with auth.

Run on the destination host AND inside its backend container. HTTP errors prove
transport only: authenticated provider, backup, and registry checks remain required.
"""
import argparse
import ipaddress
import json
import logging
import subprocess
from urllib.parse import urlsplit


DEFAULT_URLS = (
    'https://ssm.us-west-2.api.aws/',
    'https://ssmmessages.us-west-2.api.aws/',
    'https://s3.dualstack.us-west-2.amazonaws.com/',
    'https://349558247779.dkr-ecr.us-west-2.on.aws/v2/',
    'https://download.docker.com/linux/ubuntu/gpg',
    'https://www.pokemonpricetracker.com/api/v2/sets',
    'https://api.cardboarddex.app/ready',
)


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Use an HTTPS URL without credentials, query, or fragment')
    return parsed.hostname


def check_url(url, run=subprocess.run):
    host = validate_url(url)
    # -q ignores local curlrc; no proxies or redirects to non-HTTPS protocols.
    result = run([
        'curl', '-q', '--ipv6', '--noproxy', '*', '--silent', '--show-error',
        '--location', '--max-redirs', '5', '--proto', '=https', '--proto-redir', '=https',
        '--connect-timeout', '5', '--max-time', '20', '--output', '/dev/null',
        '--write-out', '%{http_code} %{remote_ip}', url,
    ], capture_output=True, text=True, timeout=25, check=False)
    if result.returncode:
        raise RuntimeError(f'{host}: curl exit {result.returncode}: {result.stderr.strip()}')
    status, address = result.stdout.strip().split()
    if not 200 <= int(status) <= 599 or ipaddress.ip_address(address).version != 6:
        raise RuntimeError(f'{host}: expected HTTPS response over IPv6, got {status} {address}')
    return {'host': host, 'http_status': int(status), 'remote_ipv6': address,
            'transport': 'passed', 'application': 'not_verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--relay-url', required=True, help='Public relay origin, never its shared key')
    parser.add_argument('--url', action='append', default=[], help='Additional image/package origin to probe')
    args = parser.parse_args()
    urls = [*DEFAULT_URLS, args.relay_url, *args.url]
    for url in urls:
        validate_url(url)
    failed = False
    for url in urls:
        try:
            print(json.dumps(check_url(url)))
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            logging.error('IPv6 transport check failed: %s: %s', type(exc).__name__, exc)
            failed = True
    return int(failed)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
