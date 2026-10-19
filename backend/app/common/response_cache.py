"""Bounded stale-while-revalidate cache for public, database-only reads.

No scheduler or provider calls. One background refresh per process; cold readers
coalesce through token-owned Redis leases, or process-local leases during outage.
"""
import hashlib
import inspect
import json
import logging
import math
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import wraps
from typing import get_type_hints

from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.params import Param
from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.redis import get_redis

logger = logging.getLogger(__name__)
LEASE_SECONDS = 15
WAIT_SECONDS = 4
_RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
_PUBLISH = """if redis.call('get',KEYS[1]) == ARGV[1] then
redis.call('set',KEYS[2],ARGV[2],'EX',ARGV[3]); redis.call('del',KEYS[1]); return 1
else return 0 end"""


class ResponseCache:
    def __init__(self, redis_factory=get_redis, max_entries=64, max_bytes=8 * 1024 * 1024):
        self.redis_factory = redis_factory
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._entries = OrderedDict()
        self._size = 0
        self._lock = threading.RLock()
        self._leases = {}
        self._failures = OrderedDict()
        self._background = threading.BoundedSemaphore(1)
        self._executor = None
        self._redis_retry_at = 0.0

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._size = 0
            self._failures.clear()

    def shutdown(self):
        with self._lock:
            executor, self._executor = self._executor, None
        if executor:
            executor.shutdown(wait=True)

    def _redis(self):
        if time.monotonic() < self._redis_retry_at:
            return None
        return self.redis_factory()

    def _redis_error(self, operation, exc):
        self._redis_retry_at = time.monotonic() + 30
        logger.warning("Response cache Redis %s failed error=%s: %s", operation, type(exc).__name__, exc)

    def _remember(self, key, entry):
        raw = json.dumps(entry, separators=(',', ':'), allow_nan=False)
        size = len(raw.encode())
        with self._lock:
            for old, (stored, count) in list(self._entries.items()):
                if stored['discard_at'] <= time.time() or old == key:
                    self._entries.pop(old)
                    self._size -= count
            if size > self.max_bytes:
                return
            self._entries[key] = (entry, size)
            self._size += size
            while len(self._entries) > self.max_entries or self._size > self.max_bytes:
                _, (_, count) = self._entries.popitem(last=False)
                self._size -= count

    def _read(self, key):
        with self._lock:
            found = self._entries.get(key)
            if found and found[0]['discard_at'] > time.time():
                # Refresh stale local copies from Redis so another worker's rebuild is visible.
                if found[0]['fresh_until'] > time.time():
                    return found[0]
            else:
                found = None
        redis = self._redis()
        if redis is not None:
            try:
                raw = redis.get(key)
                if raw:
                    entry = json.loads(raw)
                    if not all(isinstance(entry.get(k), (int, float)) and math.isfinite(entry[k]) for k in ('generated_at', 'fresh_until', 'discard_at')) or 'data' not in entry:
                        raise ValueError('Invalid response cache envelope')
                    if entry['discard_at'] > time.time():
                        self._remember(key, entry)
                        return entry
            except Exception as exc:
                self._redis_error('read', exc)
        return found[0] if found else None

    def _acquire(self, key):
        now = time.monotonic()
        with self._lock:
            self._leases = {k: v for k, v in self._leases.items() if v[1] > now}
            if key in self._leases or len(self._leases) >= 64:
                return None
            token = uuid.uuid4().hex
            self._leases[key] = (token, now + LEASE_SECONDS)
        redis = self._redis()
        if redis is not None:
            try:
                if not redis.set(key + ':lock', token, nx=True, ex=LEASE_SECONDS):
                    self._release_local(key, token)
                    return None
            except Exception as exc:
                self._redis_error('lock', exc)
                redis = None
        return token, redis

    def _release_local(self, key, token):
        with self._lock:
            if self._leases.get(key, (None,))[0] == token:
                self._leases.pop(key, None)

    def _release(self, key, lease):
        token, redis = lease
        try:
            if redis is not None:
                redis.eval(_RELEASE, 1, key + ':lock', token)
        except Exception as exc:
            self._redis_error('unlock', exc)
        finally:
            self._release_local(key, token)

    def _build(self, key, lease, build, fresh, maximum):
        started = time.monotonic()
        token, redis = lease
        try:
            data = jsonable_encoder(build())
            generated = time.time()
            entry = dict(data=data, generated_at=generated, fresh_until=generated + fresh, discard_at=generated + maximum)
            raw = json.dumps(entry, separators=(',', ':'), allow_nan=False)
            with self._lock:
                owned = self._leases.get(key)
                owned = owned is not None and owned[0] == token and owned[1] > time.monotonic()
            if not owned:
                raise RuntimeError('Response cache rebuild exceeded its lease')
            if redis is not None:
                try:
                    if not redis.eval(_PUBLISH, 2, key + ':lock', key, token, raw, maximum):
                        raise RuntimeError('Response cache Redis lease was lost')
                except RuntimeError:
                    raise
                except Exception as exc:
                    self._redis_error('publish', exc)
                    # Cannot prove ownership after a Redis write failure: do not publish locally.
                    raise
            self._remember(key, entry)
            with self._lock:
                self._failures.pop(key, None)
            logger.info('Response cache rebuild key=%s duration_ms=%.1f bytes=%d', key, (time.monotonic() - started) * 1000, len(raw.encode()))
            return entry
        except HTTPException:
            # Validation/not-found responses must not become cached failures.
            raise
        except Exception as exc:
            with self._lock:
                self._failures[key] = time.monotonic() + 30
                self._failures.move_to_end(key)
                while len(self._failures) > 64:
                    self._failures.popitem(last=False)
            logger.error('Response cache rebuild failed key=%s error=%s: %s', key, type(exc).__name__, exc)
            raise
        finally:
            self._release(key, lease)

    def get(self, key, build, *, fresh, maximum):
        entry = self._read(key)
        if entry and entry['fresh_until'] > time.time():
            return entry, 'hit'
        with self._lock:
            failed = self._failures.get(key, 0) > time.monotonic()
        if entry:
            if failed:
                return entry, 'stale-error'
            status = 'stale'
            if self._background.acquire(blocking=False):
                lease = self._acquire(key)
                if lease:
                    def refresh():
                        try:
                            self._build(key, lease, build, fresh, maximum)
                        except Exception as exc:
                            logger.warning('Background refresh unavailable key=%s error=%s: %s', key, type(exc).__name__, exc)
                        finally:
                            self._background.release()
                    with self._lock:
                        if self._executor is None:
                            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='response-cache')
                        self._executor.submit(refresh)
                else:
                    self._background.release()
            else:
                status = 'stale-busy'
            if entry['discard_at'] <= time.time():
                raise HTTPException(503, 'Results are being refreshed', headers={'Retry-After': '2'})
            return entry, status
        if failed:
            raise HTTPException(503, 'Results temporarily unavailable', headers={'Retry-After': '2'})
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            with self._lock:
                if self._failures.get(key, 0) > time.monotonic():
                    raise HTTPException(503, 'Results temporarily unavailable', headers={'Retry-After': '2'})
            lease = self._acquire(key)
            if lease:
                # A rebuild may have completed between our first read and lease acquisition.
                entry = self._read(key)
                if entry and entry['fresh_until'] > time.time():
                    self._release(key, lease)
                    return entry, 'hit'
                try:
                    return self._build(key, lease, build, fresh, maximum), 'miss'
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.warning('Cold cache unavailable key=%s error=%s: %s', key, type(exc).__name__, exc)
                    raise HTTPException(503, 'Results temporarily unavailable', headers={'Retry-After': '2'}) from exc
            if time.monotonic() >= deadline:
                raise HTTPException(503, 'Results are being refreshed', headers={'Retry-After': '2'})
            time.sleep(0.05)
            entry = self._read(key)
            if entry and entry['fresh_until'] > time.time():
                return entry, 'hit'


