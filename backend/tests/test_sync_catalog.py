from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Card, Set
from jobs.sync_catalog import run_catalog_sync


class FakeTCGAPIClient:
    def iter_sets(self):
        yield {"id": "24541", "name": "Evolving Skies", "card_count": 237,
               "release_date": "2021-08-27"}

    def iter_cards(self, set_ids):
        assert set_ids == ["24541"]
        yield {"id": "8765", "_set_id": "24541", "name": "Umbreon VMAX",
               "number": "215/203", "rarity": "Rare Rainbow",
               "image_url": "https://tcgplayer-cdn.test/8765.jpg"}


def test_catalog_sync_upserts_sets_before_cards_and_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert run_catalog_sync(session, FakeTCGAPIClient()) == {"sets": 1, "cards": 1, "prices": 0}
        assert run_catalog_sync(session, FakeTCGAPIClient()) == {"sets": 1, "cards": 1, "prices": 0}
        card = session.scalar(select(Card))
        card_set = session.scalar(select(Set))
    assert card is not None and card.number == "215" and card.printed_total == 203
    assert card.image_url == "https://tcgplayer-cdn.test/8765.jpg"
    assert card_set is not None and card_set.name == "Evolving Skies"


class MultiSetClient:
    def iter_sets(self):
        yield {"id": "1", "name": "First", "card_count": 1, "release_date": None}
        yield {"id": "2", "name": "Second", "card_count": 1, "release_date": None}

    def iter_cards(self, set_ids):
        assert set_ids == ["1"]
        yield {"id": "card-1", "_set_id": "1", "name": "Pikachu",
               "number": "1/1", "rarity": "Common", "image_url": "https://img.test/1.jpg"}


def test_catalog_sync_respects_set_limit() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert run_catalog_sync(session, MultiSetClient(), set_limit=1) == {"sets": 1, "cards": 1, "prices": 0}
        assert [item.name for item in session.scalars(select(Set)).all()] == ["First"]


class NewestSetClient:
    def iter_sets(self):
        yield {"id": "1", "name": "Old Set", "card_count": 1,
               "release_date": "2024-01-01"}
        yield {"id": "2", "name": "Pitch Black", "card_count": 1,
               "release_date": "2026-08-28"}

    def iter_cards(self, set_ids):
        assert set_ids == ["2"]
        yield {"id": "pitch-black-1", "_set_id": "2", "name": "Mega Charizard X ex",
               "number": "1/1", "rarity": "Rare", "image_url": "https://img.test/2.jpg"}


def test_catalog_sync_prioritizes_newest_release_before_applying_limit() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = run_catalog_sync(session, NewestSetClient(), set_limit=1)
        card_set = session.scalar(select(Set))
    assert result == {"sets": 1, "cards": 1, "prices": 0}
    assert card_set is not None and card_set.name == "Pitch Black"


class PricingSetClient:
    def iter_sets(self):
        yield {"id": "100", "name": "Surging Sparks", "card_count": 1, "release_date": "2024-11-08"}

    def iter_cards(self, set_ids):
        assert set_ids == ["100"]
        yield {
            "id": "999",
            "_set_id": "100",
            "name": "Pikachu ex",
            "number": "057/191",
            "rarity": "Double Rare",
            "image_url": "https://img.test/pika.jpg",
            "printing": "Normal",
            "market_price": 12.50,
            "low_price": 10.00,
            "price_updated_at": "2026-08-28T12:00:00Z",
        }


def test_catalog_sync_records_price_observations() -> None:
    from app.models import PriceObservation, ProviderCardState

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = run_catalog_sync(session, PricingSetClient())
        obs = session.scalar(select(PriceObservation))
        state = session.scalar(select(ProviderCardState))

    assert result == {"sets": 1, "cards": 1, "prices": 1}
    assert obs is not None and float(obs.price) == 12.50
    assert obs.provider == "tcgapi"
    assert obs.printing == "Normal"
    assert state is not None and state.match_status == "matched"


class TwoSetResumeClient:
    def iter_sets(self, game="pokemon"):
        yield {"id": "set-1", "name": "Set One", "card_count": 1, "release_date": "2024-01-01"}
        yield {"id": "set-2", "name": "Set Two", "card_count": 1, "release_date": "2024-02-01"}

    def iter_cards(self, set_ids):
        # When resuming from set-1, only set-2 should be requested
        assert set_ids == ["set-1"] or set_ids == ["set-2"]
        for s_id in set_ids:
            yield {
                "id": f"card-{s_id}",
                "_set_id": s_id,
                "name": f"Card for {s_id}",
                "number": "1/1",
                "rarity": "Common",
                "image_url": f"https://img.test/{s_id}.jpg",
            }


class FakeRedis:
    def __init__(self, initial: dict[str, str] | None = None):
        self.store = dict(initial or {})

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

    def delete(self, key: str) -> bool:
        self.store.pop(key, None)
        return True


def test_catalog_sync_resumes_from_checkpoint_cursor() -> None:
    import json

    fake_redis = FakeRedis({
        "cardboarddex:sync:cursor:pokemon": json.dumps({"last_synced_set_id": "set-2", "set_index": 0})
    })

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Client orders set-2 (newest) then set-1 (older)
        # Cursor says set-2 was already synced, so resume should only sync set-1
        result = run_catalog_sync(
            session,
            TwoSetResumeClient(),
            game="pokemon",
            resume=True,
            redis_client=fake_redis,
        )

    assert result == {"sets": 1, "cards": 1, "prices": 0}
    # When all sets complete, cursor must be cleared
    assert "cardboarddex:sync:cursor:pokemon" not in fake_redis.store


def test_catalog_sync_checkpoints_on_quota_exceeded() -> None:
    from app.providers.limiter import ProviderRequestLimitExceeded

    class QuotaExceededClient:
        def iter_sets(self, game="pokemon"):
            yield {"id": "set-10", "name": "Set Ten", "card_count": 1, "release_date": "2024-01-01"}

        def iter_cards(self, set_ids):
            raise ProviderRequestLimitExceeded("TCG API daily limit of 500 requests reached")

    fake_redis = FakeRedis()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        result = run_catalog_sync(
            session,
            QuotaExceededClient(),
            game="pokemon",
            resume=False,
            redis_client=fake_redis,
        )

    # Sets were upserted before cards failed
    assert result["sets"] == 1
    assert result["cards"] == 0
    # Checkpoint cursor was written to Redis
    assert "cardboarddex:sync:cursor:pokemon" in fake_redis.store
    assert "set-10" in fake_redis.store["cardboarddex:sync:cursor:pokemon"]

