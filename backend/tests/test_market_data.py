from unittest.mock import AsyncMock
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models import Card, Set, MarketHistory, CatalogSnapshot, ProviderCardState, PriceObservation
from app.services import market_data_service as service
from app.services import sealed_service
from app.tcgapi.client import TCGAPIClient, DEFAULT_BASE_URL
from app.services.legacy_records import import_legacy_history, import_legacy_catalog_snapshot
from jobs.collect_prices import _state


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(sealed_service, "get_redis", lambda: None)
    sealed_service._SEALED_SIGNALS_LOCAL_FALLBACK.clear()
    with Session(engine) as session:
        session.add(Set(id="set", name="Test", release_date=date(2025, 1, 1)))
        session.add(Card(id="box", name="Booster Box", set_id="set", number="1"))
        session.commit()
        yield session
    sealed_service._SEALED_SIGNALS_LOCAL_FALLBACK.clear()
    engine.dispose()


def test_legacy_http_client_is_retired():
    from app.tcgapi.client import TCGAPIConfigurationError
    with pytest.raises(TCGAPIConfigurationError, match="retired"):
        TCGAPIClient(api_key="test")


def test_idempotent_history_preserves_zero_null_and_corrections(db):
    today = datetime.now(UTC).date().isoformat()
    client = Mock()
    client.get_history.return_value = {"data": [
        {"date": today, "printing": "Normal", "market_price": 100, "sales_volume": 0},
        {"date": today, "printing": "Foil", "market_price": 110, "sales_volume": None},
    ]}
    card = db.get(Card, "box")
    import_legacy_history(db, card, client.get_history())
    import_legacy_history(db, card, client.get_history())
    assert db.scalar(select(func.count()).select_from(MarketHistory)) == 2
    assert service.sales_activity(db)["total_sales"] == 0
    client.get_history.return_value["data"][0]["sales_volume"] = 8
    import_legacy_history(db, card, client.get_history())
    assert service.sales_activity(db)["total_sales"] == 8
    assert db.scalar(select(func.count()).select_from(MarketHistory)) == 2
    client.get_history.return_value = {"data": [{"date": today, "market_price": "NaN"}]}
    with pytest.raises(ValueError):
        import_legacy_history(db, card, client.get_history())
    db.rollback()
    assert service.sales_activity(db)["total_sales"] == 8


def test_history_exact_baseline_and_staleness(db):
    today = datetime.now(UTC).date()
    for ago, price in [(90, 100), (30, 150), (0, 200)]:
        db.add(MarketHistory(card_id="box", printing="Normal", day=today - timedelta(days=ago), market_price=price, fetched_at=datetime.now(UTC)))
    db.commit()
    history = service.history_series(db, "box", 90)
    assert history["return_percent"] == 100
    assert service.history_series(db, "box", 365)["return_percent"] is None
    assert service.historical_returns(db, ["box"], 90)[("box", "Normal")] == 100
    db.delete(db.get(MarketHistory, ("box", "Normal", today)))
    db.commit()
    assert service.history_series(db, "box", 30)["return_percent"] is None
    assert service.freshness({"market_price_as_of": (today - timedelta(days=20)).isoformat()})["price_freshness"] == "stale"
    assert service.freshness({})["price_freshness"] == "unknown"


@pytest.mark.parametrize("nested", [False, True])
def test_explicit_product_type_overrides_missing_rarity(db, nested):
    card_data = {"product_type": "Cards"}
    state = ProviderCardState(card_id="box", provider="tcgapi", match_status="matched", payload={"card": {"data": card_data} if nested else card_data})
    db.add(state)
    db.add(PriceObservation(card_id="box", provider="tcgapi", provider_card_id="box", variant_id="normal", printing="Normal", fingerprint="box", price=100, payload={"price_change_30d": 5}))
    db.commit()
    assert sealed_service.calculate_sealed_signals(db).total_items == 0
    state.payload = {"card": {"product_type": "Sealed Products"}}
    db.get(Card, "box").rarity = "Provider supplied rarity"
    db.commit()
    sealed_service._SEALED_SIGNALS_LOCAL_FALLBACK.clear()
    result = sealed_service.calculate_sealed_signals(db)
    assert result.total_items == 1
    assert result.items[0].price_freshness == "unknown"
    _state(db, "box", "tcgapi", "matched", {"prices": {"data": []}})
    assert state.payload["card"]["product_type"] == "Sealed Products"


