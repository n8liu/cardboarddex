from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.services.portfolio_service import (
    _PORTFOLIO_LOCAL_FALLBACK,
    calculate_portfolio_valuation,
)


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean_portfolio_cache() -> None:
    _PORTFOLIO_LOCAL_FALLBACK.clear()


def test_portfolio_empty_ids(test_db: Session) -> None:
    res = calculate_portfolio_valuation(test_db, [])
    assert res.total_cards == 0
    assert res.total_current_value == 0.0
    assert res.cards == []
    assert res.history == []
    assert res.highest_value_card is None


def test_portfolio_single_card_valuation(test_db: Session) -> None:
    now = datetime.now(UTC)
    s = Set(id="base1", name="Base Set", release_date=date(1999, 1, 9))
    test_db.add(s)

    c = Card(
        id="c1",
        set_id="base1",
        name="Charizard",
        number="4",
        printed_total=102,
        rarity="Rare Holo",
    )
    test_db.add(c)

    # Add provider state with deltas
    state = ProviderCardState(
        provider="tcgapi",
        card_id="c1",
        match_status="matched",
        last_synced_at=now,
        payload={
            "prices": {
                "market_price": 350.0,
                "price_change_24h": 15.0,
                "price_change_7d": 45.0,
                "price_change_30d": 90.0,
            }
        },
    )
    test_db.add(state)

    # Add historical observation 3 days ago
    obs = PriceObservation(
        fingerprint="fp-c1-1",
        provider="tcgapi",
        provider_card_id="c1",
        card_id="c1",
        variant_id="c1:normal",
        price=Decimal("335.0"),
        currency="USD",
        observed_at=now - timedelta(days=3),
    )
    test_db.add(obs)
    test_db.commit()

    res = calculate_portfolio_valuation(test_db, ["c1"])
    assert res.total_cards == 1
    assert res.total_current_value == 350.0
    assert res.highest_value_card is not None
    assert res.highest_value_card.name == "Charizard"
    assert res.highest_value_card.market_price == 350.0
    assert len(res.history) >= 1
    # Latest point in history matches current total value
    assert res.history[-1].total_value == 350.0


def test_portfolio_multi_card_aggregation(test_db: Session) -> None:
    now = datetime.now(UTC)
    s = Set(id="base1", name="Base Set", release_date=date(1999, 1, 9))
    test_db.add(s)

    c1 = Card(id="c1", set_id="base1", name="Charizard", number="4", rarity="Rare Holo")
    c2 = Card(id="c2", set_id="base1", name="Blastoise", number="2", rarity="Rare Holo")
    c3 = Card(id="c3", set_id="base1", name="Venusaur", number="15", rarity="Rare Holo")
    test_db.add_all([c1, c2, c3])

    test_db.add_all([
        ProviderCardState(
            provider="tcgapi",
            card_id="c1",
            match_status="matched",
            last_synced_at=now,
            payload={"prices": {"market_price": 300.0, "price_change_24h": 10.0}},
        ),
        ProviderCardState(
            provider="tcgapi",
            card_id="c2",
            match_status="matched",
            last_synced_at=now,
            payload={"prices": {"market_price": 100.0, "price_change_24h": -5.0}},
        ),
        ProviderCardState(
            provider="tcgapi",
            card_id="c3",
            match_status="matched",
            last_synced_at=now,
            payload={"prices": {"market_price": 75.0, "price_change_24h": 2.5}},
        ),
    ])
    test_db.commit()

    res = calculate_portfolio_valuation(test_db, ["c1", "c2", "c3"])
    assert res.total_cards == 3
    assert res.total_current_value == 475.0
    assert res.highest_value_card is not None
    assert res.highest_value_card.name == "Charizard"
    assert res.highest_value_card.market_price == 300.0
    assert len(res.cards) == 3
    # Cards sorted descending by price
    assert res.cards[0].id == "c1"
    assert res.cards[1].id == "c2"
    assert res.cards[2].id == "c3"


def test_portfolio_api_endpoint(client: TestClient, test_db: Session) -> None:
    now = datetime.now(UTC)
    s = Set(id="pgo", name="Pokemon GO", release_date=date(2022, 7, 1))
    test_db.add(s)

    c = Card(id="pgo-1", set_id="pgo", name="Mewtwo V", number="072/078", rarity="Ultra Rare")
    test_db.add(c)

    test_db.add(
        ProviderCardState(
            provider="tcgapi",
            card_id="pgo-1",
            match_status="matched",
            last_synced_at=now,
            payload={"prices": {"market_price": 42.50}},
        )
    )
    test_db.commit()

    response = client.post(
        "/cards/portfolio-valuation",
        json={"card_ids": ["pgo-1"], "days": 30},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_cards"] == 1
    assert data["total_current_value"] == 42.50
    assert len(data["cards"]) == 1
    assert data["cards"][0]["name"] == "Mewtwo V"
