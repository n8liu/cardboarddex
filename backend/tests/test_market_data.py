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
