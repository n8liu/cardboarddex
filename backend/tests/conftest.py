import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def no_trending_dev_fallback(monkeypatch):
    """A local .env may enable the dev-only Trending fallback; tests must never publish
    into the developer's real Redis/Postgres through it. Tests opt in explicitly."""
    monkeypatch.setattr(get_settings(), "trending_on_demand_fallback", False)


@pytest.fixture(autouse=True)
def no_live_feed_shared_cache(monkeypatch):
    """Feed tests read uncommitted rows through their own session; tests opt in explicitly."""
    monkeypatch.setattr(get_settings(), "live_feed_shared_cache_enabled", False)
