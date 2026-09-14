from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.routers.cards import get_tcgapi_client, clear_catalog_caches
from app.common.redis import get_redis
from app.services.catalog_service import _pokemon_volume_cache
from app.services.trending_service import (
    _IN_MEMORY_CARD_CLICKS,
    _IN_MEMORY_POKE_CLICKS,
    _IN_MEMORY_SEARCHES,
    _TRENDING_CACHE,
    invalidate_trending_cache,
)


class FakeImageClient:
    def get_image(self, source_url: str) -> tuple[bytes, str]:
        assert source_url == "https://tcgplayer-cdn.test/pikachu.jpg"
        return b"image-bytes", "image/jpeg"


def _clean_test_caches() -> None:
    clear_catalog_caches()
    _pokemon_volume_cache.clear()
    _IN_MEMORY_CARD_CLICKS.clear()
    _IN_MEMORY_POKE_CLICKS.clear()
    _IN_MEMORY_SEARCHES.clear()
    _TRENDING_CACHE.clear()
    invalidate_trending_cache()
    r = get_redis()
    if r is not None:
        try:
            for prefix in [
                "cardboarddex:top_volume:*",
                "cardboarddex:trending:*",
                "cardboarddex:analytics:*",
                "cardboarddex:catalog:*",
            ]:
                keys = r.keys(prefix)
                if keys:
                    r.delete(*keys)
        except Exception:
            pass


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    _clean_test_caches()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(
            id="1",
            name="Base Set",
            series="Original",
            printed_total=102,
            release_date=date(1999, 1, 9),
        ))
        session.add(Set(
            id="2",
            name="Jungle",
            series="Original",
            printed_total=64,
            release_date=date(1999, 6, 16),
        ))
        session.add(Card(
            id="pikachu-1",
            name="Pikachu",
            set_id="1",
            number="58",
            printed_total=102,
            rarity="Common",
            image_url="https://tcgplayer-cdn.test/pikachu.jpg",
        ))
        session.add(Card(
            id="venusaur-1",
            name="Venusaur",
            set_id="1",
            number="15",
            printed_total=102,
            rarity="Rare Holo",
            image_url="https://tcgplayer-cdn.test/venusaur.jpg",
        ))
        session.add(Card(
            id="eevee-1",
            name="Eevee",
            set_id="2",
            number="51",
            printed_total=64,
            rarity="Common",
            image_url="https://tcgplayer-cdn.test/eevee.jpg",
        ))
        session.add(Card(
            id="base-box-1",
            name="Base Set Booster Box",
            set_id="1",
            number="",
            printed_total=None,
            rarity=None,
            image_url="https://tcgplayer-cdn.test/box.jpg",
        ))
        session.add(ProviderCardState(
            card_id="pikachu-1",
            provider="tcgapi",
            provider_card_id="provider-pikachu",
            match_status="matched",
            match_method="exact_name_set_number",
        ))
        session.add(PriceObservation(
            fingerprint="a" * 64,
            card_id="pikachu-1",
            provider="tcgapi",
            provider_card_id="provider-pikachu",
            variant_id="near-mint",
            condition="Near Mint",
            printing="Normal",
            price=Decimal("12.34"),
            currency="USD",
            provider_updated_at=datetime.now(UTC),
        ))
        session.add(PriceObservation(
            fingerprint="b" * 64,
            card_id="pikachu-1",
            provider="legacy_provider",
            provider_card_id="legacy-pikachu",
            variant_id="legacy-near-mint",
            condition="Near Mint",
            printing="Normal",
            price=Decimal("999.99"),
            currency="USD",
            provider_updated_at=datetime.now(UTC),
        ))
        session.add(Set(
            id="3",
            name="Empty Set Without Cards",
            series="Promo",
            printed_total=10,
            release_date=date(2020, 1, 1),
        ))
        session.add(Card(
            id="code-card-1",
            name="Code Card - Base Set Booster Pack",
            set_id="1",
            number="",
            printed_total=None,
            rarity="Code Card",
            image_url="https://tcgplayer-cdn.test/code.jpg",
        ))
        session.add(PriceObservation(
            fingerprint="c" * 64,
            card_id="venusaur-1",
            provider="tcgapi",
            provider_card_id="provider-venusaur",
            variant_id="holo",
            condition="Near Mint",
            printing="Holofoil",
            price=Decimal("150.00"),
            currency="USD",
            provider_updated_at=datetime.now(UTC),
        ))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tcgapi_client] = lambda: FakeImageClient()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_search_cards_by_name_and_set(client: TestClient) -> None:
    pika_response = client.get("/cards/search", params={"q": "pika"})
    assert pika_response.status_code == 200
    assert pika_response.json()[0]["name"] == "Pikachu"
    assert pika_response.json()[0]["market_price"] == 12.34
    assert pika_response.json()[0]["market_currency"] == "USD"

    base_response = client.get("/cards/search", params={"q": "base", "hide_sealed": "true"})
    assert base_response.status_code == 200
    assert any(item["name"] == "Pikachu" for item in base_response.json())


