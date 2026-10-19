"""Bounded off-host image replication. R2 state bucket must remain private."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import httpx

from app.services.image_delivery import CARD_ID, validate_manifest

logger = logging.getLogger(__name__)
from app.services.image_download import (MAX_BYTES, CAP_BYTES, ALLOWED, TYPES, PLACEHOLDER, validate_source, image_extension, download)

def read_state(s3, bucket):
    try:
        state = json.loads(s3.get_object(Bucket=bucket, Key='state.json')['Body'].read())
    except ClientError as exc:
        if exc.response['Error']['Code'] not in ('NoSuchKey', '404'):
            raise
        return {'version': 1, 'cards': {}}
    if state.get('version') != 1 or not isinstance(state.get('cards'), dict):
        raise ValueError('Invalid private synchronization state')
    validate_manifest({'version': 1, 'images': {cid: entry['key'] for cid, entry in state['cards'].items() if entry.get('key')}})
    return state


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, sort_keys=True))
    temp.replace(path)


def sync(s3, client, inventory, bucket, state_bucket, output, limit=500, workers=2, refresh=False):
    if bucket == state_bucket:
        raise ValueError('Synchronization state must use a separate private bucket')
    state = read_state(s3, state_bucket)
    stored_bytes = sum(obj['Size'] for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket) for obj in page.get('Contents', []))
    s3.put_object(Bucket=bucket, Key='placeholder.svg', Body=PLACEHOLDER, ContentType='image/svg+xml', CacheControl='public, max-age=86400')
    counts = {'uploaded': 0, 'skipped': 0, 'failed': 0, 'deferred': 0, 'bytes_uploaded': 0, 'inventory': 0}
    seen = set()
    pending = []

    def transfer(row):
        try:
            content, mime, ext = download(client, row['url'])
            digest = hashlib.sha256(content).hexdigest()
            key = f"cards/{row['id']}/{digest}.{ext}"
            s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType=mime,
                          ContentMD5=base64.b64encode(hashlib.md5(content).digest()).decode(),
                          Metadata={'sha256': digest}, CacheControl='public, max-age=31536000, immutable')
            head = s3.head_object(Bucket=bucket, Key=key)
            if head['ContentLength'] != len(content) or head.get('Metadata', {}).get('sha256') != digest:
                raise ValueError(f'Upload verification failed: {key}')
            return row, {'key': key, 'source': hashlib.sha256(row['url'].encode()).hexdigest(), 'bytes': len(content), 'error': None, 'retry_after': 0}
        except Exception as exc:
            logger.exception('Image synchronization failed card_id=%s url=%s error=%s: %s', row['id'], row['url'], type(exc).__name__, exc)
            return row, {'error': f'{type(exc).__name__}: {exc}'}

    def checkpoint():
        s3.put_object(Bucket=state_bucket, Key='state.json', Body=json.dumps(state).encode(), ContentType='application/json')

    def process_batch(pool):
        nonlocal stored_bytes
        for row, result in pool.map(transfer, pending):
            old = state['cards'].get(row['id'], {})
            if result.get('error'):
                counts['failed'] += 1
                # Preserve a verified older image when refresh fails.
                state['cards'][row['id']] = {**old, 'error': result['error'], 'attempted_source': hashlib.sha256(row['url'].encode()).hexdigest(), 'retry_after': time.time() + 86400}
                # A failed verification may still have written an object.
                stored_bytes += MAX_BYTES
            else:
                counts['uploaded'] += 1
                counts['bytes_uploaded'] += result['bytes']
                stored_bytes += result['bytes']
                state['cards'][row['id']] = result
        checkpoint()
        pending.clear()

    with ThreadPoolExecutor(max_workers=workers) as pool, open(inventory) as source:
        attempted = 0
        for line in source:
            row = json.loads(line)
            if not CARD_ID.fullmatch(row['id']) or row['id'] in seen:
                raise ValueError(f'Invalid or duplicate card ID: {row["id"]}')
            seen.add(row['id'])
            counts['inventory'] += 1
            old = state['cards'].get(row['id'], {})
            fingerprint = hashlib.sha256(row['url'].encode()).hexdigest()
            if not refresh and old.get('attempted_source') == fingerprint and old.get('retry_after', 0) > time.time():
                counts['deferred'] += 1
                continue
            if not refresh and old.get('key') and old.get('source') == fingerprint:
                counts['skipped'] += 1
                continue
            # Reserve worst-case bytes for all outstanding downloads.
            if attempted >= limit or stored_bytes + (len(pending) + 1) * MAX_BYTES > CAP_BYTES:
                counts['deferred'] += 1
                continue
            attempted += 1
            pending.append(row)
            if len(pending) >= workers:
                process_batch(pool)
        if pending:
            process_batch(pool)
    checkpoint()
    manifest = {'version': 1, 'images': {cid: entry['key'] for cid, entry in state['cards'].items() if cid in seen and entry.get('key')}}
    validate_manifest(manifest)
    atomic_json(output, manifest)
    counts['stored_bytes_upper_bound'] = stored_bytes
    logger.info('Image sync summary: %s', counts)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--output', default='manifest.json')
    parser.add_argument('--limit', type=int, default=500)
    parser.add_argument('--workers', type=int, choices=(1, 2), default=2)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error('--limit must be between 1 and 500')
    logging.basicConfig(level=logging.INFO)
    started = time.monotonic()
    s3 = boto3.client('s3', endpoint_url=os.environ['R2_ENDPOINT_URL'], region_name='auto',
                      aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'], aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
                      config=Config(max_pool_connections=2, retries={'max_attempts': 3}, connect_timeout=5, read_timeout=30))
    with httpx.Client(timeout=httpx.Timeout(15, connect=5), limits=httpx.Limits(max_connections=2, max_keepalive_connections=2)) as client:
        result = sync(s3, client, args.inventory, os.environ['R2_BUCKET'], os.environ['R2_STATE_BUCKET'], args.output, args.limit, args.workers, args.refresh)
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    atomic_json(Path(args.output).with_name('summary.json'), result)
    print(json.dumps(result))
    if result['failed']:
        raise SystemExit(2)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logger.exception('R2 synchronization failed')
        raise
