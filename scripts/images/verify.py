#!/usr/bin/env python3
"""Opt-in CDN acceptance check with a page-sized burst."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from time import monotonic
from urllib.parse import urlsplit
import uuid
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='https://api.cardboarddex.app')
    args = parser.parse_args()
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.get(args.api + '/cards/search', params={'limit':24, 'offset':0, 'sort_by':'price_desc', 'hide_sealed':'true'})
        response.raise_for_status()
        cards = response.json()
        assert cards, 'Catalog is empty'
        urls = [card['image_url'] for card in cards]
        assert all(urlsplit(url).hostname == 'images.cardboarddex.app' for url in urls), 'API still returns proxied images'
        assert all('/cards/' in url for url in urls), 'Initial catalog still has pending images'
        def check(url):
            start = monotonic()
            result = client.get(url)
            result.raise_for_status()
            assert result.status_code == 200
            return {'url':url, 'seconds':round(monotonic()-start, 3), 'cache':result.headers.get('cf-cache-status')}
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(check, urls + [args.api + '/ready', args.api + '/cards/live-updates?provider=all&grade_filter=all&page=1&per_page=24']))
        for url in urls:
            result = client.get(url)
            result.raise_for_status()
            assert result.headers.get('cf-cache-status') == 'HIT', f'CDN miss after warmup: {url}'
            assert result.headers.get('content-type', '').startswith('image/')
            assert 'immutable' in result.headers.get('cache-control', '')
        missing_url = 'https://images.cardboarddex.app/cards/missing/' + uuid.uuid4().hex * 2 + '.png'
        for _ in range(2):
            missing = client.get(missing_url)
            assert missing.status_code == 404
            assert missing.headers.get('cf-cache-status') != 'HIT'
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