def test_search_cards_filters_empty_sets_and_code_cards(client: TestClient) -> None:
    # Empty set 3 is excluded from /cards/sets
    sets_response = client.get("/cards/sets")
    assert sets_response.status_code == 200
    set_names = [item["name"] for item in sets_response.json()]
    assert set_names == ["Jungle", "Base Set"]
    assert "Empty Set Without Cards" not in set_names

    # Code cards are filtered out of search
    all_search = client.get("/cards/search", params={"q": "Code", "hide_sealed": "false"})
    assert all_search.status_code == 200
    assert len(all_search.json()) == 0


def test_get_set_stats(client: TestClient) -> None:
    # 1. Base Set stats (Pikachu $12.34 + Venusaur $150.00 = $162.34, 2 cards when hide_sealed=true)
    res = client.get("/cards/sets/1/stats", params={"hide_sealed": "true"})
    assert res.status_code == 200
    data = res.json()
    assert data["set_id"] == "1"
    assert data["set_name"] == "Base Set"
    assert data["total_cards"] == 2
    assert data["priced_cards"] == 2
    assert data["total_price"] == 162.34
    assert data["avg_price"] == 81.17
    assert data["currency"] == "USD"

    # 2. Filtered with search query q="pika"
    res_q = client.get("/cards/sets/1/stats", params={"q": "pika", "hide_sealed": "true"})
    assert res_q.status_code == 200
    data_q = res_q.json()
    assert data_q["total_cards"] == 1
    assert data_q["priced_cards"] == 1
    assert data_q["total_price"] == 12.34

    # 3. Non-existent set returns 404
    res_404 = client.get("/cards/sets/missing-set/stats")
    assert res_404.status_code == 404


def test_search_cards_sort_options(client: TestClient) -> None:
    # Default is price_desc (Venusaur $150 > Pikachu $12.34 > Eevee None)
    default_sort = client.get("/cards/search", params={"hide_sealed": "true"})
    assert default_sort.status_code == 200
    assert [item["name"] for item in default_sort.json()] == ["Venusaur", "Pikachu", "Eevee"]

    # price_asc
    price_asc = client.get("/cards/search", params={"sort_by": "price_asc", "hide_sealed": "true"})
    assert price_asc.status_code == 200
    assert [item["name"] for item in price_asc.json()] == ["Pikachu", "Venusaur", "Eevee"]

    # number_asc
    number_asc = client.get("/cards/search", params={"set_id": "1", "sort_by": "number_asc", "hide_sealed": "true"})
    assert number_asc.status_code == 200
    assert [(item["name"], item["number"]) for item in number_asc.json()] == [
        ("Venusaur", "15"),
        ("Pikachu", "58"),
    ]

    # number_desc
    number_desc = client.get("/cards/search", params={"set_id": "1", "sort_by": "number_desc", "hide_sealed": "true"})
    assert number_desc.status_code == 200
    assert [(item["name"], item["number"]) for item in number_desc.json()] == [
        ("Pikachu", "58"),
        ("Venusaur", "15"),
    ]


def test_search_cards_hide_sealed_defaults_to_true(client: TestClient) -> None:
    # By default, sealed products are hidden
    default_response = client.get("/cards/search", params={"set_id": "1"})
    assert default_response.status_code == 200
    assert len(default_response.json()) == 2
    assert all(item["name"] != "Base Set Booster Box" for item in default_response.json())

    # When hide_sealed=false, sealed products are included
    with_sealed = client.get("/cards/search", params={"set_id": "1", "hide_sealed": "false"})
    assert with_sealed.status_code == 200
    assert any(item["name"] == "Base Set Booster Box" for item in with_sealed.json())

    # sealed_only=true
    sealed_only = client.get("/cards/search", params={"set_id": "1", "sealed_only": "true"})
    assert sealed_only.status_code == 200
    assert len(sealed_only.json()) == 1
    assert sealed_only.json()[0]["name"] == "Base Set Booster Box"


def test_search_cards_price_filter(client: TestClient) -> None:
    # 1. Price range $10 to $50: matches Pikachu ($12.34), excludes Venusaur ($150) and unpriced Eevee
    mid_range = client.get("/cards/search", params={"min_price": "10", "max_price": "50", "hide_sealed": "true"})
    assert mid_range.status_code == 200
    names = [c["name"] for c in mid_range.json()]
    assert names == ["Pikachu"]

    # 2. Min price $100: matches Venusaur ($150)
    high_range = client.get("/cards/search", params={"min_price": "100", "hide_sealed": "true"})
    assert high_range.status_code == 200
    names = [c["name"] for c in high_range.json()]
    assert names == ["Venusaur"]

    # 3. Max price $5: no cards match
    under_5 = client.get("/cards/search", params={"max_price": "5", "hide_sealed": "true"})
    assert under_5.status_code == 200
    assert len(under_5.json()) == 0