def test_catalog_snapshot_counts_missing_and_failed_refresh(db):
    client = Mock()
    client.get_game.return_value = {"data": {"set_count": 2, "card_count": 10}}
    client.iter_game_sets.return_value = iter([
        {"id": "set", "name": "Imported", "card_count": 4, "release_date": "2025-01-01"},
        {"id": "new", "name": "New set", "card_count": 6, "release_date": "2026-10-01"},
    ])
    import_legacy_catalog_snapshot(db, "pokemon", client.get_game()["data"], list(client.iter_game_sets()))
    result = service.legacy_catalog_coverage(db)["games"][0]
    assert result["local_set_count"] == 1
    assert result["local_card_count"] == 1
    assert result["missing_sets"][0]["id"] == "new"
    assert result["latest_sets"][0]["id"] == "new"
    client.iter_game_sets.side_effect = ValueError("Failed page 2")
    with pytest.raises(ValueError):
        import_legacy_catalog_snapshot(db, "pokemon", client.get_game()["data"], list(client.iter_game_sets()))
    db.rollback()
    assert db.get(CatalogSnapshot, "pokemon").payload["game"]["set_count"] == 2


def test_public_history_and_sales_api(db, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.main.check_rate_limit", AsyncMock(return_value=(True, 0)))
    try:
        with TestClient(app) as client:
            response = client.get("/cards/box/market-history?days=90")
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "not_synced"
            assert client.get("/cards/missing/market-history").status_code == 404
            assert client.get("/cards/box/market-history?days=999").status_code == 422
            assert client.get("/cards/sealed-signals?period=90&era=newer").status_code == 200
            sales = client.get("/market/sales-activity?days=7")
            assert sales.status_code == 200, sales.text
            assert sales.json()["total_sales"] is None
            assert client.get("/admin/catalog-health").status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("era,age", [("newer", 30), ("older", 1500)])
def test_sealed_language_filters_before_pagination_and_isolates_cache(db, monkeypatch, era, age):
    today = datetime.now(UTC)
    for cid, series, growth in [("jp", "Pokemon Japan", 50), ("en", "Scarlet & Violet", 20), ("legacy", None, 10)]:
        db.add(Set(id=cid, name=cid, series=series, release_date=today.date() - timedelta(days=age)))
        db.add(Card(id=cid, name=f"{cid} Booster Box", set_id=cid, number="BB"))
        db.add(PriceObservation(fingerprint=cid, card_id=cid, provider="tcgapi", provider_card_id=cid,
            variant_id="default", price=100, observed_at=today,
            payload={"market_price": 100, "price_change_30d": growth}))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.main.check_rate_limit", AsyncMock(return_value=(True, 0)))
    try:
        with TestClient(app) as client:
            path = f"/cards/sealed-signals?era={era}&sort_by=momentum_desc&per_page=1"
            for game, expected, total in [("all", "jp", 3), ("pokemon", "en", 2), ("pokemon-japan", "jp", 1), ("pokemon", "en", 2)]:
                response = client.get(f"{path}&game={game}")
                assert response.status_code == 200, response.text
                data = response.json()
                assert data["total_items"] == total
                assert data["total_pages"] == total
                assert data["items"][0]["card_id"] == expected
            assert client.get(f"{path}&game=pokemon&page=2").json()["items"][0]["card_id"] == "legacy"
            assert client.get(path).json()["total_items"] == 3
            assert client.get(f"{path}&game=invalid").status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("projection", [False, True])
def test_movers_and_sealed_pages_are_disjoint(db, monkeypatch, projection):
    from app.config import get_settings
    from app.models import PPTProduct
    from app.services.catalog_prices import refresh_candidates
    from app.services.movers_service import build_rankings
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", False)
    monkeypatch.setattr(get_settings(), "catalog_current_prices_enabled", projection)
    now = datetime.now(UTC)
    # "box" (fixture) has no rarity and no metadata: the legacy sealed fallback.
    db.add(Card(id="single", name="Charizard", set_id="set", number="4", rarity="Rare Holo"))
    db.add(Card(id="ppt-box", name="Elite Trainer Box", set_id="set", number="ETB", rarity="Rare Holo"))
    db.add(Card(id="ppt-card", name="Pikachu", set_id="set", number="25"))  # no rarity, explicit card
    for pid, card_id, segment in [("a", "ppt-box", "english:sealed"), ("b", "ppt-card", "english:cards")]:
        db.add(PPTProduct(id=pid, provider_id=pid, card_id=card_id, segment=segment, status="matched",
                          metadata_payload={}, quotes=[]))
    for card_id in ["box", "single", "ppt-box", "ppt-card"]:
        db.add(PriceObservation(fingerprint=card_id, card_id=card_id, provider="tcgapi", provider_card_id=card_id,
            variant_id="default", price=100, observed_at=now,
            payload={"market_price": 100, "price_change_24h": 10, "price_change_30d": 10}))
    db.commit()
    refresh_candidates(db, ["box", "single", "ppt-box", "ppt-card"])
    db.commit()
    movers = build_rankings(db, now)["pokemon:24h"]
    assert sorted(item.card_id for item in movers.gainers) == ["ppt-card", "single"]
    sealed = sealed_service.calculate_sealed_signals(db, use_cache=False, game="all", per_page=10)
    assert sorted(item.card_id for item in sealed.items) == ["box", "ppt-box"]


class FakeRedis:
    """Enough Redis for snapshot leases, publishes and TTLs, on a clock tests can advance."""
    def __init__(self):
        self.values, self.clock = {}, 0
    def _live(self, key):
        value, expires = self.values.get(key, (None, None))
        if expires is not None and expires <= self.clock:
            self.values.pop(key)
            return None
        return value
    def get(self, key):
        return self._live(key)
    def mget(self, keys):
        return [self._live(key) for key in keys]
    def ttl(self, key):
        if self._live(key) is None:
            return -2
        expires = self.values[key][1]
        return -1 if expires is None else expires - self.clock
    def set(self, key, value, nx=False, ex=None):
        if nx and self._live(key) is not None:
            return False
        self.values[key] = (value, None if ex is None else self.clock + ex)
        return True
    def setex(self, key, ex, value):
        return self.set(key, value, ex=ex)
    def eval(self, script, count, *args):
        keys, argv = args[:count], args[count:]
        if self._live(keys[0]) != argv[0]:
            return 0
        del self.values[keys[0]]
        for key, value in zip(keys[1:], argv[1:-1]):
            self.set(key, value, ex=int(argv[-1]))
        return 1


@pytest.fixture
def snapshot_redis(db, monkeypatch):
    from app.services import market_snapshots
    redis = FakeRedis()
    monkeypatch.setattr(market_snapshots, "get_redis", lambda: redis)
    monkeypatch.setattr(market_snapshots, "SessionLocal", lambda: Session(db.get_bind()))
    return redis


@pytest.mark.parametrize("projection", [False, True])
def test_movers_snapshot_ranks_every_game_and_period_from_one_read(db, monkeypatch, projection):
    from sqlalchemy import event
    from app.config import get_settings
    from app.services import movers_service
    from app.services.catalog_prices import refresh_candidates
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", False)
    monkeypatch.setattr(get_settings(), "catalog_current_prices_enabled", projection)
    db.add(Set(id="jp", name="Japanese", series="Pokemon Japan"))
    now = datetime.now(UTC)
    rows = [("up", "set", {"price_change_24h": 30, "price_change_7d": -10}, "USD", now),
            ("up2", "set", {"price_change_24h": 10}, "USD", now),
            ("week", "set", {"price_change_7d": 90}, "USD", now),
            ("jp-card", "jp", {"price_change_24h": 99}, "USD", now),
            ("eur", "set", {"price_change_24h": 999}, "EUR", now),
            ("future", "set", {"price_change_24h": 999}, "USD", now + timedelta(days=1))]
    for index, (card_id, set_id, changes, currency, observed) in enumerate(rows):
        db.add(Card(id=card_id, name=card_id, set_id=set_id, number=str(index), rarity="Rare"))
        db.add(PriceObservation(fingerprint=card_id, card_id=card_id, provider="tcgapi", provider_card_id=card_id,
            variant_id="normal", currency=currency, price=10, observed_at=observed, payload=changes))
    db.commit()
    refresh_candidates(db, [row[0] for row in rows])
    db.commit()
    statements = []
    record = lambda *args: statements.append(args[2])
    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        rankings = movers_service.build_rankings(db, now, limit=1)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)
    assert len(statements) == 1
    assert [item.card_id for item in rankings["pokemon:24h"].gainers] == ["up"]
    assert rankings["pokemon:24h"].total_gainers == 2
    assert [item.card_id for item in rankings["pokemon:7d"].gainers] == ["week"]
    assert [item.card_id for item in rankings["pokemon:7d"].losers] == ["up"]
    assert [item.card_id for item in rankings["pokemon-japan:24h"].gainers] == ["jp-card"]
    assert rankings["pokemon-japan:30d"].total_gainers == 0


