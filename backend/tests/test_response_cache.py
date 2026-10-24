import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from redis.exceptions import ConnectionError

from app.common import response_cache as module
from app.common.response_cache import ResponseCache, cache_headers


class MemoryRedis:
    """Atomic Redis subset; integration tests also run against actual Redis."""
    def __init__(self):
        self.values = {}
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            value = self.values.get(key)
            if value and value[1] > time.monotonic():
                return value[0]
            return None

    def set(self, key, value, nx=False, ex=60):
        with self.lock:
            if nx and self.get(key) is not None:
                return False
            self.values[key] = (value, time.monotonic() + int(ex))
            return True

    def eval(self, script, count, *args):
        with self.lock:
            lock, token = args[0], args[count]
            if self.get(lock) != token:
                return 0
            if count == 2:
                self.set(args[1], args[3], ex=args[4])
            del self.values[lock]
            return 1


@pytest.fixture
def cache():
    instance = ResponseCache(redis_factory=lambda: None)
    yield instance
    instance.shutdown()


def seed(cache, key='key', fresh=-1, maximum=100):
    now = time.time()
    entry = dict(data={'value': 'old'}, generated_at=now - 10, fresh_until=now + fresh, discard_at=now + maximum)
    cache._remember(key, entry)
    return entry


def test_fresh_hit_and_valid_empty_result(cache):
    build = Mock(return_value=[])
    first, status = cache.get('key', build, fresh=60, maximum=300)
    assert status == 'miss'
    second, status = cache.get('key', build, fresh=60, maximum=300)
    assert status == 'hit' and second == first
    build.assert_called_once()


def test_stale_returns_before_single_background_refresh(cache):
    old = seed(cache)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def build():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        return 'new'
    try:
        result, status = cache.get('key', build, fresh=60, maximum=300)
        assert result == old and status == 'stale'
        assert entered.wait(1)
        for _ in range(5):
            assert cache.get('key', build, fresh=60, maximum=300)[0] == old
        assert len(calls) == 1
    finally:
        release.set()
        cache.shutdown()
    assert cache.get('key', build, fresh=60, maximum=300)[0]['data'] == 'new'


def test_failure_keeps_timestamp_and_respects_maximum_age(cache):
    old = seed(cache)
    build = Mock(side_effect=RuntimeError('database down'))
    cache.get('key', build, fresh=60, maximum=300)
    cache.shutdown()
    result, status = cache.get('key', build, fresh=60, maximum=300)
    assert result == old and status == 'stale-error'
    build.assert_called_once()
    old['discard_at'] = time.time() - 1
    with pytest.raises(HTTPException) as error:
        cache.get('key', build, fresh=60, maximum=300)
    assert error.value.status_code == 503


def test_cold_concurrent_readers_build_once_across_workers():
    redis = MemoryRedis()
    caches = [ResponseCache(lambda: redis) for _ in range(2)]
    entered, release = threading.Event(), threading.Event()
    count = []
    def build():
        count.append(1)
        entered.set()
        assert release.wait(2)
        return {'ok': True}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(caches[i % 2].get, 'key', build, fresh=60, maximum=300) for i in range(6)]
        assert entered.wait(1)
        release.set()
        results = [f.result(timeout=2) for f in futures]
    assert len(count) == 1
    assert all(r[0] == results[0][0] for r in results)


def test_redis_copy_does_not_restart_freshness():
    redis = MemoryRedis()
    one, two = ResponseCache(lambda: redis), ResponseCache(lambda: redis)
    entry, _ = one.get('key', lambda: 1, fresh=60, maximum=300)
    loaded, status = two.get('key', Mock(side_effect=AssertionError('unexpected rebuild')), fresh=60, maximum=300)
    assert status == 'hit' and loaded == entry


def test_lost_lease_cannot_publish_or_release_new_owner():
    redis = MemoryRedis()
    cache = ResponseCache(lambda: redis)
    def steal():
        redis.set('key:lock', 'new-owner')
        return 'obsolete'
    with pytest.raises(HTTPException):
        cache.get('key', steal, fresh=60, maximum=300)
    assert redis.get('key') is None and redis.get('key:lock') == 'new-owner'
    assert not cache._entries


def test_local_lease_expiry_rejects_obsolete_result(cache):
    def expire():
        token, _ = cache._leases['key']
        cache._leases['key'] = token, time.monotonic() - 1
        return 'obsolete'
    with pytest.raises(HTTPException):
        cache.get('key', expire, fresh=60, maximum=300)
    assert not cache._entries