def test_set_stats_price_filter(client: TestClient) -> None:
    # Full set 1 has Pikachu ($12.34) and Venusaur ($150.00) = $162.34
    full_stats = client.get("/cards/sets/1/stats", params={"hide_sealed": "true"})
    assert full_stats.status_code == 200
    assert full_stats.json()["priced_cards"] == 2
    assert full_stats.json()["total_price"] == 162.34

    # Filtered set 1 with price range $10 - $50 should only include Pikachu ($12.34)
    filtered_stats = client.get("/cards/sets/1/stats", params={"min_price": "10", "max_price": "50", "hide_sealed": "true"})
    assert filtered_stats.status_code == 200
    assert filtered_stats.json()["priced_cards"] == 1
    assert filtered_stats.json()["total_price"] == 12.34


def test_get_card_detail_and_image(client: TestClient) -> None:
    detail = client.get("/cards/pikachu-1")
    assert detail.status_code == 200
    assert detail.json()["set_name"] == "Base Set"
    assert detail.json()["image_url"] == "/cards/pikachu-1/image"

    image = client.get("/cards/pikachu-1/image")
    assert image.status_code == 200
    assert image.content == b"image-bytes"
    assert image.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_missing_card_returns_404(client: TestClient) -> None:
    assert client.get("/cards/missing").status_code == 404
    assert client.get("/cards/missing/prices").status_code == 404


def test_get_card_prices_returns_provider_state_and_observations(client: TestClient) -> None:
    response = client.get("/cards/pikachu-1/prices", params={"days": 30})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_states"][0]["provider"] == "tcgapi"
    assert payload["provider_states"][0]["match_status"] == "matched"
    assert payload["observations"][0]["price"] == 12.34
    assert payload["observations"][0]["condition"] == "Near Mint"
    assert len(payload["observations"]) == 1
    assert "avg_listing_price" in payload


class FakeMoverClient:
    def get_top_movers(self, game: str = "pokemon", direction: str = "up", period: str = "24h", limit: int = 20) -> dict:
        if direction == "up":
            return {
                "data": [
                    {
                        "card_id": "pikachu-1",
                        "name": "Pikachu",
                        "set_name": "Base Set",
                        "printing": "Normal",
                        "market_price": 25.00,
                        "price_change": 102.6,
                        "last_updated_at": "2026-08-29T12:00:00Z",
                    }
                ]
            }
        else:
            return {
                "data": [
                    {
                        "card_id": "venusaur-1",
                        "name": "Venusaur",
                        "set_name": "Base Set",
                        "printing": "Holofoil",
                        "market_price": 75.00,
                        "price_change": -50.0,
                        "last_updated_at": "2026-08-29T11:00:00Z",
                    }
                ]
            }


def test_get_market_movers_endpoint() -> None:
    from app.routers.cards import _MOVERS_LOCAL_FALLBACK, _get_redis
    _MOVERS_LOCAL_FALLBACK.clear()
    _r = _get_redis()
    if _r is not None:
        try:
            _r.delete("cardboarddex:movers:pokemon:24h")
        except Exception:
            pass
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", printed_total=102, release_date=date(1999, 1, 9)))
        session.add(Card(id="pikachu-1", name="Pikachu", set_id="1", number="58", printed_total=102, rarity="Common", image_url="https://tcgplayer-cdn.test/pikachu.jpg"))
        session.add(Card(id="venusaur-1", name="Venusaur", set_id="1", number="15", printed_total=102, rarity="Rare Holo", image_url="https://tcgplayer-cdn.test/venusaur.jpg"))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tcgapi_client] = lambda: FakeMoverClient()
    try:
        with TestClient(app) as test_client:
            res = test_client.get("/cards/market-movers?direction=all&period=24h&page=1&per_page=12")
            assert res.status_code == 200
            data = res.json()
            assert data["period"] == "24h"
            assert data["page"] == 1
            assert data["per_page"] == 12
            assert data["total_gainers"] == 1
            assert data["total_losers"] == 1
            assert data["total_pages"] == 1
            assert len(data["gainers"]) == 1
            assert data["gainers"][0]["card_id"] == "pikachu-1"
            assert data["gainers"][0]["name"] == "Pikachu"
            assert data["gainers"][0]["set_name"] == "Base Set"
            assert data["gainers"][0]["market_price"] == 25.0
            assert data["gainers"][0]["price_change_percentage"] == 102.6
            assert data["gainers"][0]["price_change_amount"] is not None
            assert data["gainers"][0]["direction"] == "up"

            assert len(data["losers"]) == 1
            assert data["losers"][0]["card_id"] == "venusaur-1"
            assert data["losers"][0]["direction"] == "down"
            assert data["losers"][0]["price_change_percentage"] == -50.0
    finally:
        _MOVERS_LOCAL_FALLBACK.clear()
        app.dependency_overrides.clear()


