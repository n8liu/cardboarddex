import hashlib
import json
from unittest.mock import Mock

import pytest

from app.services import image_delivery as delivery
from app.routers.cards import get_card_image
from jobs.publish_image_manifest import validate_manifest


@pytest.fixture
def cdn(monkeypatch, tmp_path):
    settings = Mock(image_cdn_enabled=True, image_cdn_base_url='https://images.cardboarddex.app', image_manifest_path=str(tmp_path / 'manifest.json'))
    monkeypatch.setattr(delivery, 'get_settings', lambda: settings)
    monkeypatch.setattr(delivery, '_path', None)
    monkeypatch.setattr(delivery, '_checked', 0)
    return settings


def write_manifest(settings, images):
    from pathlib import Path
    Path(settings.image_manifest_path).write_text(json.dumps({'version': 1, 'images': images}))


def test_atomic_reload_retains_previous_on_corruption(cdn, monkeypatch):
    key = f'cards/a/{hashlib.sha256(b"a").hexdigest()}.jpg'
    write_manifest(cdn, {'a': key})
    assert delivery.card_image_url('a').endswith(key)
    initial = delivery.image_generation()
    assert delivery.card_image_url('missing').endswith('/placeholder.svg')
    write_manifest(cdn, {'a': '../bad.jpg'})
    monkeypatch.setattr(delivery, '_checked', 0)
    assert delivery.card_image_url('a').endswith(key)
    assert delivery.image_generation() == initial
    key2 = f'cards/a/{hashlib.sha256(b"b").hexdigest()}.png'
    write_manifest(cdn, {'a': key2})
    monkeypatch.setattr(delivery, '_checked', 0)
    assert delivery.card_image_url('a').endswith(key2)
    assert delivery.image_generation() != initial


def test_cdn_compatibility_uses_no_database_or_network(cdn, monkeypatch):
    monkeypatch.setattr('app.routers.cards.get_settings', lambda: cdn)
    db, client = Mock(), Mock()
    response = get_card_image('a', db=db, client=client)
    assert response.status_code == 307
    assert response.headers['location'] == 'https://images.cardboarddex.app/placeholder.svg'
    assert 'immutable' not in response.headers['cache-control']
    assert not db.mock_calls and not client.mock_calls


@pytest.mark.parametrize('images', [{'a': 'https://evil.invalid/image.jpg'}, {'a': 'cards/b/' + 'f'*64 + '.jpg'}, {'../a': 'cards/a/' + 'f'*64 + '.png'}])
def test_reject_unsafe_manifest(images):
    with pytest.raises(ValueError):
        validate_manifest({'version': 1, 'images': images})


def test_disabled_preserves_local_development(cdn):
    cdn.image_cdn_enabled = False
    assert delivery.card_image_url('a') == '/cards/a/image'
    assert delivery.image_generation() == 'legacy'


def test_publish_rejects_corruption_and_preserves_rollback(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    script = Path(__file__).parents[1] / 'jobs/publish_image_manifest.py'
    directory = tmp_path / 'published'
    def publish(data):
        return subprocess.run([sys.executable, str(script), str(directory)], input=json.dumps(data), text=True, capture_output=True)
    first = {'version':1,'images':{'a':'cards/a/'+'a'*64+'.png'}}
    second = {'version':1,'images':{'a':'cards/a/'+'b'*64+'.png'}}
    assert publish(first).returncode == 0
    assert publish(second).returncode == 0
    assert json.loads((directory/'manifest.previous.json').read_text()) == first
    assert publish({'version':1,'images':{'a':'../escape'}}).returncode != 0
    assert json.loads((directory/'manifest.json').read_text()) == second