def test_market_snapshots_rebuild_only_every_12_hours(db, monkeypatch, snapshot_redis):
    from sqlalchemy import event
    from app.config import get_settings
    from app.services import market_snapshots
    from jobs.refresh_market_snapshots import refresh_due
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", False)
    monkeypatch.setattr("app.main.check_rate_limit", AsyncMock(return_value=(True, 0)))
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            for path in ["/cards/market-movers", "/cards/sealed-signals", "/cards/grading-profit"]:
                missing = client.get(path)
                assert missing.status_code == 503 and missing.headers["cache-control"] == "no-store"
            assert refresh_due() == {"movers": True, "sealed-evidence-v2": True, "grading-identity-v2": True}
            statements = []
            record = lambda *args: statements.append(args[2])
            event.listen(db.get_bind(), "before_cursor_execute", record)
            try:
                # The 15-minute Beat check queries nothing until a snapshot is 12 hours old.
                snapshot_redis.clock += 12 * 3600 - 60
                assert refresh_due() == {"movers": False, "sealed-evidence-v2": False, "grading-identity-v2": False}
                for path in ["/cards/market-movers", "/cards/grading-profit"]:
                    assert client.get(path).status_code == 200
            finally:
                event.remove(db.get_bind(), "before_cursor_execute", record)
            assert statements == []
            snapshot_redis.clock += 60
            assert refresh_due() == {"movers": True, "sealed-evidence-v2": True, "grading-identity-v2": True}
            # A lost snapshot (cache eviction) is rebuilt on the next check, not in 12 hours.
            snapshot_redis.values.pop(market_snapshots.part_key("grading-identity-v2"))
            assert refresh_due() == {"movers": False, "sealed-evidence-v2": False, "grading-identity-v2": True}
            # Failed rebuilds keep serving the previous snapshot for up to 36 hours.
            snapshot_redis.clock += 36 * 3600
            assert client.get("/cards/market-movers").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_sealed_and_grading_snapshots_match_on_demand_results(db, monkeypatch, snapshot_redis):
    from app.config import get_settings
    from app.services import grading_service
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", False)
    now = datetime.now(UTC)
    db.add(Set(id="old", name="Vintage Set", release_date=date(2001, 1, 1)))
    for card_id, set_id, name, price, listings in [("etb", "set", "Elite Trainer Box", 60, 10),
                                                   ("bb", "old", "Booster Box", 900, 200)]:
        db.add(Card(id=card_id, name=name, set_id=set_id, number=card_id))
        db.add(PriceObservation(fingerprint=card_id, card_id=card_id, provider="tcgapi", provider_card_id=card_id,
            variant_id="default", price=price, observed_at=now,
            payload={"market_price": price, "total_listings": listings, "price_change_30d": 12}))
    for card_id, raw, psa10, psa9 in [("zard", 100, 900, 300), ("pika", 10, 40, None), ("mew", 50, None, 45)]:
        db.add(Card(id=card_id, name=card_id.title(), set_id="set", number=card_id, rarity="Rare Holo"))
        for grade, price in [(None, raw), (10, psa10), (9, psa9)]:
            if price is not None:
                db.add(PriceObservation(fingerprint=f"{card_id}-{grade}", card_id=card_id, provider="tcgapi",
                    provider_card_id=card_id, variant_id="default", price=price, observed_at=now,
                    grading_company="PSA" if grade else None, grade=grade, payload={}))
    db.commit()
    assert sealed_service.refresh_snapshot(force=True) and grading_service.refresh_snapshot(force=True)
    for filters in [{}, {"era": "older"}, {"product_type": "etb"}, {"signal": "strong_buy"}, {"q": "vintage"},
                    {"sort_by": "price_asc", "per_page": 1, "page": 2}, {"period": 90, "sort_by": "momentum_desc"}]:
        stored = sealed_service.stored_sealed_signals(db, **filters)
        fresh = sealed_service.calculate_sealed_signals(db, use_cache=False, **filters)
        assert stored.model_dump(exclude={"updated_at"}) == fresh.model_dump(exclude={"updated_at"}), filters
    assert sealed_service.stored_sealed_signals(db).total_items == 2
    for filters in [{}, {"grading_fee": 100}, {"target_grade": "psa9"}, {"sort_by": "spread_desc"},
                    {"max_raw_price": 60, "min_profit": 0}, {"psa9_safe_only": True}, {"q": "pika"}, {"set_id": "nope"}]:
        stored = grading_service.stored_grading_profit(db, **filters)
        fresh = grading_service.calculate_grading_profit(db, use_cache=False, **filters)
        assert stored.model_dump(exclude={"updated_at"}) == fresh.model_dump(exclude={"updated_at"}), filters
    assert [item.card_id for item in grading_service.stored_grading_profit(db).items] == ["zard", "pika", "mew"]