def test_cold_follower_wait_is_bounded(cache, monkeypatch):
    monkeypatch.setattr(module, 'WAIT_SECONDS', 0)
    cache._leases['key'] = ('owner', time.monotonic() + 10)
    with pytest.raises(HTTPException) as error:
        cache.get('key', Mock(), fresh=60, maximum=300)
    assert error.value.status_code == 503 and error.value.headers['Retry-After'] == '2'


def test_redis_outage_uses_local_cache_and_circuit_breaker():
    redis = Mock()
    redis.get.side_effect = ConnectionError('offline')
    cache = ResponseCache(lambda: redis)
    build = Mock(return_value='ok')
    assert cache.get('key', build, fresh=60, maximum=300)[0]['data'] == 'ok'
    cache.get('key', build, fresh=60, maximum=300)
    build.assert_called_once()
    redis.get.assert_called_once()


def test_memory_byte_and_entry_limits_and_oversized_response():
    cache = ResponseCache(lambda: None, max_entries=2, max_bytes=500)
    for index in range(5):
        cache.get(str(index), lambda: 'small', fresh=60, maximum=300)
    assert len(cache._entries) <= 2 and cache._size <= 500
    result, _ = cache.get('big', lambda: 'x' * 1000, fresh=60, maximum=300)
    assert result['data'] == 'x' * 1000
    assert 'big' not in cache._entries


def test_invalid_requests_are_not_retained(cache):
    build = Mock(side_effect=HTTPException(404, 'not found'))
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            cache.get('key', build, fresh=60, maximum=300)
        assert error.value.status_code == 404
    assert build.call_count == 2 and not cache._failures and not cache._entries


def test_metadata_exposes_original_generation(cache):
    entry = seed(cache)
    response = Response()
    cache_headers(response, entry, 'stale', time.monotonic())
    assert response.headers['X-Cache-Status'] == 'stale'
    assert 'max-age=0' in response.headers['Cache-Control']  # browsers always revalidate
    assert 'cache;desc="stale"' in response.headers['Server-Timing']


def test_rate_limit_redis_does_not_block_event_loop(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from app.common.rate_limiter import check_rate_limit_async
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def redis_eval(*args):
            entered.set()
            await release.wait()
            return 1
        client = Mock()
        client.eval = AsyncMock(side_effect=redis_eval)
        monkeypatch.setattr('app.common.redis.get_async_redis', lambda: client)
        pending = asyncio.create_task(check_rate_limit_async('127.0.0.1'))
        await asyncio.wait_for(entered.wait(), 1)
        # The loop remains responsive while Redis is outstanding.
        await asyncio.sleep(0)
        assert not pending.done()
        release.set()
        assert await pending == (True, 0)
    asyncio.run(scenario())


def test_waiting_cold_readers_do_not_repeat_a_failed_rebuild(cache):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def build():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        raise RuntimeError('database down')
    with ThreadPoolExecutor(max_workers=4) as pool:
        reads = [pool.submit(cache.get, 'key', build, fresh=60, maximum=300) for _ in range(4)]
        assert entered.wait(1)
        release.set()
        for read in reads:
            with pytest.raises(HTTPException):
                read.result(timeout=2)
    assert len(calls) == 1


def test_background_work_does_not_queue_more_keys(cache):
    seed(cache, 'one')
    seed(cache, 'two')
    entered, release = threading.Event(), threading.Event()
    def build():
        entered.set()
        assert release.wait(2)
        return 'new'
    other = Mock()
    try:
        cache.get('one', build, fresh=60, maximum=300)
        assert entered.wait(1)
        _, status = cache.get('two', other, fresh=60, maximum=300)
        assert status == 'stale-busy'
        other.assert_not_called()
    finally:
        release.set()
        cache.shutdown()


def test_cdn_cache_control_tracks_backend_freshness():
    from app.common.response_cache import cdn_cache_control
    entry = dict(generated_at=1000, fresh_until=1300, discard_at=2800)
    assert cdn_cache_control(entry, 'hit', now=1100) == 'public, max-age=0, s-maxage=200, stale-while-revalidate=1500'
    assert cdn_cache_control(entry, 'miss', now=1000) == 'public, max-age=0, s-maxage=300, stale-while-revalidate=1500'
    # Past fresh the edge must come back soon rather than pin old data.
    assert cdn_cache_control(entry, 'stale', now=1400) == 'public, max-age=0, s-maxage=10'
    assert cdn_cache_control(entry, 'stale-error', now=1400) == 'public, max-age=0, s-maxage=10'


def test_unavailable_responses_are_never_cached(cache):
    def boom():
        raise RuntimeError('database down')
    with pytest.raises(HTTPException) as error:
        cache.get('cold', boom, fresh=60, maximum=600)
    assert error.value.status_code == 503
    assert error.value.headers['Cache-Control'] == 'no-store'
