from unittest.mock import Mock
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time
from types import SimpleNamespace
from anyio import to_thread
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.engine import make_url

from app.common.cache import TTLCache
from app.config import Settings
from app.providers.limiter import DailyRequestLimiter
import app.common.cache as cache_module
import app.common.redis as redis_module
import app.main as main
import app.routers.cards as cards


def test_special_characters_in_database_password_roundtrip():
    password = 'space @:/?#%$!'
    s = Settings(_env_file=None, postgres_host='postgres', postgres_password=password)
    assert make_url(s.effective_database_url).password == password
    with pytest.raises(ValueError, match='POSTGRES_PASSWORD'):
        Settings(_env_file=None, postgres_host='postgres', postgres_password='').effective_database_url


def test_database_pool_settings_reject_unbounded_values():
    with pytest.raises(ValueError):
        Settings(_env_file=None, db_pool_size=0)
    with pytest.raises(ValueError):
        Settings(_env_file=None, db_max_overflow=-1)


def test_api_lifespan_bounds_concurrent_sync_work(monkeypatch):
    monkeypatch.setattr(main.settings, 'api_thread_limit', 2)
    lock = Lock()
    active = peak = 0

    def work():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1

    async def run():
        previous = to_thread.current_default_thread_limiter().total_tokens
        async with main.lifespan(main.app):
            await asyncio.gather(*(to_thread.run_sync(work) for _ in range(10)))
        assert to_thread.current_default_thread_limiter().total_tokens == previous

    asyncio.run(run())
    assert peak == 2


def test_image_releases_database_before_external_io(monkeypatch):
    db = Mock()
    db.get.return_value = SimpleNamespace(image_url='https://images.pokemontcg.io/test.png')
    monkeypatch.setattr(cards, '_get_redis', lambda: None)
    monkeypatch.setattr(cards, 'get_settings', lambda: Settings(_env_file=None, s3_bucket_name=None))

    def download(url):
        db.close.assert_called_once()
        return b'image', 'image/png'

    result = cards.get_card_image('test', db=db, client=SimpleNamespace(get_image=download))
    assert result.body == b'image'


def test_concurrent_images_initialize_one_s3_client(monkeypatch):
    import boto3
    instance = object()
    def create(*args, **kwargs):
        time.sleep(0.02)
        return instance
    factory = Mock(side_effect=create)
    monkeypatch.setattr(cards, '_S3_CLIENT', None)
    monkeypatch.setattr(boto3, 'client', factory)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(cards._get_s3_client, ['us-west-2'] * 8))
    assert all(result is instance for result in results)
    factory.assert_called_once_with('s3', region_name='us-west-2')


def test_cache_evicts_and_expires(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cache_module, 'monotonic', lambda: clock[0])
    cache = TTLCache(max_entries=2, ttl=5)
    cache['a'] = 1
    cache['b'] = 2
    cache['c'] = 3
    assert 'a' not in cache and len(cache) == 2
    clock[0] += 6
    assert cache.get('b') is None and len(cache) == 0


def test_cache_and_durable_redis_use_different_urls(monkeypatch):
    settings = Settings(_env_file=None, redis_url='redis://durable:6379', cache_redis_url='redis://cache:6379')
    factory = Mock()
    monkeypatch.setattr(redis_module, 'get_settings', lambda: settings)
    monkeypatch.setattr(redis_module, '_redis_client', None)
    monkeypatch.setattr(redis_module, '_durable_redis_client', None)
    monkeypatch.setattr(redis_module.Redis, 'from_url', factory)
    redis_module.get_redis()
    redis_module.get_durable_redis()
    assert [c.args[0] for c in factory.call_args_list] == ['redis://cache:6379', 'redis://durable:6379']
    assert all(c.kwargs['socket_timeout'] == 2 for c in factory.call_args_list)


def test_provider_does_not_continue_after_burst_store_failure():
    redis = Mock()
    redis.incr.side_effect = RedisConnectionError('unavailable')
    with pytest.raises(RedisConnectionError):
        DailyRequestLimiter('unused', 'test', 10, redis_client=redis).acquire()
    assert redis.incr.call_count == 1


@pytest.mark.parametrize('failed', ['db', 'durable', 'cache', None])
def test_readiness_requires_all_dependencies(monkeypatch, failed):
    db, durable, cache = Mock(), Mock(), Mock()
    if failed == 'db':
        db.execute.side_effect = RuntimeError('unreachable')
    if failed == 'durable':
        durable.ping.side_effect = RedisConnectionError('unreachable')
    if failed == 'cache':
        cache.ping.side_effect = RedisConnectionError('unreachable')
    monkeypatch.setattr(main, 'get_durable_redis', lambda: durable)
    monkeypatch.setattr(main, '_get_redis', lambda: cache)
    main.app.dependency_overrides[main.get_db] = lambda: db
    try:
        response = TestClient(main.app).get('/ready')
        assert response.status_code == (503 if failed else 200)
        assert response.json() == {'status': 'unavailable' if failed else 'ready'}
    finally:
        main.app.dependency_overrides.pop(main.get_db, None)