def test_movers_api_serves_snapshot_without_sql(db, monkeypatch, snapshot_redis):
    from sqlalchemy import event
    from app.config import get_settings
    from app.services import movers_service
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", False)
    monkeypatch.setattr("app.main.check_rate_limit", AsyncMock(return_value=(True, 0)))
    for index in range(3):
        db.add(Card(id=f"c{index}", name=f"c{index}", set_id="set", number=str(index), rarity="Rare"))
        db.add(PriceObservation(fingerprint=f"c{index}", card_id=f"c{index}", provider="tcgapi",
            provider_card_id=f"c{index}", variant_id="normal", price=10, observed_at=datetime.now(UTC),
            payload={"price_change_24h": index + 1}))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            assert movers_service.refresh_snapshot() is True
            statements = []
            record = lambda *args: statements.append(args[2])
            event.listen(db.get_bind(), "before_cursor_execute", record)
            try:
                page = client.get("/cards/market-movers?direction=up&per_page=2&page=2")
            finally:
                event.remove(db.get_bind(), "before_cursor_execute", record)
            assert page.status_code == 200, page.text
            assert statements == []
            data = page.json()
            assert [item["card_id"] for item in data["gainers"]] == ["c0"]
            assert data["total_gainers"] == 3 and data["total_pages"] == 2 and data["losers"] == []
            assert page.headers["x-cache-generated-at"] == data["updated_at"].replace("Z", "+00:00")
    finally:
        app.dependency_overrides.clear()


