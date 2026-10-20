import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def no_trending_dev_fallback(monkeypatch):
    """A local .env may enable the dev-only Trending fallback; tests must never publish
    into the developer's real Redis/Postgres through it. Tests opt in explicitly."""
    monkeypatch.setattr(get_settings(), "trending_on_demand_fallback", False)
