from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Card, Set, PriceObservation, ListingAssessment
from app.routers.market import get_live_feed, get_live_updates
from app.services import live_stats
from app.services.listing_quality import eligible_observation, MATCHER_VERSION


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="s", name="Base"))
        session.add(Card(id="c", name="Pikachu", number="25", set_id="s"))
        for i, provider in enumerate(["tcgapi", "tcgapi", "pokemonpricetracker", "ebay", "ebay"]):
            session.add(PriceObservation(card_id="c", provider=provider, provider_card_id=str(i),
                fingerprint=str(i), variant_id=str(i), price=10, currency="USD", observed_at=datetime(2026, 10, 1, tzinfo=UTC),
                grading_company="PSA" if i == 3 else None, grade=10 if i == 3 else None,
                payload={"assessment_fingerprint": "match" if i == 3 else "reject"}))
        session.add(ListingAssessment(card_id="c", item_id="3", fingerprint="match", version=MATCHER_VERSION,
                                      status="matched", text_status="matched", image_status="matched", evidence={}, source={}))
        session.commit()
        yield session
    engine.dispose()


def feed(db, **kwargs):
    return get_live_feed(Response(), db=db, **dict(provider="all", grade_filter="all", set_id=None,
                         q=None, page=1, per_page=2, **kwargs))


def test_feed_no_aggregates_and_pagination(db, monkeypatch):
    monkeypatch.setattr(live_stats.get_settings(), "ppt_primary_enabled", False)
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda c, cu, sql, p, ctx, many: statements.append(sql))
    first = feed(db)
    second = get_live_feed(Response(), "all", "all", None, None, 2, 2, db)
    assert first.has_more and not second.has_more
    assert len(first.items) == 2 and len(second.items) == 1
    assert not set(i.id for i in first.items) & set(i.id for i in second.items)
    assert not any("count(" in sql.lower() or "sum(" in sql.lower() for sql in statements)
    assert first.items[0].provider == "ebay"  # tied times use descending IDs


@pytest.mark.parametrize("primary", [False, True])
def test_snapshot_matches_feed_eligibility(db, monkeypatch, primary):
    monkeypatch.setattr(live_stats.get_settings(), "ppt_primary_enabled", primary)
    snapshot = live_stats.calculate_snapshot(db)
    expected = db.scalar(select(func.count()).select_from(PriceObservation).where(eligible_observation()))
    assert snapshot.total_items == expected == (4 if primary else 3)
    assert snapshot.total_ebay_updates == snapshot.graded_updates_count == 1
    assert snapshot.total_tcg_updates == 2
    assert snapshot.total_ppt_updates == int(primary)
    assessment = db.scalar(select(ListingAssessment))
    assessment.version = "old"
    db.flush()
    assert live_stats.calculate_snapshot(db).total_ebay_updates == 0


@pytest.mark.parametrize("provider,grade,q,expected", [
    ("tcgapi", "raw", None, 2), ("all", "psa10", None, 1),
    ("all", "all", "missing", 0), ("all", "raw", "Pikachu", 2),
])
def test_filters_and_legacy_compatibility(db, monkeypatch, provider, grade, q, expected):
    monkeypatch.setattr(live_stats.get_settings(), "ppt_primary_enabled", False)
    monkeypatch.setattr("app.routers.market._get_redis", lambda: None)
    response = Response()
    new = get_live_feed(response, provider, grade, None, q, 1, 100, db)
    legacy = get_live_updates(Response(), provider, grade, None, q, 1, 100, db)
    assert [i.id for i in new.items] == [i.id for i in legacy.items]
    assert len(new.items) == expected
    assert legacy.total_items == expected
    assert not new.has_more
    assert response.headers["Cache-Control"] == "no-store"


def test_unfiltered_first_page_shares_one_query(db, monkeypatch):
    from app.common.response_cache import response_cache
    monkeypatch.setattr(live_stats.get_settings(), "ppt_primary_enabled", False)
    monkeypatch.setattr(live_stats.get_settings(), "live_feed_shared_cache_enabled", True)
    monkeypatch.setattr(response_cache, "redis_factory", lambda: None)
    response_cache.clear()
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute",
                 lambda c, cu, sql, p, ctx, many: statements.append(sql) if "price_observations" in sql else None)
    try:
        first_response, second_response = Response(), Response()
        first = get_live_feed(first_response, "all", "all", None, None, 1, 2, db)
        second = get_live_feed(second_response, "all", "all", None, None, 1, 2, db)
        assert [i.id for i in first.items] == [i.id for i in second.items]
        assert len(statements) == 1
        assert second_response.headers["X-Cache-Status"] == "hit"
        assert first_response.headers["Cache-Control"] == second_response.headers["Cache-Control"] == "no-store"
        # Searched and later pages stay live.
        get_live_feed(Response(), "all", "all", None, "Pikachu", 1, 2, db)
        get_live_feed(Response(), "all", "all", None, None, 2, 2, db)
        assert len(statements) == 3
    finally:
        response_cache.clear()


@pytest.mark.parametrize("age,stale,available",[(0, False, True), (61, True, True), (1801, True, True), (86399, True, True), (86401, True, False)])
def test_snapshot_age(db, monkeypatch, age, stale, available):
    snapshot = live_stats.calculate_snapshot(db)
    snapshot.generated_at = datetime.now(UTC) - timedelta(seconds=age)
    monkeypatch.setattr(live_stats, "get_redis", lambda: Mock(get=Mock(return_value=snapshot.model_dump_json())))
    if available:
        assert live_stats.read_snapshot().is_stale == stale
    else:
        with pytest.raises(HTTPException) as error:
            live_stats.read_snapshot()
        assert error.value.status_code == 503
        assert error.value.headers["Retry-After"] == "60"