def test_get_market_movers_database_fallback() -> None:
    from app.routers.cards import _MOVERS_LOCAL_FALLBACK, _get_redis
    _MOVERS_LOCAL_FALLBACK.clear()
    _r = _get_redis()
    if _r is not None:
        try:
            _r.delete("cardboarddex:movers:pokemon:24h")
        except Exception:
            pass

    class EmptyMoverClient:
        def get_top_movers(self, game: str = "pokemon", direction: str = "up", period: str = "24h", limit: int = 50) -> dict[str, Any]:
            return {"data": []}

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", printed_total=102, release_date=date(1999, 1, 9)))
        session.add(Card(id="charizard-1", name="Charizard", set_id="1", number="4", printed_total=102, rarity="Rare Holo", image_url="https://tcgplayer-cdn.test/charizard.jpg"))
        session.add(Card(id="blastoise-1", name="Blastoise", set_id="1", number="2", printed_total=102, rarity="Rare Holo", image_url="https://tcgplayer-cdn.test/blastoise.jpg"))
        session.add(
            ProviderCardState(
                card_id="charizard-1",
                provider="tcgapi",
                match_status="matched",
                payload={"market_price": 350.0, "price_change_24h": 15.5},
            )
        )
        session.add(
            ProviderCardState(
                card_id="blastoise-1",
                provider="tcgapi",
                match_status="matched",
                payload={"market_price": 120.0, "price_change_24h": -8.0},
            )
        )
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tcgapi_client] = lambda: EmptyMoverClient()
    try:
        with TestClient(app) as test_client:
            res = test_client.get("/cards/market-movers?direction=all&period=24h&page=1&per_page=12")
            assert res.status_code == 200
            data = res.json()
            assert data["total_gainers"] == 1
            assert data["total_losers"] == 1
            assert data["gainers"][0]["card_id"] == "charizard-1"
            assert data["gainers"][0]["market_price"] == 350.0
            assert data["gainers"][0]["price_change_percentage"] == 15.5
            assert data["losers"][0]["card_id"] == "blastoise-1"
            assert data["losers"][0]["market_price"] == 120.0
            assert data["losers"][0]["price_change_percentage"] == -8.0
    finally:
        _MOVERS_LOCAL_FALLBACK.clear()
        app.dependency_overrides.clear()


def test_get_market_movers_historical_observations_fallback() -> None:
    from datetime import datetime, UTC, timedelta
    from app.routers.cards import _MOVERS_LOCAL_FALLBACK, _get_redis
    _MOVERS_LOCAL_FALLBACK.clear()
    _r = _get_redis()
    if _r is not None:
        try:
            _r.delete("cardboarddex:movers:pokemon:24h")
        except Exception:
            pass

    class EmptyMoverClient:
        def get_top_movers(self, game: str = "pokemon", direction: str = "up", period: str = "24h", limit: int = 50) -> dict[str, Any]:
            return {"data": []}

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", printed_total=102, release_date=date(1999, 1, 9)))
        session.add(Card(id="gengar-1", name="Gengar", set_id="1", number="5", printed_total=102, rarity="Rare Holo", image_url="https://tcgplayer-cdn.test/gengar.jpg"))
        session.add(Card(id="venusaur-1", name="Venusaur", set_id="1", number="15", printed_total=102, rarity="Rare Holo", image_url="https://tcgplayer-cdn.test/venusaur.jpg"))
        # Gengar went UP: 50 -> 80 (+60%)
        session.add(PriceObservation(fingerprint="g1", card_id="gengar-1", provider="tcgapi", provider_card_id="g1", variant_id="v1", price=50.0, observed_at=now - timedelta(days=2)))
        session.add(PriceObservation(fingerprint="g2", card_id="gengar-1", provider="tcgapi", provider_card_id="g1", variant_id="v1", price=80.0, observed_at=now))
        # Venusaur went DOWN: 100 -> 75 (-25%)
        session.add(PriceObservation(fingerprint="v1", card_id="venusaur-1", provider="tcgapi", provider_card_id="v1", variant_id="v1", price=100.0, observed_at=now - timedelta(days=2)))
        session.add(PriceObservation(fingerprint="v2", card_id="venusaur-1", provider="tcgapi", provider_card_id="v1", variant_id="v1", price=75.0, observed_at=now))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tcgapi_client] = lambda: EmptyMoverClient()
    try:
        with TestClient(app) as test_client:
            res = test_client.get("/cards/market-movers?direction=all&period=24h&page=1&per_page=12")
            assert res.status_code == 200
            data = res.json()
            assert data["total_gainers"] >= 1
            assert data["total_losers"] >= 1
            assert any(g["card_id"] == "gengar-1" and g["price_change_percentage"] == 60.0 for g in data["gainers"])
            assert any(l["card_id"] == "venusaur-1" and l["price_change_percentage"] == -25.0 for l in data["losers"])
    finally:
        _MOVERS_LOCAL_FALLBACK.clear()
        app.dependency_overrides.clear()


