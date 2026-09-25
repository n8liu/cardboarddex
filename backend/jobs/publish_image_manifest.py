"""Validate stdin and atomically publish a local image manifest with rollback copy."""
import argparse
import json
import logging
from pathlib import Path
import shutil
import sys
import re

CARD_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
IMAGE_PATH = re.compile(r"cards/([A-Za-z0-9_-]{1,64})/[a-f0-9]{64}\.(jpg|png|webp|gif|avif)\Z")


def validate_manifest(data):
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('images'), dict):
        raise ValueError('Unsupported image manifest')
    for cid, key in data['images'].items():
        match = IMAGE_PATH.fullmatch(key) if isinstance(key, str) else None
        if not CARD_ID.fullmatch(cid) or not match or match[1] != cid:
            raise ValueError(f'Invalid image manifest entry: {cid!r}')
    return data['images']


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, sort_keys=True))
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('Image manifest exceeds 32 MiB')
    data = json.loads(raw)
    validate_manifest(data)
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'manifest.json'
    if target.exists():
        try:
            validate_manifest(json.loads(target.read_bytes()))
        except (ValueError, TypeError) as exc:
            logging.warning('Existing manifest is invalid; retaining previous rollback copy: %s: %s', type(exc).__name__, exc)
        else:
            shutil.copyfile(target, directory / 'manifest.previous.json')
    atomic_json(target, data)
    target.chmod(0o644)
    print(f'Published manifest: {len(data["images"])} images')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('Manifest publication failed')
        raise
