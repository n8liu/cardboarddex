from datetime import date
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Card, Set
from app.services.catalog_service import get_cards_for_pokemon
from jobs import collect_prices
from jobs.cycle_prices import run_price_cycle
from jobs.update_pokemon import update_cards_for_pokemon


def _setup_test_db() -> Session:
    collect_prices._BULK_PRICES_SUPPORTED = True
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    base_set = Set(id="base1", name="Base Set", series="Base", printed_total=102, release_date=date(1999, 1, 9))
    jungle_set = Set(id="base2", name="Jungle", series="Base", printed_total=64, release_date=date(1999, 6, 16))
    session.add_all([base_set, jungle_set])

    cards = [
        Card(id="pika-1", name="Pikachu", set_id="base1", number="58", printed_total=102, rarity="Common"),
        Card(id="pika-2", name="Flying Pikachu", set_id="base1", number="113", printed_total=102, rarity="Secret Rare"),
        Card(id="pika-code", name="Pikachu Code Card", set_id="base1", number="CODE", printed_total=102, rarity="Code Card"),
        Card(id="char-1", name="Charizard", set_id="base1", number="4", printed_total=102, rarity="Rare Holo"),
        Card(id="mew-1", name="Mew", set_id="base2", number="8", printed_total=64, rarity="Rare"),
        Card(id="mewtwo-1", name="Mewtwo", set_id="base1", number="10", printed_total=102, rarity="Rare Holo"),
        Card(id="tag-1", name="Mew & Mewtwo-GX", set_id="base2", number="71", printed_total=64, rarity="Ultra Rare"),
    ]
    session.add_all(cards)
    session.commit()
    return session


def test_get_cards_for_pokemon_matches_and_filters() -> None:
    session = _setup_test_db()

    # Query Pikachu
    pikachu_cards = get_cards_for_pokemon(session, "Pikachu")
    pika_ids = [c.id for c in pikachu_cards]
    assert "pika-1" in pika_ids
    assert "pika-2" in pika_ids
    # Code cards must be excluded
    assert "pika-code" not in pika_ids
    assert "char-1" not in pika_ids


def test_get_cards_for_pokemon_mew_boundary() -> None:
    session = _setup_test_db()

    mew_cards = get_cards_for_pokemon(session, "Mew")
    mew_ids = [c.id for c in mew_cards]
    assert "mew-1" in mew_ids
    assert "tag-1" in mew_ids  # Tag team allowed
    assert "mewtwo-1" not in mew_ids  # Mewtwo excluded from Mew

    mewtwo_cards = get_cards_for_pokemon(session, "Mewtwo")
    mewtwo_ids = [c.id for c in mewtwo_cards]
    assert "mewtwo-1" in mewtwo_ids


def test_update_cards_for_pokemon_full() -> None:
    session = _setup_test_db()

    mock_tcgapi = MagicMock()
    mock_tcgapi.get_bulk_prices.return_value = {
        "data": [
            {
                "card_id": "pika-1",
                "printing": "Normal",
                "market_price": 12.00,
                "last_updated_at": "2026-09-01T00:00:00Z",
            },
            {
                "card_id": "pika-2",
                "printing": "Holofoil",
                "market_price": 55.00,
                "last_updated_at": "2026-09-01T00:00:00Z",
            },
        ]
    }

    mock_ebay = MagicMock()
    mock_ebay.search_item_summaries.return_value = [
        {
            "itemId": "v1|123456789|0",
            "title": "Pikachu Base Set 58/102 Pokemon Card Mint",
            "price": {"value": "15.00", "currency": "USD"},
            "itemWebUrl": "https://www.ebay.com/itm/123456789",
            "itemEndDate": "2026-09-01T12:00:00.000Z",
        }
    ]

    res = update_cards_for_pokemon(
        session=session,
        pokemon_name="Pikachu",
        delay_seconds=0.0,
        tcgapi_client=mock_tcgapi,
        ebay_client=mock_ebay,
    )

    assert res["pokemon"] == "Pikachu"
    assert res["total_cards"] == 2  # pika-1 and pika-2 (code card filtered)
    assert res["tcgapi_observations"] >= 2
    assert res["ebay_raw_listings"] >= 2
    assert res["ebay_observations"] >= 1
    assert res["tcgapi_errors"] == 0
    assert res["ebay_errors"] == 0


def test_update_cards_for_pokemon_modes() -> None:
    session = _setup_test_db()

    mock_tcgapi = MagicMock()
    mock_tcgapi.get_bulk_prices.return_value = {"data": []}
    mock_ebay = MagicMock()
    mock_ebay.search_item_summaries.return_value = []

    # 1. tcg_only
    res_tcg = update_cards_for_pokemon(
        session=session,
        pokemon_name="Charizard",
        tcg_only=True,
        delay_seconds=0.0,
        tcgapi_client=mock_tcgapi,
        ebay_client=mock_ebay,
    )
    assert res_tcg["total_cards"] == 1
    assert mock_tcgapi.get_bulk_prices.called
    assert not mock_ebay.search_item_summaries.called

    # 2. ebay_only
    mock_tcgapi.reset_mock()
    mock_ebay.reset_mock()
    res_ebay = update_cards_for_pokemon(
        session=session,
        pokemon_name="Charizard",
        ebay_only=True,
        delay_seconds=0.0,
        tcgapi_client=mock_tcgapi,
        ebay_client=mock_ebay,
    )
    assert res_ebay["total_cards"] == 1
    assert not mock_tcgapi.get_bulk_prices.called
    assert mock_ebay.search_item_summaries.called


def test_run_price_cycle_with_pokemon() -> None:
    session = _setup_test_db()

    mock_tcgapi = MagicMock()
    mock_tcgapi.get_bulk_prices.return_value = {
        "data": [
            {
                "card_id": "pika-1",
                "printing": "Normal",
                "market_price": 10.0,
            }
        ]
    }
    mock_ebay = MagicMock()
    mock_ebay.search_item_summaries.return_value = []

    cycle_res = run_price_cycle(
        session=session,
        pokemon="Pikachu",
        tcgapi_client=mock_tcgapi,
        ebay_client=mock_ebay,
    )

    assert cycle_res["status"] == "completed"
    assert cycle_res["pokemon"] == "Pikachu"
    assert "pika-1" in cycle_res["card_ids"]
    assert cycle_res["tcgapi"]["cards"] >= 2