def test_get_grading_profit_endpoint() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", printed_total=102, release_date=date(1999, 1, 9)))
        session.add(Set(id="2", name="Team Up", series="Sun & Moon", printed_total=181, release_date=date(2019, 2, 1)))

        # Card 1: High profit Charizard
        session.add(Card(id="char-1", name="Charizard", set_id="1", number="4", printed_total=102, rarity="Rare Holo", image_url="https://tcgplayer-cdn.test/char.jpg"))
        # Raw price: $200
        session.add(PriceObservation(
            fingerprint="fp-char-raw",
            card_id="char-1",
            provider="tcgapi",
            provider_card_id="p-char",
            variant_id="raw",
            price=Decimal("200.00"),
            observed_at=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
        ))
        # PSA 10 price: $2000
        session.add(PriceObservation(
            fingerprint="fp-char-psa10",
            card_id="char-1",
            provider="ebay",
            provider_card_id="ebay-1",
            variant_id="psa10",
            grading_company="PSA",
            grade=Decimal("10.0"),
            price=Decimal("2000.00"),
            observed_at=datetime(2026, 8, 29, 11, 0, tzinfo=UTC),
        ))
        # PSA 9 price: $400
        session.add(PriceObservation(
            fingerprint="fp-char-psa9",
            card_id="char-1",
            provider="ebay",
            provider_card_id="ebay-2",
            variant_id="psa9",
            grading_company="PSA",
            grade=Decimal("9.0"),
            price=Decimal("400.00"),
            observed_at=datetime(2026, 8, 29, 11, 0, tzinfo=UTC),
        ))

        # Card 2: Safe flip Pikachu
        session.add(Card(id="pika-1", name="Pikachu", set_id="2", number="33", printed_total=181, rarity="Common", image_url="https://tcgplayer-cdn.test/pika.jpg"))
        session.add(PriceObservation(
            fingerprint="fp-pika-raw",
            card_id="pika-1",
            provider="tcgapi",
            provider_card_id="p-pika",
            variant_id="raw",
            price=Decimal("5.00"),
            observed_at=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
        ))
        session.add(PriceObservation(
            fingerprint="fp-pika-psa10",
            card_id="pika-1",
            provider="ebay",
            provider_card_id="ebay-3",
            variant_id="psa10",
            grading_company="PSA",
            grade=Decimal("10.0"),
            price=Decimal("150.00"),
            observed_at=datetime(2026, 8, 29, 11, 0, tzinfo=UTC),
        ))
        session.add(PriceObservation(
            fingerprint="fp-pika-psa9",
            card_id="pika-1",
            provider="ebay",
            provider_card_id="ebay-4",
            variant_id="psa9",
            grading_company="PSA",
            grade=Decimal("9.0"),
            price=Decimal("40.00"),
            observed_at=datetime(2026, 8, 29, 11, 0, tzinfo=UTC),
        ))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            # 1. Default query ($24.99 fee)
            res = test_client.get("/cards/grading-profit?page=1&per_page=10")
            assert res.status_code == 200
            data = res.json()
            assert data["total_cards"] == 2
            assert data["grading_fee"] == 24.99
            assert len(data["items"]) == 2

            # Top item should be Charizard ($2000 - $200 - $24.99 = $1775.01 profit)
            char = data["items"][0]
            assert char["card_id"] == "char-1"
            assert char["raw_price"] == 200.0
            assert char["psa10_price"] == 2000.0
            assert char["psa10_profit"] == 1775.01
            assert char["psa9_profit"] == 175.01
            assert char["psa9_safe"] is True
            assert char["spread_multiplier"] == 10.0

            # 2. Custom grading fee override ($20.00)
            res_fee = test_client.get("/cards/grading-profit?grading_fee=20.00")
            assert res_fee.status_code == 200
            data_fee = res_fee.json()
            assert data_fee["grading_fee"] == 20.0
            assert data_fee["items"][0]["psa10_profit"] == 1780.0

            # 3. Filter by set_id
            res_set = test_client.get("/cards/grading-profit?set_id=2")
            assert res_set.status_code == 200
            data_set = res_set.json()
            assert data_set["total_cards"] == 1
            assert data_set["items"][0]["card_id"] == "pika-1"

            # 4. Sort by PSA 10 ROI
            res_roi = test_client.get("/cards/grading-profit?sort_by=psa10_roi_desc")
            assert res_roi.status_code == 200
            data_roi = res_roi.json()
            assert len(data_roi["items"]) == 2

            # 5. Filter by max_raw_price (e.g. Budget Raw < $25)
            res_budget = test_client.get("/cards/grading-profit?max_raw_price=25.0")
            assert res_budget.status_code == 200
            data_budget = res_budget.json()
            assert data_budget["total_cards"] == 1
            assert data_budget["items"][0]["card_id"] == "pika-1"
            assert data_budget["items"][0]["raw_price"] <= 25.0

            # 6. Filter by min_spread (e.g. Highest Multiplier 20x+)
            res_spread = test_client.get("/cards/grading-profit?min_spread=20.0")
            assert res_spread.status_code == 200
            data_spread = res_spread.json()
            assert data_spread["total_cards"] == 1
            assert data_spread["items"][0]["card_id"] == "pika-1"
            assert data_spread["items"][0]["spread_multiplier"] >= 20.0
    finally:
        app.dependency_overrides.clear()


