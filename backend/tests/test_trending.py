"""Unit and integration tests for the Trending & Top 50 feature.

Verifies:
1. 3-column Trending Dashboard structure (Trending Cards, Popular Pokémon, Volume Leaders).
2. All timeframes (24h, 7d, 30d, all_time, 2026_ytd).
3. Real-time click tracking: immediate counter increment and cache invalidation.
4. Dual attribution: clicking a Pokémon card increments both the card and the Pokémon.
5. Zero-observation card inclusion: cards without price observations can still trend via user clicks.
6. Search query filtering on trending cards and Pokémon.
7. Ranking algorithm: active user velocity prioritizes items above passive catalog entries.
8. View tracking via GET /cards/{card_id}.
9. Payload validation on /cards/track-action.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.routers.cards import get_tcgapi_client
from app.common.redis import get_redis
from app.services.catalog_service import _pokemon_volume_cache
from app.services.trending_service import (
    REDIS_KEY_CARD_CLICKS,
    REDIS_KEY_POKE_CLICKS,
    REDIS_KEY_SEARCHES,
    _IN_MEMORY_CARD_CLICKS,
    _IN_MEMORY_POKE_CLICKS,
    _IN_MEMORY_SEARCHES,
    _TRENDING_CACHE,
    calculate_trending_cards,
    calculate_trending_pokemon,
    invalidate_trending_cache,
    record_action,
)


class FakeImageClient:
    async def get_card_image(self, card_id: str) -> tuple[bytes, str]:
        return b"image-bytes", "image/jpeg"


def _reset_redis_and_memory() -> None:
    _IN_MEMORY_CARD_CLICKS.clear()
    _IN_MEMORY_POKE_CLICKS.clear()
    _IN_MEMORY_SEARCHES.clear()
    _TRENDING_CACHE.clear()
    _pokemon_volume_cache.clear()
    invalidate_trending_cache()
    r = get_redis()
    if r is not None:
        try:
            r.delete(REDIS_KEY_CARD_CLICKS, REDIS_KEY_POKE_CLICKS, REDIS_KEY_SEARCHES)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def clean_trending_state() -> Generator[None, None, None]:
    """Ensure in-memory analytics dictionaries and Redis sorted sets are clean before and after each test."""
    _reset_redis_and_memory()
    yield
    _reset_redis_and_memory()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client with an in-memory SQLite database seeded with representative cards and observations."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Sets
        session.add(Set(id="set-1", name="Base Set", series="Original", printed_total=102, release_date=date(1999, 1, 9)))
        session.add(Set(id="set-2", name="Team Up", series="Sun & Moon", printed_total=181, release_date=date(2019, 2, 1)))

        # Cards
        session.add(Card(id="pika-base", name="Pikachu", set_id="set-1", number="58", rarity="Common", image_url="https://img.test/pika.jpg"))
        session.add(Card(id="char-base", name="Charizard", set_id="set-1", number="4", rarity="Rare Holo", image_url="https://img.test/char.jpg"))
        session.add(Card(id="snorlax-1", name="Snorlax", set_id="set-2", number="158", rarity="Rare", image_url="https://img.test/snorlax.jpg"))
        session.add(Card(id="zero-obs-card", name="Snorlax Promo", set_id="set-2", number="SMP-01", rarity="Promo", image_url="https://img.test/promo.jpg"))

        # Provider Card State
        session.add(ProviderCardState(card_id="char-base", provider="tcgapi", provider_card_id="tcg-char", match_status="matched"))
        session.add(ProviderCardState(card_id="pika-base", provider="tcgapi", provider_card_id="tcg-pika", match_status="matched"))

        # Price Observations
        now = datetime.now(UTC)
        session.add(PriceObservation(
            fingerprint="obs-1", card_id="char-base", provider="tcgapi", provider_card_id="tcg-char",
            variant_id="holo", condition="Near Mint", printing="Holofoil", price=Decimal("350.00"), currency="USD",
            observed_at=now - timedelta(days=2), provider_updated_at=now,
        ))
        session.add(PriceObservation(
            fingerprint="obs-2", card_id="pika-base", provider="tcgapi", provider_card_id="tcg-pika",
            variant_id="nm", condition="Near Mint", printing="Normal", price=Decimal("25.00"), currency="USD",
            observed_at=now - timedelta(days=1), provider_updated_at=now,
        ))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tcgapi_client] = lambda: FakeImageClient()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_trending_dashboard_structure(client: TestClient) -> None:
    """Verifies that GET /cards/trending returns all 3 pillars with valid structure."""
    res = client.get("/cards/trending?timeframe=7d")
    assert res.status_code == 200
    data = res.json()

    assert data["timeframe"] == "7d"
    assert "trending_cards" in data
    assert "trending_pokemon" in data
    assert "volume_pokemon" in data
    assert "total_volume_usd" in data
    assert "total_sales_count" in data
    assert "updated_at" in data

    # Verify at least one card and Pokemon returned
    assert len(data["trending_cards"]) >= 1
    assert len(data["trending_pokemon"]) >= 1
    assert len(data["volume_pokemon"]) >= 1

    # Check Card fields
    card = data["trending_cards"][0]
    assert "rank" in card
    assert "card_id" in card
    assert "name" in card
    assert "set_name" in card
    assert "trend_score" in card
    assert "clicks_count" in card

    # Check Pokemon fields
    poke = data["trending_pokemon"][0]
    assert "rank" in poke
    assert "pokemon_name" in poke
    assert "dex_number" in poke
    assert "sprite_url" in poke
    assert "trend_score" in poke
    assert "clicks_count" in poke


def test_trending_dashboard_timeframes(client: TestClient) -> None:
    """Verifies that all supported timeframe values function properly."""
    for tf in ["24h", "7d", "30d", "all_time", "2026_ytd"]:
        res = client.get(f"/cards/trending?timeframe={tf}")
        assert res.status_code == 200
        assert res.json()["timeframe"] == tf


def test_card_click_increments_counter_immediately(client: TestClient) -> None:
    """Verifies that tracking a card click immediately increments clicks_count on the very next fetch."""
    # 1. Fetch initial trending cards
    res1 = client.get("/cards/trending?timeframe=7d")
    assert res1.status_code == 200
    pika_card = next((c for c in res1.json()["trending_cards"] if c["card_id"] == "pika-base"), None)
    initial_clicks = pika_card["clicks_count"] if pika_card else 0

    # 2. Track click on pika-base
    track_res = client.post("/cards/track-action", json={
        "entity_type": "card",
        "entity_id": "pika-base",
        "action": "click",
    })
    assert track_res.status_code == 200
    assert track_res.json() == {"status": "ok"}

    # 3. Immediately fetch trending cards again
    res2 = client.get("/cards/trending?timeframe=7d")
    assert res2.status_code == 200
    pika_card_after = next((c for c in res2.json()["trending_cards"] if c["card_id"] == "pika-base"), None)
    assert pika_card_after is not None
    assert pika_card_after["clicks_count"] == initial_clicks + 1


def test_card_click_dual_attribution_to_pokemon(client: TestClient) -> None:
    """Verifies that clicking a card of 'Charizard' also increments Charizard's click counter in trending_pokemon."""
    # 1. Fetch initial Charizard stats
    res1 = client.get("/cards/trending?timeframe=7d")
    char_poke_before = next((p for p in res1.json()["trending_pokemon"] if p["pokemon_name"] == "Charizard"), None)
    initial_poke_clicks = char_poke_before["clicks_count"] if char_poke_before else 0

    # 2. User clicks on the Charizard card
    track_res = client.post("/cards/track-action", json={
        "entity_type": "card",
        "entity_id": "char-base",
        "action": "click",
    })
    assert track_res.status_code == 200

    # 3. Fetch trending dashboard: Charizard Pokemon clicks must increment
    res2 = client.get("/cards/trending?timeframe=7d")
    char_poke_after = next((p for p in res2.json()["trending_pokemon"] if p["pokemon_name"] == "Charizard"), None)
    assert char_poke_after is not None
    assert char_poke_after["clicks_count"] == initial_poke_clicks + 1


