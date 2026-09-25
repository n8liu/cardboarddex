from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app.celery_app import celery_app
from app.main import app


def test_alembic_has_one_linear_head_with_catalog_foundation() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0005_price_obs_analytics_cover"]
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


def test_catalog_sync_is_scheduled_daily() -> None:
    schedule = celery_app.conf.beat_schedule["sync-catalog-daily"]
    assert schedule["task"] == "jobs.sync_catalog.sync_catalog"
    assert schedule["schedule"]._orig_minute == 0
    assert schedule["schedule"]._orig_hour == 3
    assert schedule["schedule"]._orig_day_of_week == "*"
