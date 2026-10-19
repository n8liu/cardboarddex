from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Card, PriceObservation, ProviderCardState, Set
import httpx
from jobs import collect_prices
from jobs.collect_prices import (
    _observation,
    normalize_number,
    normalize_text,
    run_price_collection,
    select_exact_candidates,
)


def test_normalization_handles_provider_formatting() -> None:
    assert normalize_text("Base Set (Shadowless)") == "base set shadowless"
    assert normalize_number("004/102") == "4"
    assert normalize_number("H29/H32") == "h29"


def test_exact_candidate_requires_name_set_and_number() -> None:
    card = SimpleNamespace(name="Charizard", number="004")
    items = [
        {"name": "Charizard", "set": {"name": "Base Set"}, "number": "4/102"},
        {"name": "Charizard", "set": {"name": "Base Set 2"}, "number": "4/130"},
        {"name": "Charizard ex", "set": {"name": "Base Set"}, "number": "4/102"},
    ]
    result = select_exact_candidates(
        items, card, "Base Set", name_field="name", set_field="set", number_field="number"
    )
    assert result == [items[0]]


def test_observation_deduplicates_current_and_history_point_in_one_transaction() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        session.add(Set(id="set", name="Set"))
        session.add(Card(id="card", name="Card", set_id="set", number="1"))
        session.commit()
        values = dict(
            card_id="card", provider="tcgapi", provider_card_id="provider-card",
            variant_id="variant", price="10.00",
        )
        assert _observation(session, **values)
        assert not _observation(session, **values)
        session.commit()
        assert session.scalar(select(func.count()).select_from(PriceObservation)) == 1


class FakeTCGAPIClient:
    def get_card(self, card_id: str) -> dict:
        assert card_id == "123"
        return {"data": {
            "id": 123,
            "name": "Charizard ex",
            "number": "006",
            "set_name": "Obsidian Flames",
        }}

    def get_card_prices(self, card_id: str, printing: str | None = None) -> dict:
        assert card_id == "123"
        return {"data": [
            {
                "card_id": 123,
                "printing": "Normal",
                "market_price": 24.99,
                "low_price": 21.00,
                "median_price": 25.50,
                "lowest_with_shipping": 22.50,
                "buylist_price": 18.00,
                "price_change_24h": 1.5,
                "price_change_7d": -2.1,
                "price_change_30d": 12.0,
                "last_updated_at": "2026-08-28T07:00:00.000Z",
            },
            {
                "card_id": 123,
                "printing": "Foil",
                "market_price": 42.50,
                "low_price": 39.00,
                "median_price": 44.00,
                "lowest_with_shipping": 41.00,
                "buylist_price": 32.00,
                "price_change_24h": 0.5,
                "price_change_7d": 4.2,
                "price_change_30d": 18.5,
                "last_updated_at": "2026-08-28T07:00:00.000Z",
            },
        ]}


def test_legacy_collection_is_disabled_even_with_injected_client():
    from unittest.mock import Mock
    client = Mock()
    assert run_price_collection(Mock(), tcgapi=client)["status"] == "disabled"
    assert client.mock_calls == []
