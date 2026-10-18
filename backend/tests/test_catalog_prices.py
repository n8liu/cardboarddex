from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import Base
from app.models import Card, Set, PriceObservation as O, PPTProduct, PPTCurrentQuote as Q, CatalogPriceCandidate as C, CatalogPriceProjectionState as State
from app.routers.catalog import search_cards
from app.services.catalog_service import query_pokemon_cards, get_set_statistics
from app.services.catalog_prices import backfill_batch, candidate_join, commit_prices, refresh_candidates, require_ready, verify_projection
from app.services.price_sources import catalog_price_join
from fastapi import Response


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(get_settings(), "catalog_current_prices_enabled", False)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(Set(id="s", name="Set", series="Pokemon"))
        db.add(Set(id="jp", name="Japanese", series="Pokemon Japan"))
        db.add_all([Card(id="c", name="Pikachu", set_id="s", rarity="Rare", number="1"),
                    Card(id="empty", name="Unpriced", set_id="s", rarity="Rare", number="2"),
                    Card(id="jp", name="Pikachu", set_id="jp", rarity=None, number="3")])
        db.add(PPTProduct(id="p", provider_id="p", card_id="c", segment="english:cards", status="matched", metadata_payload={}, quotes=[]))
        db.commit()
        yield db
    engine.dispose()


def observation(db, fingerprint, *, provider="tcgapi", price=10, days=0, card="c", primary=True, dated=True):
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(days=days)
    row = O(card_id=card, provider=provider, provider_card_id="p", variant_id=fingerprint,
            fingerprint=fingerprint, price=Decimal(str(price)), currency="USD", observed_at=now,
            provider_updated_at=now if dated else None, payload={"primary": primary})
    db.add(row)
    db.flush()
    if provider == "pokemonpricetracker":
        db.add(Q(fingerprint=fingerprint, product_id="p", price_date=now.date()))
        db.flush()
    return row


def selected(db, projection, primary, broad=True):
    get_settings().catalog_current_prices_enabled = projection
    get_settings().ppt_primary_enabled = primary
    cols, rows, on = catalog_price_join(broad=broad)
    return db.execute(select(Card.id, cols.price, cols.currency, cols.provider_updated_at).outerjoin(rows, on).order_by(Card.id)).all()


@pytest.mark.parametrize("primary", [False, True])
@pytest.mark.parametrize("broad", [False, True])
def test_selection_parity(db, monkeypatch, primary, broad):
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", primary)
    observation(db, "old", price=1000, days=10)
    observation(db, "new", price=0)
    observation(db, "tie", price=20)
    observation(db, "null-date", price=9999, dated=False)
    observation(db, "ppt-old", provider="pokemonpricetracker", price=2, days=8)
    observation(db, "ppt-current", provider="pokemonpricetracker", price=4)
    observation(db, "ppt-not-primary", provider="pokemonpricetracker", price=999, primary=False)
    refresh_candidates(db, ["c", "empty", "jp"])
    assert selected(db, False, primary, broad) == selected(db, True, primary, broad)
    assert len(list(db.scalars(select(C)))) == 3
    assert not verify_projection(db)["mismatched_cards"]


