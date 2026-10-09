"""Opt-in integration test. The URL must point at a disposable analytics_test DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.schemas.analytics import PageView
from app.services.site_analytics_service import record_page_view, report


@pytest.mark.skipif(not os.getenv("TEST_ANALYTICS_POSTGRES_URL"), reason="Requires disposable PostgreSQL database")
def test_postgres_migration_and_concurrent_events(monkeypatch):
    url = os.environ["TEST_ANALYTICS_POSTGRES_URL"]
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"} and parsed.database == "analytics_test"
    settings = get_settings()
    monkeypatch.setattr(settings, "postgres_host", None)
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.setattr(settings, "analytics_identity_secret", "p" * 32)
    engine = create_engine(url)
    config = Config("alembic.ini")
    command.upgrade(config, "0005_price_obs_analytics_cover")

    def catalog_schema():
        inspector = inspect(engine)
        return {table: (str(inspector.get_columns(table)), str(inspector.get_indexes(table)),
                        str(inspector.get_unique_constraints(table)), str(inspector.get_foreign_keys(table)))
                for table in ("cards", "sets")}

    original = catalog_schema()
    command.upgrade(config, "head")
    assert catalog_schema() == original
    command.downgrade(config, "0005_price_obs_analytics_cover")
    assert catalog_schema() == original
    assert "analytics_events" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    visitor = uuid4()
    now = datetime.now(UTC)
    unique_events = [PageView(event_id=uuid4(), visitor_id=visitor, path="/catalog") for _ in range(12)]

    def write(event):
        with Session(engine) as db:
            return record_page_view(db, event, "US", now)

    # Concurrent first visits from one browser and duplicate deliveries.
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(write, unique_events + unique_events))
    assert sum(results) == 12
    with Session(engine) as db:
        # Reports must bucket UTC even when the PostgreSQL session uses another timezone.
        db.execute(text("SET TIME ZONE 'Pacific/Auckland'"))
        result = report(db, now.date(), now.date(), now)
        assert result["current"] == {"views": 12, "visitors": 1, "sessions": 1}
        assert result["total_views"] == 12
        assert result["daily"][0]["views"] == 12
    engine.dispose()