def test_market_data_migration_preserves_catalog(tmp_path, monkeypatch):
    # Alembic logging setup must not disable pytest/application loggers.
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    from alembic import command
    from alembic.config import Config
    from app.config import get_settings
    database = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setattr(get_settings(), "database_url", database)
    monkeypatch.setattr(get_settings(), "postgres_host", None)
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(config, "0006_site_analytics")
    engine = create_engine(database)
    def schema():
        inspector = inspect(engine)
        return {table: (inspector.get_columns(table), inspector.get_indexes(table), inspector.get_foreign_keys(table)) for table in ("cards", "sets")}
    before = repr(schema())
    command.upgrade(config, "head")
    assert "market_history" in inspect(engine).get_table_names()
    assert repr(schema()) == before
    command.downgrade(config, "0006_site_analytics")
    assert "market_history" not in inspect(engine).get_table_names()
    assert repr(schema()) == before
    command.upgrade(config, "head")
    assert repr(schema()) == before
    engine.dispose()


def test_retired_history_job_preserves_existing_data(db, monkeypatch):
    from jobs import sync_market_data as job
    db.add(MarketHistory(card_id="box", printing="Normal", day=datetime.now(UTC).date(), market_price=100, sales_volume=3, fetched_at=datetime.now(UTC)))
    db.commit()
    factory = Mock(side_effect=AssertionError("No legacy provider construction"))
    assert job.sync_market_data.run(limit=2, card_ids=["box"])["status"] == "retired"
    factory.assert_not_called()
    assert db.scalar(select(func.count()).select_from(MarketHistory)) == 1


def test_trending_can_skip_observation_aggregates(db, monkeypatch):
    from app.services import trending_service
    monkeypatch.setattr(trending_service, "get_redis", lambda: None)
    trending_service._TRENDING_CACHE.clear()
    monkeypatch.setattr(trending_service, "calculate_trending_cards", lambda *args, **kwargs: [])
    monkeypatch.setattr(trending_service, "calculate_trending_pokemon", lambda *args, **kwargs: [])
    volume = Mock(side_effect=AssertionError("Observation aggregation must not run"))
    monkeypatch.setattr(trending_service, "calculate_top_pokemon_volume", volume)
    result = trending_service.get_trending_dashboard(db, include_observation_volume=False)
    assert result.volume_pokemon == []
    volume.assert_not_called()
    trending_service._TRENDING_CACHE.clear()


def test_sealed_90_day_return_uses_history_not_weekly_momentum(db):
    today = datetime.now(UTC).date()
    db.add(PriceObservation(card_id="box", provider="tcgapi", provider_card_id="box", variant_id="normal", printing="Normal", fingerprint="histbox", price=150, payload={"price_change_30d": 20, "price_change_7d": 999, "market_price_as_of": today.isoformat()}))
    for age, price in [(90, 100), (0, 150)]:
        db.add(MarketHistory(card_id="box", printing="Normal", day=today - timedelta(days=age), market_price=price, fetched_at=datetime.now(UTC)))
    db.commit()
    result = sealed_service.calculate_sealed_signals(db, period=90, sort_by="momentum_desc")
    assert result.items[0].return_percent == 50
    assert result.items[0].price_freshness == "recent"
    assert len(result.items[0].history["points"]) == 2


def test_history_collection_is_opt_in():
    from app.celery_app import celery_app
    from app.config import Settings
    assert Settings(_env_file=None).market_history_enabled is False
    assert "sync-market-history" not in celery_app.conf.beat_schedule