def test_expiration_without_worker_and_empty_snapshot(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", True)
    observation(db, "legacy", price=10)
    observation(db, "ppt", provider="pokemonpricetracker", price=25, days=7)
    refresh_candidates(db, ["c"])
    def price(day):
        cols, rows, on = candidate_join(as_of=day)
        return db.scalar(select(cols.price).select_from(Card).outerjoin(rows, on).where(Card.id == "c"))
    assert price(datetime.now(UTC).date()) == 25
    assert price(datetime.now(UTC).date() + timedelta(days=1)) == 10
    db.execute(delete(Q))
    refresh_candidates(db, ["c"])
    assert price(datetime.now(UTC).date()) == 10
    assert len(list(db.scalars(select(C)))) == 1


def test_backfill_resume_verification_and_rollback(db, monkeypatch):
    from app.services import catalog_prices
    observation(db, "old", price=10)
    db.commit()
    monkeypatch.setattr(catalog_prices, "BATCH_SIZE", 1)
    assert backfill_batch(db) == 1
    assert not db.get(State, 1).complete
    with pytest.raises(RuntimeError): require_ready(db)
    while not db.get(State, 1).complete: backfill_batch(db)
    assert verify_projection(db)["mismatched_cards"] == []
    with pytest.raises(RuntimeError): require_ready(db)
    db.get(State, 1).verified_at = datetime.now(UTC)
    db.commit()
    require_ready(db)
    observation(db, "new", price=20)
    refresh_candidates(db, ["c"])
    db.rollback()
    assert db.scalar(select(C.price)) == 10
    db.execute(delete(C))
    assert verify_projection(db)["mismatched_cards"] == ["c"]


@pytest.mark.parametrize("primary", [False, True])
def test_endpoint_parity(db, monkeypatch, primary):
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", primary)
    observation(db, "a", price=10)
    observation(db, "b", price=30, days=1)
    observation(db, "ppt", provider="pokemonpricetracker", price=20)
    observation(db, "j", price=5, card="jp")
    refresh_candidates(db, ["c", "jp", "empty"])
    for sort in ["price_asc", "price_desc", "name", "set", "number_asc", "number_desc"]:
        for options in [{}, {"q": "Pikachu"}, {"set_id": "s"}, {"game": "pokemon-japan", "hide_sealed": False}, {"min_price": 0, "max_price": 10}]:
            kwargs = dict(q="", sort_by=sort, limit=60, offset=0, set_id=None, game="all", hide_sealed=False,
                          sealed_only=False, min_price=None, max_price=None, db=db, response=Response()) | options
            get_settings().catalog_current_prices_enabled = False
            before = search_cards.__wrapped__(**kwargs)
            get_settings().catalog_current_prices_enabled = True
            assert search_cards.__wrapped__(**kwargs) == before
    for projection in [False, True]:
        get_settings().catalog_current_prices_enabled = projection
        result = (query_pokemon_cards(db, "Pikachu"), get_set_statistics(db, "s", hide_sealed=False, use_cache=False))
        if not projection: old = result
        else: assert result == old


def test_tcg_commit_tracks_autoflushed_observations(db):
    from jobs.collect_prices import _observation
    for card_id in ["c", "jp"]:
        _observation(db, card_id=card_id, provider="tcgapi", provider_card_id=card_id, variant_id="v", price=10)
        db.flush()
    commit_prices(db)
    assert set(db.scalars(select(C.card_id))) == {"c", "jp"}
    assert "catalog_price_cards" not in db.info


def test_projection_mode_uses_separate_response_cache(db, monkeypatch):
    from app.common.response_cache import response_cache
    monkeypatch.setattr(response_cache, 'redis_factory', lambda: None)
    response_cache.clear()
    observation(db, "old", price=10)
    refresh_candidates(db, ["c"])
    db.commit()
    kwargs = dict(response=Response(), db=db, q="", sort_by="price_desc", limit=60, offset=0,
                  set_id=None, game="all", hide_sealed=False, sealed_only=False, min_price=None, max_price=None)
    get_settings().catalog_current_prices_enabled = False
    old = search_cards(**kwargs)
    # Deliberately divergent fixture proves cache isolation (real ingestion is atomic).
    candidate = db.scalar(select(C))
    candidate.price = 20
    db.commit()
    get_settings().catalog_current_prices_enabled = True
    try:
        new = search_cards(**kwargs)
        assert old[0].market_price == 10 and new[0].market_price == 20
    finally:
        response_cache.clear()


def test_startup_rejects_unverified_projection(db, monkeypatch):
    from contextlib import nullcontext
    from fastapi.testclient import TestClient
    from app.main import app
    from app import database
    from unittest.mock import Mock
    monkeypatch.setattr(get_settings(), "catalog_current_prices_enabled", True)
    monkeypatch.setattr(database, "SessionLocal", lambda: nullcontext(Mock(get=Mock(return_value=None))))
    with pytest.raises(RuntimeError, match="completed, verified"):
        with TestClient(app): pass