def test_read_missing_corrupt_or_redis_failure_never_builds(monkeypatch):
    build = Mock(side_effect=AssertionError("must not build"))
    monkeypatch.setattr(live_stats, "calculate_snapshot", build)
    for redis in [None, Mock(get=Mock(return_value=None)), Mock(get=Mock(return_value="bad")),
                  Mock(get=Mock(side_effect=ConnectionError("offline")))]:
        monkeypatch.setattr(live_stats, "get_redis", lambda: redis)
        with pytest.raises(HTTPException):
            live_stats.read_snapshot()
    build.assert_not_called()


def test_key_isolates_modes_and_matcher(monkeypatch):
    monkeypatch.setattr(live_stats.get_settings(), "ppt_primary_enabled", False)
    original = live_stats.snapshot_key()
    monkeypatch.setattr(live_stats.get_settings(), "ppt_primary_enabled", True)
    assert original != live_stats.snapshot_key()
    other = live_stats.snapshot_key()
    monkeypatch.setattr(live_stats.listing_quality, "MATCHER_VERSION", "next")
    assert other != live_stats.snapshot_key()


def test_refresh_lock_and_failure_preserve_snapshot(db, monkeypatch):
    redis = Mock(set=Mock(return_value=False))
    monkeypatch.setattr(live_stats, "get_redis", lambda: redis)
    sessions = Mock()
    monkeypatch.setattr(live_stats, "SessionLocal", sessions)
    assert live_stats.refresh_snapshot() is False
    sessions.assert_not_called()
    redis.eval.assert_not_called()
    redis.set.return_value = True
    sessions.side_effect = RuntimeError("database unavailable")
    assert live_stats.refresh_snapshot() is False
    assert redis.eval.call_count == 1  # release only; no overwrite
    assert redis.eval.call_args.args[0] == live_stats._RELEASE


def test_refresh_publishes_atomically_and_rejects_lost_lease(db, monkeypatch):
    redis = Mock(set=Mock(return_value=True), eval=Mock(return_value=1), get=Mock(return_value=None))
    monkeypatch.setattr(live_stats, "get_redis", lambda: redis)
    from contextlib import nullcontext
    monkeypatch.setattr(live_stats, "SessionLocal", lambda: nullcontext(db))
    assert live_stats.refresh_snapshot() is True
    publish = redis.eval.call_args_list[0].args
    assert publish[0] == live_stats._PUBLISH
    assert publish[1] == 2 and publish[-1] == live_stats.RETAIN_SECONDS
    assert '"total_items"' in publish[-2]
    redis.eval.return_value = 0
    assert live_stats.refresh_snapshot() is False


@pytest.mark.parametrize("primary", [False, True])
def test_cached_legacy_counts_match_full_recount(db, monkeypatch, primary):
    monkeypatch.setattr(live_stats.get_settings(), "ppt_primary_enabled", primary)
    legacy = live_stats.legacy_counts(db)
    assert legacy == [2, 0, 2, 0, 0]
    counts = lambda snapshot: snapshot.model_dump(exclude={"generated_at"})
    assert counts(live_stats.calculate_snapshot(db, legacy)) == counts(live_stats.calculate_snapshot(db))


def test_refresh_counts_legacy_once_then_reads_cache(db, monkeypatch):
    import fakeredis
    from contextlib import nullcontext
    redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(live_stats, "get_redis", lambda: redis)
    monkeypatch.setattr(live_stats, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(live_stats, "_PUBLISH", "redis.call('set', KEYS[2], ARGV[2]) return 1")
    counted = Mock(wraps=live_stats.legacy_counts)
    monkeypatch.setattr(live_stats, "legacy_counts", counted)
    assert live_stats.refresh_snapshot() and live_stats.refresh_snapshot()
    assert counted.call_count == 1
    assert 0 < redis.ttl(live_stats.LEGACY_KEY) <= live_stats.LEGACY_SECONDS
    redis.set(live_stats.LEGACY_KEY, "[100, 0, 100, 0, 0]")
    assert live_stats.refresh_snapshot()
    assert live_stats.read_snapshot().total_tcg_updates == 100  # cached legacy, not a recount


def test_public_routes_and_cold_stats_contract(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.routers.market import router
    app = FastAPI()
    app.include_router(router)
    db = Mock()
    db.get_bind.return_value.dialect.name = "sqlite"
    db.execute.return_value.all.return_value = []
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(live_stats, "get_redis", lambda: None)
    with TestClient(app) as client:
        stats = client.get("/cards/live-updates/stats")
        assert stats.status_code == 503
        assert stats.headers["retry-after"] == "60"
        assert stats.headers["cache-control"] == "no-store"
        db.execute.assert_not_called()
        feed_response = client.get("/cards/live-updates/feed")
        assert feed_response.status_code == 200
        assert feed_response.headers["cache-control"] == "no-store"
        assert feed_response.json()["has_more"] is False
        assert "total_items" not in feed_response.json()
        assert client.get("/cards/live-updates/feed?provider=invalid").status_code == 422
        assert client.get("/cards/live-updates/feed?per_page=101").status_code == 422


@pytest.mark.parametrize("age,header", [(0, "public, max-age=0, s-maxage=30"), (120, "public, max-age=0, s-maxage=10")])
def test_stats_route_is_edge_cacheable_and_shorter_when_stale(db, monkeypatch, age, header):
    from fastapi import Response
    from app.routers.market import get_live_stats
    snapshot = live_stats.calculate_snapshot(db)
    snapshot.generated_at = datetime.now(UTC) - timedelta(seconds=age)
    monkeypatch.setattr(live_stats, "get_redis", lambda: Mock(get=Mock(return_value=snapshot.model_dump_json())))
    response = Response()
    get_live_stats(response)
    assert response.headers["Cache-Control"] == header