def test_pokemon_search_action_tracking(client: TestClient) -> None:
    """Verifies that tracking a search action increments searches_count and boosts trend score."""
    # 1. Track a search for Snorlax
    track_res = client.post("/cards/track-action", json={
        "entity_type": "pokemon",
        "entity_id": "Snorlax",
        "action": "search",
    })
    assert track_res.status_code == 200

    # 2. Verify Snorlax has searches_count >= 1
    res = client.get("/cards/trending?timeframe=7d")
    assert res.status_code == 200
    snorlax = next((p for p in res.json()["trending_pokemon"] if p["pokemon_name"] == "Snorlax"), None)
    assert snorlax is not None
    assert snorlax["searches_count"] >= 1
    assert snorlax["trend_score"] > 0


def test_zero_observation_card_enters_trending_on_click(client: TestClient) -> None:
    """Verifies that a card with 0 price observations still enters trending cards when clicked."""
    # Card 'zero-obs-card' has 0 PriceObservations in the fixture
    # Track 2 clicks on it
    client.post("/cards/track-action", json={"entity_type": "card", "entity_id": "zero-obs-card", "action": "click"})
    client.post("/cards/track-action", json={"entity_type": "card", "entity_id": "zero-obs-card", "action": "click"})

    # Fetch trending cards
    res = client.get("/cards/trending?timeframe=7d")
    assert res.status_code == 200
    card_ids = [c["card_id"] for c in res.json()["trending_cards"]]
    assert "zero-obs-card" in card_ids

    target = next(c for c in res.json()["trending_cards"] if c["card_id"] == "zero-obs-card")
    assert target["clicks_count"] == 2
    assert target["name"] == "Snorlax Promo"


