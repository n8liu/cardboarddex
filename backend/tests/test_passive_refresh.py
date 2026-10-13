from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Card, Set, ProviderCardState
from app.services import passive_refresh as refresh


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="set", name="Set"))
        session.add_all(Card(id=str(i), name=f"Card {i}", number=str(i), set_id="set") for i in range(10))
        session.commit()
        yield session
    engine.dispose()


def test_popular_slots_and_long_tail_are_both_served(db):
    redis = MagicMock()
    redis.zrangebyscore.return_value = []
    ids = refresh.select_due_cards(db, "tcgapi", ["0", "1", "2", "3"], datetime.now(UTC), 5, redis)
    assert ids == ["0", "1", "2", "4", "5"]


def test_provider_freshness_is_independent_and_hot_cards_refresh_sooner(db):
    now = datetime.now(UTC)
    db.add_all([
        ProviderCardState(card_id="0", provider="tcgapi", match_status="matched", last_synced_at=now),
        ProviderCardState(card_id="1", provider="tcgapi", match_status="matched", last_synced_at=now - timedelta(hours=2)),
        ProviderCardState(card_id="2", provider="tcgapi", match_status="matched", last_synced_at=now - timedelta(hours=2)),
    ])
    db.commit()
    redis = MagicMock()
    redis.zrangebyscore.return_value = []
    tcg = refresh.select_due_cards(db, "tcgapi", ["0", "1"], now, 5, redis)
    assert "0" not in tcg and "1" in tcg and "2" not in tcg
    assert "0" in refresh.select_due_cards(db, "ebay", ["0", "1"], now, 5, redis)


def test_failed_attempts_cool_down_without_blocking_later_cards(db):
    redis = MagicMock()
    redis.zrangebyscore.return_value = [str(i) for i in range(6)]
    assert refresh.select_due_cards(db, "ebay", ["0"], datetime.now(UTC), 5, redis) == ["6", "7", "8", "9"]


@pytest.mark.parametrize("reason", ["busy", "daily_limit", "redis_unavailable", "disabled"])
def test_scheduled_safety_gates_never_call_provider(db, monkeypatch, reason):
    redis = MagicMock()
    redis.set.return_value = reason != "busy"
    redis.get.return_value = "500" if reason == "daily_limit" else "0"
    if reason == "redis_unavailable":
        redis.set.side_effect = ConnectionError("offline")
    monkeypatch.setattr(refresh, "get_durable_redis", lambda: redis)
    if reason == "disabled":
        monkeypatch.setattr(refresh, "get_settings", lambda: type("Settings", (), {"passive_refresh_enabled": False})())
    collect = MagicMock()
    assert refresh.run_scheduled_collection(db, "ebay", collect) == {"skipped": reason}
    collect.assert_not_called()


def test_attempts_recorded_before_collection_and_lease_released_on_failure(db, monkeypatch):
    redis = MagicMock()
    redis.set.return_value = True
    redis.get.return_value = "0"
    redis.zrangebyscore.return_value = []
    monkeypatch.setattr(refresh, "get_durable_redis", lambda: redis)
    monkeypatch.setattr(refresh, "popular_card_ids", lambda now: ["0"])

    def collect(session, *, card_ids):
        redis.pipeline.return_value.execute.assert_called_once()
        assert card_ids == ["0", "1", "2", "3", "4"]
        raise ValueError("bad provider payload")

    with pytest.raises(ValueError, match="bad provider payload"):
        refresh.run_scheduled_collection(db, "tcgapi", collect)
    redis.eval.assert_called_once()
    assert redis.eval.call_args.args[0] == refresh.RELEASE


def test_popularity_combines_recent_buckets_and_expires(monkeypatch):
    redis = MagicMock()
    redis.zrevrange.side_effect = [[("0", 2), ("1", 1)], [("1", 3)]]
    monkeypatch.setattr(refresh, "get_redis", lambda: redis)
    assert refresh.popular_card_ids(86400 * 100) == ["1", "0"]
    refresh.record_card_interest(redis, "0", 86400 * 100)
    pipe = redis.pipeline.return_value
    pipe.expire.assert_called_once_with(f"{refresh.PREFIX}:interest:100", 172800)
    pipe.zremrangebyrank.assert_called_once_with(f"{refresh.PREFIX}:interest:100", 0, -2001)


def test_scheduled_entrypoints_use_coordinator(monkeypatch):
    from jobs import collect_prices, collect_ebay_prices
    runner = MagicMock(return_value={"cards": 0})
    monkeypatch.setattr(refresh, "run_scheduled_collection", runner)
    for module, task, provider in [(collect_prices, collect_prices.collect_prices, "tcgapi"),
                                  (collect_ebay_prices, collect_ebay_prices.collect_ebay_prices, "ebay")]:
        monkeypatch.setattr(module, "SessionLocal", MagicMock())
        assert task.run() == {"cards": 0}
        assert runner.call_args.args[1] == provider