response_cache = ResponseCache()


def cache_headers(response, entry, status, started):
    response.headers['Cache-Control'] = 'public, no-cache, max-age=0, must-revalidate'
    response.headers['X-Cache-Status'] = status
    for name, field in [('Generated-At', 'generated_at'), ('Expires-At', 'fresh_until')]:
        response.headers['X-Cache-' + name] = datetime.fromtimestamp(entry[field], UTC).isoformat()
    response.headers['Server-Timing'] = f'cache;desc="{status}", app;dur={(time.monotonic() - started) * 1000:.1f}'


def cached_read(namespace, *, fresh, maximum):
    """Decorate a sync DB read after FastAPI resolves/validates its parameters."""
    def decorate(func):
        signature = inspect.signature(func)
        hints = get_type_hints(func)
        adapter = TypeAdapter(hints['return'])
        @wraps(func)
        def wrapped(*args, **kwargs):
            from app.services.image_delivery import image_generation
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            values = {k: (v.default if isinstance(v, Param) else v) for k, v in bound.arguments.items()}
            db = values.pop('db')
            response = values.pop('response')
            bind = db.get_bind()
            # Database identity prevents cache reuse between isolated test databases.
            identity = str(bind.url) if bind.dialect.name != 'sqlite' else str(id(bind))
            from app.config import get_settings
            projection_mode = ("catalog-projection-v1", get_settings().catalog_current_prices_enabled) if namespace in {"search_cards", "get_pokemon_cards", "get_set_stats"} else None
            canonical = json.dumps([namespace, image_generation(), get_settings().ppt_primary_enabled, projection_mode, identity, values], sort_keys=True, default=str)
            key = 'cardboarddex:responses:v2:' + namespace + ':' + hashlib.sha256(canonical.encode()).hexdigest()
            def build():
                with Session(bind, expire_on_commit=False) as session:
                    if bind.dialect.name == 'postgresql':
                        session.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                    return func(**values, db=session, response=Response())
            started = time.monotonic()
            entry, status = response_cache.get(key, build, fresh=fresh, maximum=maximum)
            cache_headers(response, entry, status, started)
            logger.info('Response cache route=%s status=%s duration_ms=%.1f', namespace, status, (time.monotonic() - started) * 1000)
            return adapter.validate_python(entry['data'])
        wrapped.__signature__ = signature.replace(parameters=[p.replace(annotation=hints.get(p.name, p.annotation)) for p in signature.parameters.values()], return_annotation=hints['return'])
        return wrapped
    return decorate
