"""Opt-in tests against explicitly supplied disposable PostgreSQL and Redis."""
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import Response
from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.common.response_cache import ResponseCache, cached_read, response_cache
from app.database import Base
from app.models import Card, PriceObservation, Set
from app.services.movers_service import build_rankings


@pytest.fixture
def infrastructure(monkeypatch):
    db_url = os.environ.get('CACHE_TEST_DATABASE_URL')
    redis_url = os.environ.get('CACHE_TEST_REDIS_URL')
    if not db_url or not redis_url:
        pytest.skip('Set CACHE_TEST_DATABASE_URL and CACHE_TEST_REDIS_URL to disposable services')
    schema = 'cache_test_' + uuid.uuid4().hex
    admin = create_engine(db_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(db_url, connect_args={'options': f'-csearch_path={schema}'})
    redis = Redis.from_url(redis_url, decode_responses=True)
    # Namespace decorator entries without deleting any unrelated Redis data.
    class NamespacedRedis:
        def get(self, key): return redis.get(schema + ':' + key)
        def set(self, key, value, **kwargs): return redis.set(schema + ':' + key, value, **kwargs)
        def eval(self, script, count, *args):
            return redis.eval(script, count, *[schema + ':' + k for k in args[:count]], *args[count:])
    client = NamespacedRedis()
    monkeypatch.setattr(response_cache, 'redis_factory', lambda: client)
    monkeypatch.setattr(response_cache, '_redis_retry_at', 0)
    response_cache.clear()
    Base.metadata.create_all(engine)
    try:
        yield engine, client
    finally:
        response_cache.shutdown()
        response_cache.clear()
        for key in redis.scan_iter(schema + ':*'):
            redis.delete(key)
        redis.close()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def test_real_redis_coalesces_workers_and_preserves_timestamps(infrastructure):
    _, redis = infrastructure
    caches = [ResponseCache(lambda: redis), ResponseCache(lambda: redis)]
    calls = []
    gate = threading.Event()
    def build():
        calls.append(1)
        assert gate.wait(2)
        return ['result']
    with ThreadPoolExecutor(max_workers=8) as pool:
        reads = [pool.submit(caches[i % 2].get, 'concurrent', build, fresh=60, maximum=300) for i in range(8)]
        gate.set()
        results = [r.result(4) for r in reads]
    assert len(calls) == 1
    assert all(result[0] == results[0][0] for result in results)


def test_postgres_movers_rankings(infrastructure):
    engine, _ = infrastructure
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add_all([Set(id='en', name='English', release_date=date(2020, 1, 1)),
                    Set(id='jp', name='Japanese', series='Pokemon Japan', release_date=date(2020, 1, 1))])
        db.flush()
        for index, (cid, language, changes, provider, currency, grade) in enumerate([
            ('first', 'en', {'price_change_24h': 30, 'price_change_7d': -10}, 'tcgapi', 'USD', None),
            ('second', 'en', {'price_change_24h': 10}, 'tcgapi', 'USD', None),
            ('missing', 'en', {'price_change_7d': 90}, 'tcgapi', 'USD', None),
            ('jp', 'jp', {'price_change_24h': 99}, 'tcgapi', 'USD', None),
            ('ebay', 'en', {'price_change_24h': 999}, 'ebay', 'USD', None),
            ('eur', 'en', {'price_change_24h': 999}, 'tcgapi', 'EUR', None),
            ('graded', 'en', {'price_change_24h': 999}, 'tcgapi', 'USD', 'PSA'),
        ]):
            db.add(Card(id=cid, name=cid, set_id=language, number=str(index), rarity='Rare'))
            db.flush()
            db.add(PriceObservation(fingerprint=cid, card_id=cid, provider=provider,
                provider_card_id=cid, variant_id='normal', currency=currency, price=10,
                grading_company=grade, observed_at=now - timedelta(days=1), payload=changes))
        db.commit()
        rankings = build_rankings(db, datetime.now(UTC))
        assert [item.card_id for item in rankings['pokemon:24h'].gainers] == ['first', 'second']
        assert [item.card_id for item in rankings['pokemon:7d'].losers] == ['first']
        assert [item.card_id for item in rankings['pokemon:7d'].gainers] == ['missing']
        assert [item.card_id for item in rankings['pokemon-japan:24h'].gainers] == ['jp']


def test_rebuild_session_timeout_and_lease_ownership(infrastructure):
    engine, redis = infrastructure
    @cached_read('timeout-check', fresh=60, maximum=300)
    def read(response: Response, db: Session) -> str:
        return db.scalar(text('SHOW statement_timeout'))
    with Session(engine) as db:
        assert read(response=Response(), db=db) == '5s'
    cache = ResponseCache(lambda: redis)
    lease = cache._acquire('expired')
    redis.set('expired:lock', 'new-owner', ex=15)
    with pytest.raises(RuntimeError, match='lease was lost'):
        cache._build('expired', lease, lambda: 'obsolete', 60, 300)
    assert redis.get('expired') is None and redis.get('expired:lock') == 'new-owner'
