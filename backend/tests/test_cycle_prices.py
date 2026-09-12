from datetime import date
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Card, ProviderCardState, Set
from jobs.cycle_prices import run_price_cycle


def test_run_price_cycle() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", printed_total=102, release_date=date(1999, 1, 9)))
        session.add(Card(id="pikachu-1", name="Pikachu", set_id="1", number="58", printed_total=102, rarity="Common", image_url="https://tcgplayer-cdn.test/pikachu.jpg"))
        session.commit()

        mock_tcgapi = MagicMock()
        mock_tcgapi.get_card.return_value = {
            "data": {
                "id": "pikachu-1",
                "name": "Pikachu",
                "set_name": "Base Set",
                "number": "58",
            }
        }
        mock_tcgapi.get_card_prices.return_value = {
            "data": [
                {
                    "printing": "Normal",
                    "market_price": 14.50,
                    "last_updated_at": "2026-08-29T12:00:00Z",
                }
            ]
        }

        mock_ebay = MagicMock()
        mock_ebay.search_item_summaries.return_value = []

        result = run_price_cycle(
            session,
            tcg_limit=1,
            ebay_limit=1,
            tcgapi_client=mock_tcgapi,
            ebay_client=mock_ebay,
        )

        assert result["status"] == "completed"
        assert result["tcgapi"]["cards"] == 1
        assert result["tcgapi"]["tcgapi_observations"] == 1
        assert result["ebay"]["cards"] == 1

        state = session.query(ProviderCardState).filter_by(card_id="pikachu-1", provider="tcgapi").first()
        assert state is not None
        assert state.match_status == "matched"
        assert state.last_synced_at is not None


def test_run_price_cycle_with_card_id() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", printed_total=102, release_date=date(1999, 1, 9)))
        session.add(Card(id="charizard-1", name="Charizard", set_id="1", number="4", printed_total=102, rarity="Holo Rare", image_url="https://tcgplayer-cdn.test/charizard.jpg"))
        session.commit()

        mock_tcgapi = MagicMock()
        mock_tcgapi.get_card.return_value = {
            "data": {
                "id": "charizard-1",
                "name": "Charizard",
                "set_name": "Base Set",
                "number": "4",
            }
        }
        mock_tcgapi.get_card_prices.return_value = {
            "data": [
                {
                    "printing": "Holofoil",
                    "market_price": 350.00,
                    "last_updated_at": "2026-08-29T12:00:00Z",
                }
            ]
        }

        mock_ebay = MagicMock()
        mock_ebay.search_item_summaries.return_value = []

        result = run_price_cycle(
            session,
            card_id="charizard-1",
            tcgapi_client=mock_tcgapi,
            ebay_client=mock_ebay,
        )

        assert result["status"] == "completed"
        assert result["card_id"] == "charizard-1"
        assert result["tcgapi"]["cards"] == 1
        assert result["tcgapi"]["tcgapi_observations"] == 1
        assert result["ebay"]["cards"] == 1