def test_get_sealed_signals_endpoint() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Scarlet & Violet", series="SV", release_date=date(2023, 3, 31)))
        session.add(Set(id="2", name="Surging Sparks", series="SV", release_date=date(2024, 11, 8)))

        # Sealed 1: Vintage Booster Box with low supply
        session.add(Card(id="box-1", name="Scarlet & Violet Booster Box", set_id="1", number="", rarity=None, image_url="https://tcgplayer-cdn.test/box1.jpg"))
        session.add(PriceObservation(
            fingerprint="fp-box-1",
            card_id="box-1",
            provider="tcgapi",
            provider_card_id="p-box-1",
            variant_id="sealed",
            price=Decimal("160.00"),
            payload={
                "market_price": 160.0,
                "low_price": 150.0,
                "median_price": 170.0,
                "lowest_with_shipping": 155.0,
                "buylist_price": 130.0,
                "total_listings": 8,
                "price_change_30d": 12.5,
            },
            observed_at=datetime.now(UTC),
        ))

        # Sealed 2: Surging Sparks ETB
        session.add(Card(id="etb-1", name="Surging Sparks Elite Trainer Box", set_id="2", number="", rarity=None, image_url="https://tcgplayer-cdn.test/etb1.jpg"))
        session.add(PriceObservation(
            fingerprint="fp-etb-1",
            card_id="etb-1",
            provider="tcgapi",
            provider_card_id="p-etb-1",
            variant_id="sealed",
            price=Decimal("55.00"),
            payload={
                "market_price": 55.0,
                "low_price": 50.0,
                "median_price": 58.0,
                "lowest_with_shipping": 52.0,
                "buylist_price": 40.0,
                "total_listings": 45,
                "price_change_30d": 2.0,
            },
            observed_at=datetime.now(UTC),
        ))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            res = test_client.get("/cards/sealed-signals?page=1&per_page=10")
            assert res.status_code == 200
            data = res.json()
            assert data["total_items"] == 2
            assert data["strong_buy_count"] >= 1
            assert len(data["items"]) == 2

            box = next(item for item in data["items"] if item["card_id"] == "box-1")
            assert box["product_type"] == "Booster Box"
            assert box["supply_rating"] == "Ultra Scarce"
            assert box["supply_score"] == 30
            assert box["signal_label"] == "STRONG BUY"
            assert box["signal_score"] >= 75

            etb = next(item for item in data["items"] if item["card_id"] == "etb-1")
            assert etb["product_type"] == "Elite Trainer Box"

            # Filter by product_type=booster_box
            res_box = test_client.get("/cards/sealed-signals?product_type=booster_box")
            assert res_box.status_code == 200
            data_box = res_box.json()
            assert data_box["total_items"] == 1
            assert data_box["items"][0]["card_id"] == "box-1"

            # Filter by signal=strong_buy
            res_sb = test_client.get("/cards/sealed-signals?signal=strong_buy")
            assert res_sb.status_code == 200
            assert res_sb.json()["total_items"] >= 1
    finally:
        app.dependency_overrides.clear()


def test_get_top_pokemon_volume_endpoint(client: TestClient) -> None:
    # 1. Default timeframe (7d) - aggregates real DB price observations
    res = client.get("/cards/top-pokemon-volume")
    assert res.status_code == 200
    data = res.json()
    assert data["timeframe"] == "7d"
    assert data["sort_by"] == "volume_desc"
    assert data["total_pokemon"] == 50
    assert data["total_volume_usd"] > 0
    assert data["total_sales_count"] > 0
    assert len(data["items"]) == 50

    # In fixture: Pikachu has $12.34 + $999.99 = $1012.33, Venusaur has $150.00
    # Dynamic ranking should place Pikachu #1, Venusaur #2
    assert data["items"][0]["rank"] == 1
    assert data["items"][0]["pokemon_name"] == "Pikachu"
    assert data["items"][0]["dex_number"] == 25
    assert "25.png" in data["items"][0]["sprite_url"]
    assert data["items"][0]["volume_usd"] == 1012.33
    assert data["items"][0]["volume_formatted"] == "$1.0K"
    assert data["items"][0]["sales_count"] == 2
    assert data["items"][0]["cards_count"] >= 1
    assert "momentum_percentage" in data["items"][0]
    assert "momentum_trend" in data["items"][0]

    assert data["items"][1]["rank"] == 2
    assert data["items"][1]["pokemon_name"] == "Venusaur"
    assert data["items"][1]["dex_number"] == 3
    assert data["items"][1]["volume_usd"] == 150.0
    assert data["items"][1]["sales_count"] == 1

    # 2. Filter with search query
    res_q = client.get("/cards/top-pokemon-volume?q=pika")
    assert res_q.status_code == 200
    data_q = res_q.json()
    names = [i["pokemon_name"] for i in data_q["items"]]
    assert "Pikachu" in names
    assert "Venusaur" not in names

    # 3. All-time timeframe
    res_at = client.get("/cards/top-pokemon-volume?timeframe=all_time")
    assert res_at.status_code == 200
    data_at = res_at.json()
    assert data_at["timeframe"] == "all_time"
    assert data_at["total_volume_usd"] >= data["total_volume_usd"]

    # 4. 24h and 30d timeframes
    res_24 = client.get("/cards/top-pokemon-volume?timeframe=24h")
    assert res_24.status_code == 200
    assert res_24.json()["timeframe"] == "24h"

    res_30 = client.get("/cards/top-pokemon-volume?timeframe=30d")
    assert res_30.status_code == 200
    assert res_30.json()["timeframe"] == "30d"

    # 5. Sorting by sales_desc
    res_sales = client.get("/cards/top-pokemon-volume?sort_by=sales_desc")
    assert res_sales.status_code == 200
    data_sales = res_sales.json()
    assert data_sales["sort_by"] == "sales_desc"
    assert data_sales["items"][0]["sales_count"] >= data_sales["items"][1]["sales_count"]


