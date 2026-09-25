#!/usr/bin/env python3
"""Preview/apply dedicated R2 buckets and CDN rule; preserve other zone rules."""
import argparse
import json
import logging
import os
import re
import httpx

PUBLIC_BUCKET = 'cardboarddex-images'
STATE_BUCKET = 'cardboarddex-images-state'
DOMAIN = 'images.cardboarddex.app'
RULE = {
    'ref': 'cardboarddex_r2_images',
    'description': 'CardboardDex versioned R2 image delivery',
    'expression': '(http.host eq "images.cardboarddex.app" and (starts_with(http.request.uri.path, "/cards/") or http.request.uri.path eq "/placeholder.svg"))',
    'action': 'set_cache_settings',
    'action_parameters': {
        'cache': True, 'browser_ttl': {'mode': 'respect_origin'},
        'edge_ttl': {'mode': 'respect_origin', 'status_code_ttl': [
            {'status_code_range': {'from': 400, 'to': 599}, 'value': -1}
        ]},
    },
    'enabled': True,
}


def configure(client, account, zone):
    def api(method, path, body=None, missing=False):
        response = client.request(method, path, json=body)
        if missing and response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if not data.get('success'):
            raise RuntimeError(f'Cloudflare {method} {path}: {data.get("errors")}')
        return data.get('result')
    info = api('GET', f'/zones/{zone}')
    if info.get('name') != 'cardboarddex.app' or info.get('account', {}).get('id') != account:
        raise ValueError('Zone must be cardboarddex.app in the supplied account')
    root = f'/accounts/{account}/r2/buckets'
    for name in (PUBLIC_BUCKET, STATE_BUCKET):
        existing = api('GET', f'{root}/{name}', missing=True)
        if existing is None:
            api('POST', root, {'name': name, 'storageClass': 'Standard'})
        elif existing.get('storageClass', existing.get('storage_class', 'Standard')) != 'Standard':
            raise ValueError(f'Existing bucket {name} is not Standard storage')
        domains = api('GET', f'{root}/{name}/domains/custom')
        if name == STATE_BUCKET and domains.get('domains'):
            raise ValueError('State bucket already has public custom domains')
        api('PUT', f'{root}/{name}/domains/managed', {'enabled': False})
    custom = api('GET', f'{root}/{PUBLIC_BUCKET}/domains/custom/{DOMAIN}', missing=True)
    if custom is None:
        api('POST', f'{root}/{PUBLIC_BUCKET}/domains/custom', {'domain': DOMAIN, 'enabled': True, 'zoneId': zone, 'minTLS': '1.2'})
    elif not custom.get('enabled'):
        api('PUT', f'{root}/{PUBLIC_BUCKET}/domains/custom/{DOMAIN}', {'enabled': True, 'minTLS': '1.2'})
    ruleset = api('GET', f'/zones/{zone}/rulesets/phases/http_request_cache_settings/entrypoint', missing=True)
    if ruleset is None:
        api('POST', f'/zones/{zone}/rulesets', {'name': 'CardboardDex image cache', 'kind': 'zone', 'phase': 'http_request_cache_settings', 'rules': [RULE]})
    else:
        existing_rule = next((rule for rule in ruleset.get('rules', []) if rule.get('ref') == RULE['ref']), None)
        rules = f'/zones/{zone}/rulesets/{ruleset["id"]}/rules'
        if existing_rule:
            api('PATCH', f'{rules}/{existing_rule["id"]}', RULE)
        else:
            api('POST', rules, RULE)
    print('Configured image buckets, custom domain, and cache rule. Verify domain activation before cutover.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({'public_bucket': PUBLIC_BUCKET, 'private_state_bucket': STATE_BUCKET, 'domain': DOMAIN, 'cache_rule': RULE}, indent=2))
        return
    account, zone = os.environ['CLOUDFLARE_ACCOUNT_ID'], os.environ['CLOUDFLARE_ZONE_ID']
    if not all(re.fullmatch(r'[a-f0-9]{32}', value) for value in (account, zone)):
        raise ValueError('Invalid Cloudflare account/zone identifier')
    with httpx.Client(base_url='https://api.cloudflare.com/client/v4', headers={'Authorization': 'Bearer ' + os.environ['CLOUDFLARE_API_TOKEN']}, timeout=30) as client:
        configure(client, account, zone)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('R2 provisioning failed')
        raise SystemExit(1)
