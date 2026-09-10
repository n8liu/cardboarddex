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


def test_price_collection_uses_only_tcgapi_and_stores_printing_variants() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="55", name="Obsidian Flames"))
        session.add(Card(id="123", name="Charizard ex", set_id="55", number="006"))
        session.commit()

        result = run_price_collection(session, limit=1, tcgapi=FakeTCGAPIClient())  # type: ignore[arg-type]

        observations = list(session.scalars(select(PriceObservation).order_by(PriceObservation.price)))
        state = session.scalar(select(ProviderCardState))

    assert result == {"cards": 1, "tcgapi_observations": 2, "provider_errors": 0}
    assert [item.provider for item in observations] == ["tcgapi", "tcgapi"]
    assert [item.printing for item in observations] == ["Normal", "Foil"]
    assert observations[0].payload is not None
    assert observations[0].payload["low_price"] == 21.00
    assert observations[0].payload["price_change_24h"] == 1.5
    assert state is not None and state.match_method == "canonical_tcgapi_id"


class FakeBulkTCGAPIClient:
    def __init__(self) -> None:
        self.bulk_calls = 0

    def get_bulk_prices(self, card_ids: list[str]) -> dict:
        self.bulk_calls += 1
        return {
            "data": [
                {
                    "card_id": 101,
                    "printing": "Normal",
                    "market_price": 50.00,
                    "low_price": 45.00,
                    "last_updated_at": "2026-08-28T07:00:00.000Z",
                },
                {
                    "card_id": 102,
                    "printing": "Normal",
                    "market_price": 30.00,
                    "low_price": 28.00,
                    "last_updated_at": "2026-08-28T07:00:00.000Z",
                },
            ]
        }


def test_bulk_price_collection_processes_multiple_cards_in_single_request() -> None:
    collect_prices._BULK_PRICES_SUPPORTED = True
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set"))
        session.add(Card(id="101", name="Pikachu", set_id="1", number="1"))
        session.add(Card(id="102", name="Raichu", set_id="1", number="2"))
        session.commit()

        client = FakeBulkTCGAPIClient()
        result = run_price_collection(session, limit=2, tcgapi=client)  # type: ignore[arg-type]

        observations = list(session.scalars(select(PriceObservation).order_by(PriceObservation.price)))

    assert client.bulk_calls == 1  # 1 single bulk API call for all cards!
    assert result["cards"] == 2
    assert result["tcgapi_observations"] == 2
    assert result["provider_errors"] == 0
    assert len(observations) == 2
    assert observations[0].price == 30.00
    assert observations[1].price == 50.00


class FakeForbiddenBulkClient:
    def __init__(self) -> None:
        self.bulk_calls = 0
        self.individual_calls = 0

    def get_bulk_prices(self, card_ids: list[str]) -> dict:
        self.bulk_calls += 1
        request = httpx.Request("GET", "https://api.tcgapi.dev/v1/bulk/prices")
        response = httpx.Response(403, request=request, json={"error": {"message": "Pro tier or higher required", "code": "TIER_REQUIRED"}})
        raise httpx.HTTPStatusError("Client error '403 Forbidden'", request=request, response=response)

    def get_card(self, card_id: str) -> dict:
        self.individual_calls += 1
        return {"data": {
            "id": card_id,
            "name": "Pikachu" if card_id == "101" else "Raichu",
            "number": "1" if card_id == "101" else "2",
            "set_name": "Base Set",
        }}

    def get_card_prices(self, card_id: str, printing: str | None = None) -> dict:
        return {"data": [
            {
                "card_id": card_id,
                "printing": "Normal",
                "market_price": 50.00 if card_id == "101" else 30.00,
                "last_updated_at": "2026-08-28T07:00:00.000Z",
            }
        ]}


def test_bulk_price_collection_403_falls_back_to_individual_collection() -> None:
    collect_prices._BULK_PRICES_SUPPORTED = True
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set"))
        session.add(Card(id="101", name="Pikachu", set_id="1", number="1"))
        session.add(Card(id="102", name="Raichu", set_id="1", number="2"))
        session.commit()

        client = FakeForbiddenBulkClient()
        result = run_price_collection(session, limit=2, tcgapi=client)  # type: ignore[arg-type]

        observations = list(session.scalars(select(PriceObservation).order_by(PriceObservation.price)))

    assert client.bulk_calls == 1
    assert client.individual_calls == 2
    assert result["cards"] == 2
    assert result["tcgapi_observations"] == 2
    assert result["provider_errors"] == 0
    assert len(observations) == 2
    assert collect_prices._BULK_PRICES_SUPPORTED is False