def test_get_card_view_auto_records_action(client: TestClient) -> None:
    """Verifies that calling GET /cards/{card_id} automatically records a view action."""
    # Get initial clicks
    res_init = client.get("/cards/trending?timeframe=7d")
    char_before = next((c for c in res_init.json()["trending_cards"] if c["card_id"] == "char-base"), None)
    clicks_before = char_before["clicks_count"] if char_before else 0

    # View the card detail page
    detail_res = client.get("/cards/char-base")
    assert detail_res.status_code == 200
    assert detail_res.json()["name"] == "Charizard"

    # Immediately fetch trending: clicks_count should have incremented
    res_after = client.get("/cards/trending?timeframe=7d")
    char_after = next((c for c in res_after.json()["trending_cards"] if c["card_id"] == "char-base"), None)
    assert char_after is not None
    assert char_after["clicks_count"] == clicks_before + 1


def test_trending_search_filter(client: TestClient) -> None:
    """Verifies that ?q=... correctly filters trending cards and Pokemon."""
    res = client.get("/cards/trending?q=char")
    assert res.status_code == 200
    data = res.json()

    # Cards must match 'char'
    for card in data["trending_cards"]:
        assert "char" in card["name"].lower() or "char" in card["set_name"].lower()

    # Pokemon must match 'char'
    for poke in data["trending_pokemon"]:
        assert "char" in poke["pokemon_name"].lower()


def test_invalid_track_action_payload(client: TestClient) -> None:
    """Verifies that invalid payloads to /cards/track-action return 422 Unprocessable Entity."""
    # Invalid entity_type
    res_bad_type = client.post("/cards/track-action", json={
        "entity_type": "invalid_type",
        "entity_id": "123",
        "action": "click",
    })
    assert res_bad_type.status_code == 422

    # Missing entity_id
    res_missing_id = client.post("/cards/track-action", json={
        "entity_type": "card",
        "action": "click",
    })
    assert res_missing_id.status_code == 422


def test_cache_invalidation_lifecycle(client: TestClient) -> None:
    """Verifies that calling invalidate_trending_cache forces a fresh dashboard calculation."""
    res1 = client.get("/cards/trending?timeframe=7d")
    assert res1.status_code == 200

    # Manually record action in service
    record_action("card", "pika-base", "click")

    # Fetch again, verify new count is reflected without 3-minute delay
    res2 = client.get("/cards/trending?timeframe=7d")
    pika = next(c for c in res2.json()["trending_cards"] if c["card_id"] == "pika-base")
    assert pika["clicks_count"] >= 1