def test_get_live_updates_endpoint(client: TestClient) -> None:
    # 1. Default request
    res = client.get("/cards/live-updates?page=1&per_page=10")
    assert res.status_code == 200
    data = res.json()
    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["total_items"] > 0
    assert len(data["items"]) > 0

    item = data["items"][0]
    assert "id" in item
    assert "card_id" in item
    assert "card_name" in item
    assert "set_name" in item
    assert "provider" in item
    assert "price" in item
    assert item["price"] > 0

    # 2. Provider filter
    res_tcg = client.get("/cards/live-updates?provider=tcgapi")
    assert res_tcg.status_code == 200
    assert all(i["provider"] == "tcgapi" for i in res_tcg.json()["items"])

    # 3. Grade filter
    res_raw = client.get("/cards/live-updates?grade_filter=raw")
    assert res_raw.status_code == 200
    assert all(i["grading_company"] is None for i in res_raw.json()["items"])

    # 4. Search query
    res_search = client.get("/cards/live-updates?q=pikachu")
    assert res_search.status_code == 200
    assert all("pikachu" in i["card_name"].lower() or "base" in i["set_name"].lower() for i in res_search.json()["items"])


def test_pokemon_japan_support(client: TestClient) -> None:
    db = next(app.dependency_overrides[get_db]())
    try:
        db.add(Set(
            id="ja-1",
            name="VSTAR Universe",
            series="Pokemon Japan",
            printed_total=172,
            release_date=date(2022, 12, 2),
        ))
        db.add(Card(
            id="ja-charizard-1",
            name="Charizard VSTAR",
            set_id="ja-1",
            number="212/172",
            printed_total=172,
            rarity="SAR",
            image_url="https://tcgplayer-cdn.test/ja-charizard.jpg",
        ))
        db.commit()
    finally:
        db.close()

    # 1. Market movers with game=pokemon-japan
    res_movers = client.get("/cards/market-movers?game=pokemon-japan")
    assert res_movers.status_code == 200
    movers_data = res_movers.json()
    assert "gainers" in movers_data
    assert "losers" in movers_data

    # 2. Sets with game filter
    res_sets_en = client.get("/cards/sets?game=pokemon")
    assert res_sets_en.status_code == 200
    assert all(s.get("series") != "Pokemon Japan" for s in res_sets_en.json())

    res_sets_ja = client.get("/cards/sets?game=pokemon-japan")
    assert res_sets_ja.status_code == 200
    ja_sets = res_sets_ja.json()
    assert len(ja_sets) > 0
    assert all(s.get("series") == "Pokemon Japan" for s in ja_sets)

    # 3. Search with game filter
    res_search_en = client.get("/cards/search?game=pokemon&limit=10")
    assert res_search_en.status_code == 200
    assert all(c.get("set_name") != "VSTAR Universe" for c in res_search_en.json())

    res_search_ja = client.get("/cards/search?game=pokemon-japan&limit=10")
    assert res_search_ja.status_code == 200
    ja_cards = res_search_ja.json()
    assert len(ja_cards) > 0
    assert all(c.get("set_name") == "VSTAR Universe" for c in ja_cards)