@pytest.mark.parametrize("price, percent, previous, delta", [(120, 20, 100, 20), (50, -50, 100, -50), (100, 0, 100, 0)])
def test_estimated_comparison(price, percent, previous, delta):
    result = service.estimated_price_change(price, percent)
    assert result["previous_price"] == previous
    assert result["price_change_amount"] == delta
    assert result["comparison_source"] == "estimated"


@pytest.mark.parametrize("percent", [None, -100, -110, float("nan"), float("inf")])
def test_invalid_comparison_is_unavailable(percent):
    assert service.estimated_price_change(100, percent) == {}


def test_sealed_comparison_uses_history_endpoint_not_current_quote(db):
    today = datetime.now(UTC).date()
    db.add(PriceObservation(card_id="box", provider="tcgapi", provider_card_id="box", variant_id="normal", printing="Normal", fingerprint="comparison", price=999, payload={"price_change_30d": 5}))
    for ago, price in [(90, 100), (0, 150)]:
        db.add(MarketHistory(card_id="box", printing="Normal", day=today - timedelta(days=ago), market_price=price, fetched_at=datetime.now(UTC)))
    db.commit()
    item = sealed_service.calculate_sealed_signals(db, period=90).items[0]
    assert item.market_price == 999
    assert item.previous_price == 100
    assert item.comparison_price == 150
    assert item.price_change_amount == 50
    assert item.return_percent == 50
    assert item.comparison_source == "history"


def test_sales_status_search_and_scoped_sync(db):
    assert service.sales_activity(db)["status"] == "not_synced"
    today = datetime.now(UTC).date()
    db.add(MarketHistory(card_id="box", printing="Normal", day=today, market_price=100, sales_volume=None, fetched_at=datetime.now(UTC)))
    db.commit()
    assert service.sales_activity(db)["status"] == "no_sales"
    row = db.get(MarketHistory, ("box", "Normal", today))
    row.sales_volume = 0
    db.commit()
    result = service.sales_activity(db, q="Test")
    assert result["status"] == "ready"
    assert result["total_sales"] == 0
    assert result["products_with_sales_data"] == 1
    assert result["synced_at"] is not None
    empty = service.sales_activity(db, q="missing")
    assert empty["status"] == "no_matches"
    assert empty["synced_at"] is None


def test_profile_uses_current_tcg_percentages_without_rewriting_history(db):
    from fastapi import Response
    from app.routers.cards import get_card_prices
    now = datetime.now(UTC)
    db.add(PriceObservation(card_id="box", provider="tcgapi", provider_card_id="box", variant_id="normal", printing="Normal", fingerprint="old-momentum", price=100,
        observed_at=now - timedelta(days=10), payload={"price_change_24h": 1, "price_change_7d": 75, "price_change_30d": 90}))
    db.add(ProviderCardState(card_id="box", provider="tcgapi", match_status="matched", last_synced_at=now, payload={"prices": {"data": [
        {"printing": "Normal", "market_price": 100, "price_change_24h": 1, "price_change_7d": -4, "price_change_30d": None},
        {"printing": "Foil", "market_price": 200, "price_change_7d": 40, "price_change_30d": 50},
    ]}}))
    db.commit()
    result = get_card_prices("box", Response(), days=365, db=db)
    quote = result.tcg_market_prices[0]
    assert quote.price == 100
    assert quote.price_change_24h == 1
    assert quote.price_change_7d == -4
    assert quote.price_change_30d is None
    assert result.observations[0].price_change_30d == 90
    assert result.avg_listing_price is None
    assert result.median_listing_price is None


def test_profile_seven_day_raw_usd_listing_sample(db):
    from fastapi import Response
    from app.routers.cards import get_card_prices
    now = datetime.now(UTC)
    for index, (listing, price, days, currency, graded) in enumerate([
        ("a", 10, 2, "USD", False), ("a", 20, 1, "USD", False),
        ("b", 40, 6, "USD", False), ("c", 10000, 8, "USD", False),
        ("d", 900, 1, "USD", True), ("e", 800, 1, "EUR", False),
        ("f", 700, -1, "USD", False),
    ]):
        db.add(PriceObservation(card_id="box", provider="ebay", provider_card_id=listing, variant_id=f"variant-{index}", fingerprint=f"listing-{index}", price=price,
            observed_at=now - timedelta(days=days), currency=currency, grading_company="PSA" if graded else None))
    db.commit()
    result = get_card_prices("box", Response(), days=1, db=db)
    assert result.listing_sample_count == 0
    assert result.avg_listing_price is None
    assert result.median_listing_price is None
    assert result.excluded_listing_count > 0
    assert result.tcg_market_prices == []


