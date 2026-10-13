from unittest.mock import AsyncMock
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Card, MarketHistory, PriceObservation, ProviderCardState, Set
from app.services import home_service as service


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    service._cache.clear()
    with Session(engine) as session:
        yield session
    service._cache.clear()
    engine.dispose()


def add_product(db, cid, change, *, sealed=False, days=0, series=None, date_offset=-30):
    now = datetime.now(UTC)
    db.add(Set(id=cid, name=f'{cid} Set', series=series, release_date=now.date() + timedelta(days=date_offset)))
    db.add(Card(id=cid, name=cid, set_id=cid, number='1', rarity=None if sealed else 'Rare'))
    db.add(PriceObservation(fingerprint=cid, card_id=cid, provider='tcgapi', provider_card_id=cid,
        variant_id='default', printing='Normal', price=100, observed_at=now - timedelta(days=days),
        payload={'price_change_30d': change, 'market_price_as_of': (now.date() - timedelta(days=days)).isoformat()}))
    db.commit()


def test_empty_home_has_no_invented_prices_or_counts(db):
    result = service.build_home_overview(db)
    assert result.products == result.sets == result.price_observations == 0
    assert result.gainer is result.loser is result.sealed is None
    assert result.catalog_updated_at is result.latest_observation_at is None
    assert result.releases == []


def test_highlights_use_latest_signed_changes_explicit_type_and_actual_dates(db):
    add_product(db, 'gain', 20, days=10)
    add_product(db, 'loss', -15)
    add_product(db, 'zero', 0)
    add_product(db, 'unknown', None)
    add_product(db, 'bad', 'NaN')
    add_product(db, 'future', 9000, date_offset=20)
    add_product(db, 'sealed', 30, sealed=False)
    db.add(ProviderCardState(card_id='sealed', provider='tcgapi', match_status='matched', payload={'card': {'product_type': 'Sealed Products'}}))
    # A card without rarity remains a card when explicitly classified.
    add_product(db, 'explicit-card', 5, sealed=True)
    db.add(ProviderCardState(card_id='explicit-card', provider='tcgapi', match_status='matched', payload={'card': {'data': {'product_type': 'Cards'}}}))
    db.add(PriceObservation(fingerprint='old-gain', card_id='gain', provider='tcgapi', provider_card_id='gain',
        variant_id='old', price=50, observed_at=datetime.now(UTC) - timedelta(days=20), payload={'price_change_30d': 1000}))
    db.add(MarketHistory(card_id='gain', printing='Normal', day=datetime.now(UTC).date(), market_price=100, fetched_at=datetime.now(UTC)))
    db.commit()
    result = service.build_home_overview(db)
    assert result.gainer.card_id == 'gain'
    assert result.gainer.change_percent == 20
    assert result.gainer.price_freshness == 'stale'
    assert len(result.gainer.history) == 1  # No fabricated chart points.
    assert result.loser.card_id == 'loss'
    assert result.sealed.card_id == 'sealed'
    assert result.products == result.sets == 8
    assert result.price_observations == 9


def test_releases_keep_both_languages_and_separate_future_dates(db):
    for n in range(10):
        add_product(db, f'en-{n}', 0, date_offset=-n)
    add_product(db, 'jp', 0, series='Pokemon Japan', date_offset=-100)
    add_product(db, 'next', 0, date_offset=1)
    add_product(db, 'far-away', 0, date_offset=200)
    db.add(Set(id='unknown-date', name='Unknown'))
    db.commit()
    result = service.build_home_overview(db)
    assert len([s for s in result.releases if s.game == 'pokemon' and not s.upcoming]) == 8
    assert next(s for s in result.releases if s.id == 'jp').game == 'pokemon-japan'
    assert next(s for s in result.releases if s.id == 'en-0').upcoming is False
    assert next(s for s in result.releases if s.id == 'next').upcoming is True
    assert not {'far-away', 'unknown-date'} & {s.id for s in result.releases}
    assert all(s.card_count == 1 and s.image_url for s in result.releases)


def test_endpoint_is_cached_and_queries_do_not_grow_per_release(db, monkeypatch):
    add_product(db, 'box', 5, sealed=True)
    queries = []
    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)
    event.listen(db.bind, 'before_cursor_execute', record)
    monkeypatch.setattr('app.main.check_rate_limit', AsyncMock(return_value=(True, 0)))
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.get('/home/overview')
            assert response.status_code == 200, response.text
            assert response.json()['sealed']['change_percent'] == 5
            assert response.headers['cache-control'] == 'public, no-cache, max-age=0, must-revalidate'
            count = len(queries)
            assert count <= 12
            assert client.get('/home/overview').json() == response.json()
            assert len(queries) == count
    finally:
        app.dependency_overrides.clear()
        event.remove(db.bind, 'before_cursor_execute', record)