def test_security_headers_present(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert res.headers["X-XSS-Protection"] == "1; mode=block"


def test_live_updates_wildcard_escaping(client: TestClient) -> None:
    # Query containing SQL wildcards % and _ should not crash or act as broad wildcards
    res = client.get("/cards/live-updates?q=%")
    assert res.status_code == 200
    assert res.json()["total_items"] == 0

    res_underscore = client.get("/cards/live-updates?q=_")
    assert res_underscore.status_code == 200
    assert res_underscore.json()["total_items"] == 0


def test_top_pokemon_volume_bulk_enrichment(client: TestClient) -> None:
    res = client.get("/cards/top-pokemon-volume?timeframe=all_time")
    assert res.status_code == 200
    data = res.json()
    assert data["total_pokemon"] == 50
    # Check Pikachu entry
    pika = next((p for p in data["items"] if p["pokemon_name"] == "Pikachu"), None)
    assert pika is not None
    assert pika["cards_count"] >= 1
    assert pika["top_card_name"] == "Pikachu"
    assert pika["top_card_price"] == 999.99


def test_get_pokemon_cards_success(client: TestClient) -> None:
    res = client.get("/cards/pokemon/Pikachu")
    assert res.status_code == 200
    data = res.json()
    assert data["pokemon_name"] == "Pikachu"
    assert data["total_cards"] >= 1
    assert len(data["cards"]) >= 1
    assert data["cards"][0]["name"] == "Pikachu"
    assert len(data["available_sets"]) >= 1
    assert data["available_sets"][0]["name"] == "Base Set"
    assert data["highest_price"] == 12.34


def test_get_pokemon_cards_set_filter(client: TestClient) -> None:
    # Set 1 has Pikachu, Set 2 (Jungle) does not
    res_set1 = client.get("/cards/pokemon/Pikachu?set_id=1")
    assert res_set1.status_code == 200
    assert len(res_set1.json()["cards"]) >= 1

    res_set2 = client.get("/cards/pokemon/Pikachu?set_id=2")
    assert res_set2.status_code == 200
    assert len(res_set2.json()["cards"]) == 0


def test_get_pokemon_cards_nonexistent(client: TestClient) -> None:
    res = client.get("/cards/pokemon/MissingNo")
    assert res.status_code == 200
    data = res.json()
    assert data["pokemon_name"] == "MissingNo"
    assert data["total_cards"] == 0
    assert data["highest_price"] is None
    assert data["lowest_price"] is None
    assert data["available_sets"] == []
    assert data["cards"] == []


def test_get_card_prices_computes_avg_listing_price() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", release_date=date(1999, 1, 9)))
        session.add(Card(id="char-1", name="Charizard", set_id="1", number="4", image_url="https://tcgplayer-cdn.test/char.jpg"))

        # Add two raw eBay listings: $200 and $300 -> avg should be $250.00
        session.add(PriceObservation(
            fingerprint="fp-ebay-1",
            card_id="char-1",
            provider="ebay",
            provider_card_id="ebay-101",
            variant_id="ebay:char-1:raw:standard",
            price=Decimal("200.00"),
            observed_at=datetime.now(UTC),
        ))
        session.add(PriceObservation(
            fingerprint="fp-ebay-2",
            card_id="char-1",
            provider="ebay",
            provider_card_id="ebay-102",
            variant_id="ebay:char-1:raw:standard",
            price=Decimal("300.00"),
            observed_at=datetime.now(UTC),
        ))
        # Add a graded eBay listing: $1500 (should be excluded because raw comps exist)
        session.add(PriceObservation(
            fingerprint="fp-ebay-3",
            card_id="char-1",
            provider="ebay",
            provider_card_id="ebay-103",
            variant_id="ebay:char-1:psa:10",
            grading_company="PSA",
            grade=Decimal("10.0"),
            price=Decimal("1500.00"),
            observed_at=datetime.now(UTC),
        ))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            res = test_client.get("/cards/char-1/prices")
            assert res.status_code == 200
            data = res.json()
            assert data["avg_listing_price"] == 250.0
    finally:
        app.dependency_overrides.clear()


def test_track_user_action_endpoint(client: TestClient) -> None:
    # 1. Track card click
    res = client.post("/cards/track-action", json={"entity_type": "card", "entity_id": "pikachu-1", "action": "click"})
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # 2. Track pokemon search
    res2 = client.post("/cards/track-action", json={"entity_type": "pokemon", "entity_id": "Charizard", "action": "search"})
    assert res2.status_code == 200
    assert res2.json() == {"status": "ok"}


def test_get_trending_dashboard_endpoint(client: TestClient) -> None:
    # First record some clicks
    client.post("/cards/track-action", json={"entity_type": "card", "entity_id": "pikachu-1", "action": "click"})
    client.post("/cards/track-action", json={"entity_type": "pokemon", "entity_id": "Pikachu", "action": "click"})

    # Fetch trending dashboard
    res = client.get("/cards/trending?timeframe=7d")
    assert res.status_code == 200
    data = res.json()

    assert data["timeframe"] == "7d"
    assert "trending_cards" in data
    assert "trending_pokemon" in data
    assert "volume_pokemon" in data
    assert len(data["trending_cards"]) >= 1
    assert len(data["trending_pokemon"]) >= 1
    assert len(data["volume_pokemon"]) >= 1

    # Check trending card structure
    top_card = data["trending_cards"][0]
    assert top_card["rank"] == 1
    assert "name" in top_card
    assert "set_name" in top_card
    assert "image_url" in top_card
    assert "trend_score" in top_card

    # Check trending pokemon structure
    top_poke = data["trending_pokemon"][0]
    assert "pokemon_name" in top_poke
    assert "sprite_url" in top_poke
    assert "trend_score" in top_poke

    # Check volume pokemon structure
    top_vol = data["volume_pokemon"][0]
    assert "volume_usd" in top_vol
    assert "sales_count" in top_vol

    # Test search filtering
    res_q = client.get("/cards/trending?q=pika")
    assert res_q.status_code == 200
    data_q = res_q.json()
    assert len(data_q["trending_pokemon"]) >= 1
    assert "Pikachu" in [p["pokemon_name"] for p in data_q["trending_pokemon"]]