def test_public_graded_sales_api(db, monkeypatch):
    from app.config import get_settings
    from app.models import PPTProduct
    monkeypatch.setattr(get_settings(), 'ppt_primary_enabled', True)
    db.add(PPTProduct(id='graded', provider_id='1', card_id='box', segment='english:cards', status='matched',
        last_success_at=datetime.now(UTC), metadata_payload={'ebay': {'salesByGrade': {'psa10': {'count': 3}}}}))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr('app.main.check_rate_limit', AsyncMock(return_value=(True, 0)))
    try:
        with TestClient(app) as client:
            response = client.get('/market/graded-sales-activity?q=Test')
            assert response.status_code == 200, response.text
            assert response.headers['cache-control'] == 'public, max-age=60'
            result = response.json()
            assert result['status'] == 'ready'
            assert result['items'][0]['sales'] == 3
            assert result['items'][0]['synced_at'] is None
            assert result['items'][0]['stale'] is True
            assert client.get('/market/graded-sales-activity?q=' + 'x' * 121).status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("redis_failure", ["missing_client", "connection"])
def test_market_snapshot_outage_never_computes_public_rankings(db, monkeypatch, redis_failure):
    from app.config import get_settings
    from app.services import market_snapshots, movers_service, grading_service
    from fastapi import HTTPException
    monkeypatch.setattr(get_settings(), "market_snapshots_on_demand_fallback", False)
    redis = None if redis_failure == "missing_client" else Mock(get=Mock(side_effect=ConnectionError("offline")))
    monkeypatch.setattr(market_snapshots, "get_redis", lambda: redis)
    def unexpected(*args, **kwargs):
        pytest.fail("Public request attempted a full database rebuild")
    monkeypatch.setattr(movers_service, "build_rankings", unexpected)
    monkeypatch.setattr(sealed_service, "build_snapshot", unexpected)
    monkeypatch.setattr(grading_service, "build_snapshot", unexpected)
    for call in [lambda: movers_service.stored_movers(db, "pokemon", "24h"),
                 lambda: sealed_service.stored_sealed_signals(db),
                 lambda: grading_service.stored_grading_profit(db)]:
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code == 503
        assert error.value.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("raw", ['null', '[]', '{"updated_at":"bad"}',
                                  '{"updated_at":"2020-01-01T00:00:00+00:00"}'])
def test_market_snapshot_rejects_invalid_and_expired_payloads(monkeypatch, raw):
    from fastapi import HTTPException
    from app.services import market_snapshots
    monkeypatch.setattr(market_snapshots, "get_redis", lambda: Mock(get=Mock(return_value=raw)))
    with pytest.raises(HTTPException) as error:
        market_snapshots.read("movers", "pokemon:24h")
    assert error.value.status_code == 503


def test_market_snapshot_failed_rebuild_keeps_previous_publication(db, monkeypatch):
    import fakeredis
    import json
    from app.services import market_snapshots
    redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(market_snapshots, "get_redis", lambda: redis)
    monkeypatch.setattr(market_snapshots, "SessionLocal", lambda: Session(db.get_bind()))
    build = lambda session, now: {part: json.dumps({"updated_at": now.isoformat(), "value": part})
                                for part in ["a", "b"]}
    assert market_snapshots.refresh("test", ["a", "b"], build)
    before = redis.mget([market_snapshots.part_key("test", part) for part in ["a", "b"]])
    def fail(session, now):
        raise RuntimeError("database rebuild failed")
    assert market_snapshots.refresh("test", ["a", "b"], fail, force=True) is False
    assert redis.mget([market_snapshots.part_key("test", part) for part in ["a", "b"]]) == before
    assert redis.get(market_snapshots.part_key("test", "lock")) is None
    # A worker that loses its lease cannot overwrite a newer owner's publication.
    def lose_lease(session, now):
        redis.set(market_snapshots.part_key("test", "lock"), "new-owner", ex=600)
        return build(session, now)
    assert market_snapshots.refresh("test", ["a", "b"], lose_lease, force=True) is False
    assert redis.mget([market_snapshots.part_key("test", part) for part in ["a", "b"]]) == before
    assert redis.get(market_snapshots.part_key("test", "lock")) == "new-owner"


def test_market_snapshot_seed_reports_failed_and_fresh_runs(db, monkeypatch, snapshot_redis):
    from jobs import refresh_market_snapshots as job
    from app.services import movers_service
    assert job.main() == 0
    assert job.main() == 0  # Fresh snapshots skipped successfully.
    monkeypatch.setattr(movers_service, "refresh_snapshot", lambda **kwargs: False)
    assert job.main(force=True) == 1


