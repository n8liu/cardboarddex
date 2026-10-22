from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app.celery_app import celery_app
from app.main import app


def test_alembic_has_one_linear_head_with_catalog_foundation() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0013_catalog_price_selected"]
    assert script.get_revision("0013_catalog_price_selected").down_revision == "0012_market_history_transitions"
    assert script.get_revision("0011_catalog_prices").down_revision == "0010_ppt_query_indexes"
    assert script.get_revision("0010_ppt_query_indexes").down_revision == "0009_pokemon_price_tracker"
    assert script.get_revision("0009_pokemon_price_tracker").down_revision == "0008_listing_assessments"
    assert script.get_revision("0008_listing_assessments").down_revision == "0007_market_data"
    assert script.get_revision("0007_market_data").down_revision == "0006_site_analytics"
    assert script.get_revision("0006_site_analytics").down_revision == "0005_price_obs_analytics_cover"
    assert script.get_revision("0005_price_obs_analytics_cover").down_revision == "0004_price_obs_search_index"
    assert script.get_revision("0004_price_obs_search_index").down_revision == "0003_ebay_raw_listings"
    assert script.get_revision("0003_ebay_raw_listings").down_revision == "0002_provider_pricing"
    assert script.get_revision("0002_provider_pricing").down_revision == "0001_catalog"


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_uses_configured_frontend_origin() -> None:
    response = TestClient(app).options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_only_active_providers_are_scheduled():
    assert "sync-catalog-daily" not in celery_app.conf.beat_schedule
    assert "collect-tcgapi-prices-alternating" not in celery_app.conf.beat_schedule
    assert "collect-ebay-prices-alternating" in celery_app.conf.beat_schedule
