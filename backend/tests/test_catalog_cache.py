from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.routers.cards import clear_catalog_caches, _evict_oldest_cache_entries


@pytest.fixture(autouse=True)
def reset_caches() -> None:
    clear_catalog_caches()
    yield
    clear_catalog_caches()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        card_set = Set(
            id="base1",
            name="Base Set",
            series="Base",
            printed_total=102,
            release_date=date(1999, 1, 9),
        )
        card = Card(
            id="base1-4",
            name="Charizard",
            set_id="base1",
            number="4",
            printed_total=102,
            rarity="Rare Holo",
            image_url="https://images.test/base1-4.jpg",
        )
        booster_card = Card(
            id="base1-booster",
            name="Base Set Booster Pack",
            set_id="base1",
            number="B1",
            printed_total=102,
            rarity="None",
            image_url="https://images.test/base1-booster.jpg",
        )
        price_obs = PriceObservation(
            fingerprint="fp-base1-4",
            card_id="base1-4",
            provider="tcgapi",
            provider_card_id="tcg-4",
            variant_id="normal",
            condition="Near Mint",
            printing="Holofoil",
            price=Decimal("350.00"),
            currency="USD",
            provider_updated_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            observed_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        )
        session.add_all([card_set, card, booster_card, price_obs])
        session.commit()

    def override_get_db() -> Generator[Session, None, None]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def test_search_cards_uses_in_memory_cache(client: TestClient) -> None:
    # First request populates cache
    res1 = client.get("/cards/search?limit=24&sort_by=price_desc&hide_sealed=true")
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1) == 1
    assert data1[0]["name"] == "Charizard"
    assert data1[0]["market_price"] == 350.0

    # Second request hits in-memory cache directly
    res2 = client.get("/cards/search?limit=24&sort_by=price_desc&hide_sealed=true")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data1 == data2


def test_search_cards_different_queries_isolated(client: TestClient) -> None:
    res_charizard = client.get("/cards/search?q=Charizard")
    assert res_charizard.status_code == 200
    assert len(res_charizard.json()) == 1

    res_pikachu = client.get("/cards/search?q=Pikachu")
    assert res_pikachu.status_code == 200
    assert len(res_pikachu.json()) == 0


def test_list_card_sets_uses_cache(client: TestClient) -> None:
    res1 = client.get("/cards/sets?game=all")
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1) == 1
    assert data1[0]["id"] == "base1"
    # Booster card preferred for thumbnail
    assert data1[0]["image_url"] == "/cards/base1-booster/image"

    res2 = client.get("/cards/sets?game=all")
    assert res2.status_code == 200
    assert res2.json() == data1


def test_redis_cache_hit_and_write(client: TestClient) -> None:
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # miss initially

    with patch("app.routers.cards._get_redis", return_value=mock_redis):
        clear_catalog_caches()
        res = client.get("/cards/search?q=Charizard")
        assert res.status_code == 200
        # Check that it attempted to write to Redis
        assert mock_redis.setex.called
        assert "cardboarddex:catalog:search:" in mock_redis.setex.call_args[0][0]


def test_redis_error_gracefully_degrades(client: TestClient) -> None:
    mock_redis = MagicMock()
    mock_redis.get.side_effect = RedisError("Connection refused")
    mock_redis.setex.side_effect = RedisError("Read-only replica")

    with patch("app.routers.cards._get_redis", return_value=mock_redis):
        clear_catalog_caches()
        # Should gracefully log warning and proceed to DB
        res = client.get("/cards/search?q=Charizard")
        assert res.status_code == 200
        assert len(res.json()) == 1


def test_evict_oldest_cache_entries() -> None:
    cache = {
        "key1": (100.0, "data1"),
        "key2": (200.0, "data2"),
        "key3": (300.0, "data3"),
        "key4": (400.0, "data4"),
    }
    _evict_oldest_cache_entries(cache, count=2)
    assert "key1" not in cache
    assert "key2" not in cache
    assert "key3" in cache
    assert "key4" in cache