def test_grading_snapshot_keeps_cards_across_batch_boundaries(db, monkeypatch):
    from app.config import get_settings
    from app.services import grading_service
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", False)
    now = datetime.now(UTC)
    for index in range(257):
        card_id = f"graded-{index}"
        db.add(Card(id=card_id, name=card_id, set_id="set", number=str(index), rarity="Rare"))
        for grade, price in [(None, 10), (10, 100)]:
            db.add(PriceObservation(fingerprint=f"{card_id}-{grade}", card_id=card_id, provider="tcgapi",
                provider_card_id=card_id, variant_id=str(grade), price=price, observed_at=now,
                grading_company="PSA" if grade else None, grade=grade))
    db.commit()
    snapshot = grading_service.build_snapshot(db, now)
    assert {row[0] for row in snapshot["rows"]} == {f"graded-{i}" for i in range(257)}
    assert all(row[6:9] == [10, 100, None] for row in snapshot["rows"])


def _grading_snapshot(prices):
    from app.services.grading_service import FIELDS
    return {"updated_at": datetime.now(UTC).isoformat(), "fields": FIELDS, "rows": [
        [cid, cid, "set", "Test", "1", "Rare", 100, p10, p9, "pokemonpricetracker", "median_7d", None]
        for cid, p10, p9 in prices
    ]}


@pytest.mark.parametrize("sort_by", ["psa10_profit_desc", "psa10_roi_desc", "psa9_profit_desc", "psa9_roi_desc", "ev_desc"])
def test_grading_sort_preserves_break_even_and_missing_outcomes(sort_by):
    from app.services.grading_service import select_grading_profit
    snapshot = _grading_snapshot([("loss", 110, 110), ("zero", 125, 125), ("gain", 150, 150),
                                  ("missing", None, 125) if sort_by.startswith("psa10") or sort_by == "ev_desc" else ("missing", 125, None)])
    result = select_grading_profit(snapshot, grading_fee=25, sort_by=sort_by)
    assert [item.card_id for item in result.items] == ["gain", "zero", "loss", "missing"]
    assert result.items[1].expected_value == 0
    assert result.items[-1].expected_value is None


@pytest.mark.parametrize("prices", [(None, 150), (150, None)])
def test_grading_expected_value_requires_both_grades(prices):
    from app.services.grading_service import select_grading_profit
    item = select_grading_profit(_grading_snapshot([("partial", *prices)]), grading_fee=25).items[0]
    assert item.expected_value is None
    assert (item.psa10_profit, item.psa9_profit) == tuple(None if p is None else 25 for p in prices)


def test_sealed_missing_evidence_does_not_generate_a_signal(db):
    db.add(PriceObservation(card_id="box", provider="tcgapi", provider_card_id="box", variant_id="normal",
        fingerprint="missing-evidence", price=100, payload={"price_change_7d": 50}))
    db.commit()
    result = sealed_service.calculate_sealed_signals(db, use_cache=False)
    item = result.items[0]
    assert item.supply_score is None and item.supply_rating == "Unavailable"
    assert item.demand_score is None and item.momentum_score is None
    assert item.signal_score is None and item.signal_label == "INSUFFICIENT DATA"
    assert result.strong_buy_count + result.buy_count + result.hold_count + result.underperform_count == 0
    assert sealed_service.calculate_sealed_signals(db, use_cache=False, signal="buy").items == []


def test_sealed_zero_monthly_return_is_not_replaced_by_short_term_growth(db):
    db.add(PriceObservation(card_id="box", provider="tcgapi", provider_card_id="box", variant_id="normal",
        fingerprint="zero-momentum", price=100, payload={"total_listings": 10, "buylist_price": 80,
            "price_change_30d": 0, "price_change_7d": 50, "price_change_24h": 90}))
    db.commit()
    item = sealed_service.calculate_sealed_signals(db, use_cache=False).items[0]
    assert item.momentum_score == 14
    assert item.signal_score == item.supply_score + item.demand_score + item.vintage_score + 14


def test_sealed_score_sort_puts_incomplete_evidence_last(db, monkeypatch):
    monkeypatch.setattr(sealed_service, "_page_history", lambda *args: None)
    db.add(PriceObservation(card_id="box", provider="tcgapi", provider_card_id="box", variant_id="normal",
        fingerprint="sort-evidence", price=100, payload={}))
    db.commit()
    snapshot = sealed_service.build_snapshot(db, datetime.now(UTC))
    snapshot["items"].append({**snapshot["items"][0], "card_id": "scored", "signal_score": 0,
                              "signal_label": "UNDERPERFORM"})
    for sort in ("score_desc", "supply_asc"):
        result = sealed_service.select_sealed_signals(db, snapshot, sort_by=sort)
        assert [item.card_id for item in result.items] == ["scored", "box"]
