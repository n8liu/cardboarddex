import io
import json
from unittest.mock import Mock

import httpx
import pytest
from botocore.exceptions import ClientError
from jobs import sync_images_to_r2 as job

PNG = b'\x89PNG\r\n\x1a\n' + b'test'


class Storage:
    def __init__(self):
        self.objects = {}
        self.writes = []

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        return {'Body': io.BytesIO(self.objects[Bucket, Key]['Body'])}

    def put_object(self, **kwargs):
        self.writes.append(kwargs)
        self.objects[kwargs['Bucket'], kwargs['Key']] = kwargs

    def head_object(self, Bucket, Key):
        obj = self.objects[Bucket, Key]
        return {'ContentLength': len(obj['Body']), 'Metadata': obj.get('Metadata', {})}

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket):
        return [{'Contents': [{'Size': len(v['Body'])} for (bucket, _), v in self.objects.items() if bucket == Bucket]}]


def inventory(tmp_path, rows):
    path = tmp_path / 'inventory.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    return path


def test_resume_skips_unchanged_and_backfills_bounded_batches(tmp_path):
    storage = Storage()
    rows = [{'id': str(i), 'url': f'https://images.pokemontcg.io/{i}.png'} for i in range(3)]
    path = inventory(tmp_path, rows)
    output = tmp_path / 'manifest.json'
    calls = []
    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, content=PNG, headers={'Content-Type': 'image/png'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = job.sync(storage, client, path, 'images', 'state', output, limit=2)
        assert first['uploaded'] == 2 and first['deferred'] == 1
        assert len(json.loads(output.read_text())['images']) == 2
        second = job.sync(storage, client, path, 'images', 'state', output, limit=2)
        assert second['uploaded'] == 1 and second['skipped'] == 2
        assert len(calls) == 3
        rows[0]['url'] += '?v=2'
        inventory(tmp_path, rows)
        third = job.sync(storage, client, path, 'images', 'state', output)
        assert third['uploaded'] == 1
    images = json.loads(output.read_text())['images']
    assert all(key.endswith('.png') for key in images.values())
    assert all('CacheControl' in obj for obj in storage.writes if obj['Bucket'] == 'images')
    assert not any(obj['Key'] == 'state.json' and obj['Bucket'] == 'images' for obj in storage.writes)


def test_failed_upload_never_published(tmp_path):
    storage = Storage()
    storage.head_object = Mock(side_effect=ValueError('bad checksum'))
    path = inventory(tmp_path, [{'id': 'a', 'url': 'https://images.pokemontcg.io/a.png'}])
    output = tmp_path / 'manifest.json'
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=PNG, headers={'Content-Type': 'image/png'}))) as client:
        result = job.sync(storage, client, path, 'images', 'state', output)
    assert result['failed'] == 1
    assert json.loads(output.read_text())['images'] == {}


def test_block_redirect_before_contacting_unapproved_host():
    calls = []
    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(302, headers={'location': 'http://169.254.169.254/latest/meta-data/'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(ValueError):
        job.download(client, 'https://images.pokemontcg.io/a.png')
    assert calls == ['images.pokemontcg.io']


@pytest.mark.parametrize('headers,content', [({'Content-Type': 'text/html'}, b'<html>'), ({'Content-Type':'image/png'}, b'<html>'), ({'Content-Type':'image/png','Content-Length':str(job.MAX_BYTES+1)}, PNG)])
def test_invalid_or_oversized_download(headers, content):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, headers=headers, content=content))) as client, pytest.raises(ValueError):
        job.download(client, 'https://images.pokemontcg.io/a.png')


def test_storage_cap_defers_download(tmp_path, monkeypatch):
    monkeypatch.setattr(job, 'CAP_BYTES', 1)
    client = Mock()
    result = job.sync(Storage(), client, inventory(tmp_path, [{'id':'a','url':'https://images.pokemontcg.io/a.png'}]), 'images','state',tmp_path/'manifest.json')
    assert result['deferred'] == 1
    assert not client.mock_calls


def test_failure_cooldown_allows_later_cards_to_progress(tmp_path):
    storage = Storage()
    path = inventory(tmp_path, [{'id': str(i), 'url': f'https://images.pokemontcg.io/{i}.png'} for i in range(2)])
    output = tmp_path / 'manifest.json'
    def handler(request):
        if request.url.path == '/0.png':
            return httpx.Response(404)
        return httpx.Response(200, content=PNG, headers={'Content-Type':'image/png'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = job.sync(storage, client, path, 'images', 'state', output, limit=1)
        assert first['failed'] == 1
        second = job.sync(storage, client, path, 'images', 'state', output, limit=1)
        assert second['uploaded'] == 1
        assert '1' in json.loads(output.read_text())['images']