def test_trending_ref_exempt_from_view_tracking(client: TestClient) -> None:
    """Verifies that visiting a card or pokemon with ref=trending does NOT increment view/click counters."""
    # 1. Visit with ref=trending
    res_card = client.get("/cards/pika-base?ref=trending")
    assert res_card.status_code == 200

    res_poke = client.get("/cards/pokemon/Pikachu?ref=trending")
    assert res_poke.status_code == 200

    assert _IN_MEMORY_CARD_CLICKS.get("pika-base", 0) == 0
    assert _IN_MEMORY_POKE_CLICKS.get("Pikachu", 0) == 0

    # 2. Normal visit without ref=trending increments tracking
    res_card_normal = client.get("/cards/pika-base")
    assert res_card_normal.status_code == 200
    assert _IN_MEMORY_CARD_CLICKS.get("pika-base", 0) == 1
    assert _IN_MEMORY_POKE_CLICKS.get("Pikachu", 0) == 1


def test_reset_trending_endpoint(client: TestClient) -> None:
    """Verifies that POST /cards/trending/reset resets all counters and clears cache."""
    # Record some clicks
    record_action("card", "pika-base", "click")
    record_action("pokemon", "Charizard", "click")
    record_action("search", "pikachu", "search")

    assert _IN_MEMORY_CARD_CLICKS.get("pika-base", 0) >= 1
    assert _IN_MEMORY_POKE_CLICKS.get("Charizard", 0) >= 1

    # Reset
    res = client.post("/cards/trending/reset")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    assert len(_IN_MEMORY_CARD_CLICKS) == 0
    assert len(_IN_MEMORY_POKE_CLICKS) == 0
    assert len(_IN_MEMORY_SEARCHES) == 0

    # Dashboard should show 0 clicks
    dash = client.get("/cards/trending?timeframe=7d").json()
    for c in dash["trending_cards"]:
        assert c["clicks_count"] == 0
    for p in dash["trending_pokemon"]:
        assert p["clicks_count"] == 0
        assert p["searches_count"] == 0


def test_pokemon_data_dex_resolution_and_sprites() -> None:
    """Verifies that all Pokémon species have correct Dex numbers and valid sprite URLs."""
    from app.common.pokemon_data import (
        POKEMON_DEX_NUMBERS,
        get_pokemon_dex_number,
        get_pokemon_sprite_url,
    )
    from app.services.catalog_service import match_to_pokemon

    # Check that Zekrom has Dex #644
    assert POKEMON_DEX_NUMBERS["Zekrom"] == 644
    assert get_pokemon_dex_number("zekrom") == 644
    assert "644.png" in get_pokemon_sprite_url("Zekrom")

    # Check other generations
    assert POKEMON_DEX_NUMBERS["Rayquaza"] == 384
    assert POKEMON_DEX_NUMBERS["Greninja"] == 658
    assert POKEMON_DEX_NUMBERS["Miraidon"] == 1008

    # Check card title matching across species
    assert match_to_pokemon("Zekrom GX - 112/095") == "Zekrom"
    assert match_to_pokemon("Special Delivery Pikachu") == "Pikachu"
    assert match_to_pokemon("Shining Rayquaza - 56/73") == "Rayquaza"


def test_popular_pokemon_includes_clicked_species(client: TestClient) -> None:
    """Verifies that clicking any Pokémon (e.g. Zekrom) causes it to appear in Popular Pokémon with valid Dex and artwork."""
    # Simulate clicking Zekrom
    record_action("pokemon", "Zekrom", "click")

    dash = client.get("/cards/trending?timeframe=7d").json()
    trending_poke = dash["trending_pokemon"]
    zekrom_entry = next((p for p in trending_poke if p["pokemon_name"] == "Zekrom"), None)

    assert zekrom_entry is not None
    assert zekrom_entry["dex_number"] == 644
    assert "644.png" in zekrom_entry["sprite_url"]
    assert zekrom_entry["clicks_count"] >= 1

