from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import Base
from app.models import Card, Set, MarketHistory, PPTProduct, PPTHistory, PPTCurrentQuote, PriceObservation
from app.providers.ppt import PPTClient, PPTBlocked, PPTQuota, PREFIX
from app.services.ppt_ingestion import normalize, map_product, ingest
from app.services.ppt_prices import pricing_data
from app.services.price_sources import market_observation, grading_observation
from app.services.listing_quality import eligible_observation


@pytest.fixture
def now():
    return datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture
def payload(now):
    d = lambda n: (now - timedelta(days=n)).date().isoformat()
    return {"tcgPlayerId": "123", "setId": 456, "setName": "Example", "name": "Pikachu", "cardNumber": "25/100",
        "rarity": "Rare", "prices": {"primaryPrinting": "Holofoil", "market": 110, "lastUpdated": d(0)},
        "variants": {"Holofoil": {"marketPrice": 110, "conditionUsed": "Near Mint"},
                     "Reverse Holofoil": {"marketPrice": 15, "conditionUsed": "Lightly Played"}},
        "priceHistory": {"variants": {"Holofoil": {"Near Mint": {"history": [
            {"date": d(0), "market": 110, "volume": None}, {"date": d(1), "market": 100, "volume": 0},
            {"date": d(7), "market": 55, "volume": 3}, {"date": d(150), "market": 40, "volume": None}]},
            "Lightly Played": {"history": [{"date": d(30), "market": 5}]}}}},
        "ebay": {"salesByGrade": {"psa10": {"marketPriceMedian7Day": 200, "medianPrice": 999,
            "count": 1234, "lastSaleDate": d(1), "lastMarketUpdate": d(0), "salesBySource": {"ebay": 1000, "fanatics": 234}}},
            "priceHistory": {"psa10": {d(1): {"average": 250, "count": 2, "totalValue": 500}}}}}


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", True)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add(Set(id="legacy-set", name="Example"))
        session.add(Card(id="legacy-card", name="Pikachu", number="25", set_id="legacy-set", rarity="Rare"))
        session.commit()
        yield session
    engine.dispose()


def test_dimensions_and_exact_baselines(payload, now):
    quotes, series = normalize(payload, "english", "cards", now.date())
    raw = next(q for q in quotes if q["primary"])
    assert raw["price_change_24h"] == 10
    assert raw["price_change_7d"] == 100
    assert raw["price_change_30d"] is None  # LP is not an NM baseline
    assert quotes[1]["condition"] == "Lightly Played"
    psa = next(q for q in quotes if q["grade"])
    assert psa["price"] == 200 and psa["metric"] == "median_7d"
    assert psa["price_change_24h"] is None  # daily mean is not a median baseline
    assert next(s for s in series if s["dimensions"]["grade"])["dimensions"]["metric"] == "daily_average"
    nm = series[0]["points"]
    assert nm[now.date().isoformat()]["sales_count"] is None
    assert nm[(now-timedelta(days=1)).date().isoformat()]["sales_count"] == 0


def test_missing_or_old_psa_never_uses_lifetime_median(payload, now):
    payload["ebay"]["salesByGrade"]["psa10"]["marketPriceMedian7Day"] = None
    assert not any(q["grade"] for q in normalize(payload, "japanese", "cards", now.date())[0])
    payload["ebay"]["salesByGrade"]["psa10"]["marketPriceMedian7Day"] = 200
    payload["ebay"]["salesByGrade"]["psa10"]["lastSaleDate"] = "2020-01-01"
    assert not any(q["grade"] for q in normalize(payload, "japanese", "cards", now.date())[0])


@pytest.mark.parametrize("language,label,expected", [
    ("english", "Near Mint Holofoil", "Near Mint"),
    ("japanese", "Near Mint Holofoil - Japanese", "Near Mint"),
    ("japanese", "Lightly Played Holofoil - Japanese", "Lightly Played"),
    ("english", "Near Mint Reverse Holofoil", "Near Mint Reverse Holofoil"),
    ("english", "Unknown", "Unknown"),
])
def test_live_provider_condition_labels(payload, now, language, label, expected):
    payload["variants"]["Holofoil"]["conditionUsed"] = label
    quote = normalize(payload, language, "cards", now.date())[0][0]
    assert quote["condition"] == expected
    assert quote["price_change_7d"] == (100 if expected == "Near Mint" else None)


def test_mapping_history_idempotence_and_legacy_preservation(db, payload, now):
    db.add(MarketHistory(card_id="legacy-card", printing="Normal", day=now.date(), market_price=99, fetched_at=now))
    product = map_product(db, payload, "english", "cards")
    assert product.card_id == "legacy-card"
    ingest(db, product, payload, now)
    db.commit()
    counts = lambda model: db.scalar(select(func.count()).select_from(model))
    observations, chunks = counts(PriceObservation), counts(PPTHistory)
    assert observations == 3
    assert counts(MarketHistory) == 1
    ingest(db, product, payload, now + timedelta(hours=1))
    db.commit()
    assert counts(PriceObservation) == observations and counts(PPTHistory) == chunks
    corrected = deepcopy(payload)
    corrected["priceHistory"]["variants"]["Holofoil"]["Near Mint"]["history"][2]["market"] = 100
    ingest(db, product, corrected, now + timedelta(hours=2))
    db.commit()
    assert counts(PriceObservation) == observations  # correction isn't a new live feed item
    selected = db.scalar(select(PriceObservation).where(market_observation()))
    assert selected.payload["price_change_7d"] == 10
    from app.services.catalog_prices import verify_projection
    assert verify_projection(db)["mismatched_cards"] == []
    result = pricing_data(db, "legacy-card")
    assert result["ppt_mapped"] and len(result["provider_history"]) == 3
    assert db.get(Card, "legacy-card").set_id == "legacy-set"
    assert db.get(Set, "legacy-set").printed_total is None
    assert db.scalar(select(MarketHistory.market_price)) == 99


def test_shadow_hidden_and_current_fallback(db, payload, now, monkeypatch):
    db.add(PriceObservation(fingerprint="legacy", card_id="legacy-card", provider="tcgapi", provider_card_id="x", variant_id="raw", price=90, currency="USD"))
    product = map_product(db, payload, "english", "cards")
    ingest(db, product, payload, now)
    db.commit()
    assert [o.provider for o in db.scalars(select(PriceObservation).where(market_observation()))] == ["pokemonpricetracker"]
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", False)
    assert pricing_data(db, "legacy-card")["provider_history"] == []
    assert [o.provider for o in db.scalars(select(PriceObservation).where(eligible_observation()))] == ["tcgapi"]
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", True)
    payload["variants"] = {}
    payload["prices"]["market"] = None
    payload["ebay"]["salesByGrade"] = {}
    ingest(db, product, payload, now)
    db.commit()
    assert [o.provider for o in db.scalars(select(PriceObservation).where(market_observation()))] == ["pokemonpricetracker"]
    assert not list(db.scalars(select(PriceObservation).where(grading_observation(), PriceObservation.grading_company == "PSA")))

    assert next(q for q in pricing_data(db, "legacy-card")["provider_quotes"] if q["primary"])["stale"]


def test_identity_conflicts_languages_and_new_products(db, payload):
    db.add(Card(id="duplicate", name="Pikachu", number="25", set_id="legacy-set"))
    db.flush()
    assert map_product(db, payload, "english", "cards").status == "quarantined"
    japanese = map_product(db, payload, "japanese", "cards")
    assert japanese.card_id.startswith("ppt-")
    assert db.get(Card, japanese.card_id).set.series == "Pokemon Japan"
    assert db.get(Card, japanese.card_id).printed_total is None
    changed = dict(payload, tcgPlayerId="999", name="Pikachu Exclusive")
    assert map_product(db, changed, "english", "cards").status == "quarantined"


def test_sealed_has_no_graded_and_keeps_null_counts(now):
    d = now.date().isoformat()
    quotes, series = normalize({"unopenedPrice": 123, "lastScrapedAt": d,
        "priceHistory": [{"date": d, "unopenedPrice": 123}]}, "japanese", "sealed", now.date())
    assert quotes[0]["condition"] == "Unopened" and quotes[0]["grade"] is None
    assert series[0]["points"][d]["sales_count"] is None


def test_client_bounded_request_and_exact_header_reconciliation(monkeypatch):
    monkeypatch.setattr(get_settings(), "ppt_api_key", "test-only")
    quota = Mock()
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": {"tcgPlayerId": "123"}}, headers={"X-API-Calls-Consumed": "3"})
    client = PPTClient(quota=quota, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.request("cards", tcgPlayerId="123", includeHistory=True, includeEbay=True)[0]["tcgPlayerId"] == "123"
    quota.reserve.assert_called_once_with(3, 1, "rotation", bonus=0)
    assert captured[0].url.params["limit"] == "1"
    assert captured[0].url.params["days"] == "180"
    assert captured[0].url.params["maxDataPoints"] == "180"
    assert quota.finish.call_args[0][1]["X-API-Calls-Consumed"] == "3"
    with pytest.raises(ValueError):
        client.request("cards", fetchAllInSet=True)
    with pytest.raises(ValueError):
        client.request("cards", limit=200)


def test_worker_sealed_request_omits_cards_only_parameters(monkeypatch):
    monkeypatch.setattr(get_settings(), "ppt_api_key", "test-only")
    quota = Mock()

    def handler(request):
        assert "includeEbay" not in request.url.params
        assert "maxDataPoints" not in request.url.params
        assert request.url.params["includeHistory"] == "true"
        assert request.url.params["days"] == "180"
        return httpx.Response(200, json={"data": {"tcgPlayerId": "712093"}})

    client = PPTClient(quota=quota, client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        assert client.request("sealed-products", language="english", tcgPlayerId="712093",
                              includeHistory=True, includeEbay=False)[0]["tcgPlayerId"] == "712093"
        quota.reserve.assert_called_once_with(2, 1, "rotation", bonus=0)
        with pytest.raises(ValueError, match="Graded sales"):
            client.request("sealed-products", tcgPlayerId="712093", includeEbay=True)
        assert quota.reserve.call_count == 1
    finally:
        client.close()


@pytest.fixture
def quota(monkeypatch):
    import fakeredis
    redis = fakeredis.FakeRedis(decode_responses=True)
    instant = [datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp()]
    result = PPTQuota(redis, now=lambda: instant[0])
    return result, redis, instant


def test_quota_weighted_sliding_window_and_single_flight(quota):
    q, redis, instant = quota
    a = q.reserve(50, 30, "rotation")
    with pytest.raises(PPTBlocked, match="in_flight"):
        q.reserve(1, 1, "rotation")
    q.finish(a)
    with pytest.raises(PPTBlocked, match="minute"):
        q.reserve(50, 30, "rotation")
    b = q.reserve(25, 25, "rotation")
    q.finish(b)
    instant[0] += 60.01
    q.finish(q.reserve(25, 25, "rotation"))


def test_quota_daily_reconciliation_ignores_prepaid_and_unknown_response(quota):
    q, redis, instant = quota
    day = int(instant[0] // 86400)
    key = f"{PREFIX}:credits:{day}"
    a = q.reserve(3, 1, "rotation")
    q.finish(a, {"X-API-Calls-Consumed": "3", "X-RateLimit-Daily-Remaining": "1", "X-RateLimit-Total-Remaining": "99999"})
    assert int(redis.get(key)) == 19999
    with pytest.raises(PPTBlocked, match="daily"):
        q.reserve(2, 1, "retry")
    q.finish(q.reserve(1, 1, "retry"))  # missing response keeps reservation spent
    assert int(redis.get(key)) == 20000
    instant[0] += 86400
    q.finish(q.reserve(2, 1, "rotation"))
    assert int(redis.get(f"{PREFIX}:credits:{day+1}")) == 2


def test_bonus_credits_retry_reserve_and_late_borrowing(quota):
    q, redis, instant = quota
    day = int(instant[0] // 86400)
    q.finish(q.reserve(3, 1, "rotation", bonus=1))
    assert redis.get(f"{PREFIX}:lane:{day}:rotation") == "2"
    assert redis.get(f"{PREFIX}:lane:{day}:graded") == "1"
    redis.set(f"{PREFIX}:lane:{day}:rotation", 13000)
    with pytest.raises(PPTBlocked, match="lane"):
        q.reserve(2, 1, "rotation")
    redis.set(f"{PREFIX}:credits:{day}", 19500)
    with pytest.raises(PPTBlocked, match="daily"):
        q.reserve(1, 1, "priority")
    instant[0] += 10*3600
    q.finish(q.reserve(2, 1, "rotation"))
    instant[0] = (day+1)*86400 - 10
    with pytest.raises(PPTBlocked, match="utc_rollover"):
        q.reserve(1, 1, "retry")


def test_concurrent_workers_never_share_inflight_reservation(quota):
    from concurrent.futures import ThreadPoolExecutor
    q, redis, _ = quota
    def attempt(_):
        try:
            return q.reserve(3, 1, "rotation")
        except PPTBlocked:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(20)))
    winners = [r for r in results if r]
    assert len(winners) == 1
    q.finish(winners[0])


def test_cooldown_shared_and_fail_closed(quota):
    q, redis, instant = quota
    q.cooldown(120, "rate_limited")
    other = PPTQuota(redis, now=lambda: instant[0])
    with pytest.raises(PPTBlocked, match="cooldown"):
        other.reserve(1, 1, "rotation")
    broken = Mock()
    from redis.exceptions import ConnectionError
    broken.eval.side_effect = ConnectionError("offline")
    with pytest.raises(ConnectionError):
        PPTQuota(broken).reserve(1, 1, "rotation")


def test_rotation_keeps_recent_graded_quotes_and_identity_change_quarantines(db, payload, now):
    product = map_product(db, payload, "english", "cards")
    ingest(db, product, payload, now)
    db.commit()
    raw_only = {k: v for k, v in payload.items() if k != "ebay"}
    ingest(db, product, raw_only, now)
    db.commit()
    assert any(q["grade"] == "psa10" for q in product.quotes)
    raw_only["name"] = "Different Pikachu"
    ingest(db, product, raw_only, now)
    db.commit()
    assert product.status == "quarantined"
    assert not list(db.scalars(select(PPTCurrentQuote)))
    from app.models import CatalogPriceCandidate
    assert not list(db.scalars(select(CatalogPriceCandidate).where(CatalogPriceCandidate.provider == "pokemonpricetracker")))
    assert pricing_data(db, "legacy-card")["ppt_mapped"] is False


def test_provider_sales_counts_only_explicit_volume(db, payload, now):
    from app.services.ppt_prices import sales_activity, market_history
    product = map_product(db, payload, "english", "cards")
    ingest(db, product, payload, now)
    db.commit()
    result = sales_activity(db)
    assert result["total_sales"] == 3  # not graded count 1234, history points, or quote count
    assert result["products_with_sales_data"] == 1
    assert market_history(db, "legacy-card", 7)["previous_price"] is None  # Backfill is separate from the continuation.
    assert market_history(db, "legacy-card", 30)["return_percent"] is None


def test_429_and_auth_stop_shared_requests(monkeypatch, quota):
    monkeypatch.setattr(get_settings(), "ppt_api_key", "test-only")
    q, redis, instant = quota
    client = PPTClient(quota=q, client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(429, json={"limitType": "daily"}, headers={"Retry-After": "5"}))))
    with pytest.raises(httpx.HTTPStatusError):
        client.request("cards", tcgPlayerId="123")
    assert redis.ttl(PREFIX + ":cooldown") > 3600
    with pytest.raises(PPTBlocked, match="cooldown"):
        client.request("cards", tcgPlayerId="123")


def test_lost_response_stays_spent(monkeypatch, quota):
    monkeypatch.setattr(get_settings(), "ppt_api_key", "test-only")
    q, redis, instant = quota
    def timeout(request):
        raise httpx.ReadTimeout("test timeout", request=request)
    client = PPTClient(quota=q, client=httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(httpx.ReadTimeout):
        client.request("cards", tcgPlayerId="123", includeHistory=True)
    assert redis.get(f"{PREFIX}:credits:{int(instant[0] // 86400)}") == "2"
    assert not redis.exists(PREFIX + ":flight")


def test_lower_pilot_cap_accounts_for_provider_daily_remaining(quota, monkeypatch):
    q, redis, instant = quota
    monkeypatch.setattr(get_settings(), "ppt_daily_credit_limit", 100)
    q.finish(q.reserve(2, 1, "rotation"), {"X-API-Calls-Consumed": "2", "X-RateLimit-Daily-Remaining": "0"})
    with pytest.raises(PPTBlocked, match="daily"):
        q.reserve(1, 1, "retry")


def test_app_price_consumers_prefer_provider_without_merging_baselines(db, payload, now):
    from app.services.catalog_service import query_pokemon_cards
    from app.services.portfolio_service import calculate_portfolio_valuation
    from app.services.grading_service import calculate_grading_profit
    db.add(PriceObservation(fingerprint="legacy", card_id="legacy-card", provider="tcgapi", provider_card_id="x", variant_id="raw", price=999, currency="USD", observed_at=now - timedelta(days=7)))
    product = map_product(db, payload, "english", "cards")
    ingest(db, product, payload, now)
    db.commit()
    catalog = query_pokemon_cards(db, "Pikachu")
    assert catalog.cards[0].market_price == 110
    assert catalog.cards[0].market_source == "pokemonpricetracker"
    binder = calculate_portfolio_valuation(db, ["legacy-card"])
    assert binder.total_current_value == 110
    assert binder.delta_7d_percent is None  # Older PPT backfill is not a continuation baseline.
    assert binder.delta_30d_percent is None
    grading = calculate_grading_profit(db, use_cache=False)
    item = next(i for i in grading.items if i.card_id == "legacy-card")
    assert item.psa10_price == 200
    assert item.raw_price == 110
    assert item.graded_metric == "median_7d"


def test_scheduler_processes_priority_once_and_preserves_checkpoint(db, payload, now, monkeypatch):
    import fakeredis
    from jobs import sync_ppt as job
    monkeypatch.setattr(get_settings(), "ppt_ingestion_enabled", True)
    monkeypatch.setattr(get_settings(), "ppt_batch_size", 1)
    redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(job, "get_durable_redis", lambda: redis)
    monkeypatch.setattr(job, "SessionLocal", lambda: Session(db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(job, "interest_scores", lambda *args: {})
    client = Mock()
    client.request.return_value = [payload]
    monkeypatch.setattr(job, "PPTClient", lambda: client)
    from app.models import PPTCheckpoint
    map_product(db, payload, "english", "cards")
    # The first lane is priority; seed this week's pool so the result never depends on the hour.
    db.add(PPTCheckpoint(key=job.pool_key(datetime.now(UTC)), payload={"cards": ["legacy-card"]}))
    db.commit()
    assert job.sync_ppt()["requests_completed"] == 1
    assert client.request.call_args.kwargs["includeEbay"] is True
    db.expire_all()
    assert db.scalar(select(PPTProduct.last_success_at)) is not None
    job.sync_ppt()
    assert client.request.call_count == 1


def _scheduler(db, monkeypatch):
    import fakeredis
    from jobs import sync_ppt as job
    monkeypatch.setattr(get_settings(), "ppt_ingestion_enabled", True)
    redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(job, "get_durable_redis", lambda: redis)
    monkeypatch.setattr(job, "SessionLocal", lambda: Session(db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(job, "interest_scores", lambda *args: {})
    return job, redis


def test_sync_never_ranks_and_falls_back_to_latest_pool(db, payload, now, monkeypatch):
    from app.models import PPTCheckpoint
    job, _ = _scheduler(db, monkeypatch)
    monkeypatch.setattr(job, "rank_ppt_priority", Mock(side_effect=AssertionError("sync must not rank")))
    monkeypatch.setattr(get_settings(), "ppt_batch_size", 1)
    client = Mock()
    client.request.return_value = [payload]
    monkeypatch.setattr(job, "PPTClient", lambda: client)
    map_product(db, payload, "english", "cards")
    db.add_all([PPTCheckpoint(key="priority:2026-10-05", payload={"cards": ["old"]}),
                PPTCheckpoint(key="priority:2026-10-12", payload={"cards": ["legacy-card"]})])
    db.commit()
    current = datetime.now(UTC)
    assert job.current_priority(db, current) == ["legacy-card"]
    assert job.sync_ppt()["requests_completed"] == 1  # provider work proceeds without a fresh pool
    db.add(PPTCheckpoint(key=job.pool_key(current), payload={"cards": ["fresh"]}))
    db.commit()
    assert job.current_priority(db, current) == ["fresh"]


def test_sync_without_any_pool_still_rotates(db, payload, monkeypatch):
    job, _ = _scheduler(db, monkeypatch)
    assert job.current_priority(db, datetime.now(UTC)) == []


def test_pool_builder_is_leased_idempotent_and_logs_failures(db, monkeypatch, caplog):
    from app.models import PPTCheckpoint
    job, redis = _scheduler(db, monkeypatch)
    key = job.pool_key(datetime.now(UTC))
    redis.set(PREFIX + ":priority-build", "other")
    rank = Mock(return_value=["a", "b"])
    monkeypatch.setattr(job, "rank_ppt_priority", rank)
    assert job.build_priority_pool()["status"] == "leased"
    rank.assert_not_called()
    redis.delete(PREFIX + ":priority-build")

    rank.side_effect = RuntimeError("canceling statement due to statement timeout")
    assert job.build_priority_pool() == {"status": "failed", "key": key}
    assert "statement timeout" in caplog.text
    assert db.get(PPTCheckpoint, key) is None
    assert redis.get(PREFIX + ":priority-build") is None  # lease released

    rank.side_effect = None
    assert job.build_priority_pool() == {"status": "built", "key": key, "cards": 2}
    db.expire_all()
    assert db.get(PPTCheckpoint, key).payload == {"cards": ["a", "b"]}
    assert job.build_priority_pool()["status"] == "exists"
    assert rank.call_count == 2


def test_pool_builder_is_scheduled_with_ingestion(monkeypatch):
    import importlib
    import app.celery_app as module
    monkeypatch.setattr(get_settings(), 'ppt_ingestion_enabled', True)
    importlib.reload(module)
    entries = {x['task']: x for x in module.celery_app.conf.beat_schedule.values()}
    assert entries['jobs.sync_ppt.build_priority_pool']['options']['time_limit'] == 240
    monkeypatch.undo()
    importlib.reload(module)


def test_discovery_is_bounded_and_does_not_emit_feed_entries(db, payload, now):
    from jobs.sync_ppt import discovery_step
    client = Mock()
    client.request.side_effect = [[{"id": "setid", "tcgPlayerNumericId": 456, "name": "Example"}], [payload]]
    discovery_step(db, client, "english:cards", now)
    db.commit()
    discovery_step(db, client, "english:cards", now)
    db.commit()
    assert client.request.call_args.kwargs["limit"] == 25
    assert db.scalar(select(func.count()).select_from(PPTProduct)) == 1
    assert db.scalar(select(func.count()).select_from(PriceObservation)) == 0


def test_disposable_migration_preserves_existing_tables(tmp_path, monkeypatch):
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect, text
    database = tmp_path / "migration.sqlite"
    monkeypatch.setattr(get_settings(), "database_url", f"sqlite:///{database}")
    monkeypatch.setattr(get_settings(), "postgres_host", None)
    config = Config()  # Do not replace pytest logging handlers.
    config.set_main_option("script_location", "alembic")
    command.upgrade(config, "0008_listing_assessments")
    engine = create_engine(f"sqlite:///{database}")
    before = {table: inspect(engine).get_columns(table) for table in ("cards", "sets")}
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sets (id,name) VALUES ('keep','Keep')"))
        conn.execute(text("INSERT INTO cards (id,name,set_id,number) VALUES ('keep','Keep','keep','1')"))
    command.upgrade(config, "head")
    after = {table: inspect(engine).get_columns(table) for table in ("cards", "sets")}
    assert str(before) == str(after)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id FROM cards")).scalar() == "keep"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0012_market_history_transitions"
    engine.dispose()


def test_explicit_external_id_supports_set_alias_but_never_guesses_local_ids(db, payload):
    from app.models import ProviderCardState
    db.add(ProviderCardState(card_id="legacy-card", provider="tcgapi", provider_card_id="unrelated-local-id", match_status="matched",
        payload={"card": {"tcgPlayerId": "123"}}))
    db.commit()
    from app.services.ppt_ingestion import index_legacy_identities
    index_legacy_identities(db)
    db.commit()
    payload["setName"] = "Provider's exact set alias"
    product = map_product(db, payload, "english", "cards")
    assert product.card_id == "legacy-card"
    assert product.match_method == "verified_tcgplayer_id"


def test_live_counts_preserve_shadow_and_listing_exclusion(db, payload, now, monkeypatch):
    from fastapi import Response
    from app.routers import market
    monkeypatch.setattr(market, "_get_redis", lambda: None)
    db.add(PriceObservation(fingerprint="legacy-kpi", card_id="legacy-card", provider="tcgapi",
        provider_card_id="x", variant_id="raw", price=90, currency="USD"))
    db.add(PriceObservation(fingerprint="unmatched-kpi", card_id="legacy-card", provider="ebay",
        provider_card_id="x", variant_id="raw", price=1, currency="USD"))
    product = map_product(db, payload, "english", "cards")
    ingest(db, product, payload, now)
    db.commit()
    for enabled, expected_items, expected_graded in ((False, 0, 0), (True, 3, 1)):
        monkeypatch.setattr(get_settings(), "ppt_primary_enabled", enabled)
        result = market.get_live_updates(response=Response(), provider="pokemonpricetracker",
            grade_filter="all", set_id=None, q=None, page=1, per_page=48, db=db)
        assert len(result.items) == expected_items
        assert result.total_tcg_updates == 1
        assert result.total_ebay_updates == 0
        assert result.graded_updates_count == expected_graded


def test_graded_sales_snapshot_counts_and_search(db, payload, now):
    from app.services.ppt_prices import graded_sales_activity
    payload['ebay']['salesByGrade'].update({
        'cgc9_5': {'count': 0}, 'psa9': {'count': 5, 'lastSaleDate': 'invalid'},
        'missing': {}, 'negative': {'count': -1}, 'boolean': {'count': True},
        'float': {'count': 2.5}, 'string': {'count': '3'}, 'bad': None,
    })
    # Invalid dates in unnormalized metadata must not break the public ranking.
    payload['ebay']['salesByGrade']['psa9'].pop('lastSaleDate')
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now - timedelta(days=8))
    product.metadata_payload = {**product.metadata_payload, 'ebay': {**payload['ebay'], 'salesByGrade': {
        **payload['ebay']['salesByGrade'], 'psa9': {'count': 5, 'lastSaleDate': 'invalid'},
    }}}
    db.commit()
    result = graded_sales_activity(db, 'Example')
    assert result['status'] == 'ready'
    item = result['items'][0]
    assert item['sales'] == 1239  # Neither raw history volume nor daily graded counts.
    assert {g['grade']: g['sales'] for g in item['grades']} == {'cgc9_5': 0, 'psa10': 1234, 'psa9': 5}
    assert item['last_sale_date'] == (now - timedelta(days=1)).date().isoformat()
    assert item['stale'] is True
    assert graded_sales_activity(db, 'Pika')['status'] == 'ready'
    assert graded_sales_activity(db, '%')['status'] == 'no_matches'
    assert graded_sales_activity(db, 'missing')['synced_at'] is None


def test_graded_sales_gate_and_empty(db, monkeypatch):
    from app.services.ppt_prices import graded_sales_activity
    assert graded_sales_activity(db)['status'] == 'not_synced'
    monkeypatch.setattr(get_settings(), 'ppt_primary_enabled', False)
    # Gate must not even query the database.
    assert graded_sales_activity(Mock())['status'] == 'provider_disabled'


def test_graded_sales_bounded_ranking_duplicate_and_zero(db, now):
    from app.services.ppt_prices import graded_sales_activity
    for i in range(125):
        cid = f'card-{i:03}'
        db.add(Card(id=cid, name=cid, number=str(i), set_id='legacy-set'))
        db.add(PPTProduct(id=cid, provider_id=cid, card_id=cid, segment='english:cards', status='matched',
            last_success_at=now, metadata_payload={'ebay': {'salesByGrade': {'psa10': {'count': i // 2}}}}))
    db.add(PPTProduct(id='older', provider_id='older', card_id='card-000', segment='english:cards', status='matched',
        last_success_at=now-timedelta(days=1), metadata_payload={'ebay': {'salesByGrade': {'psa10': {'count': 999999}}}}))
    db.add(PPTProduct(id='sealed', provider_id='sealed', card_id='legacy-card', segment='english:sealed', status='matched',
        last_success_at=now, metadata_payload={'ebay': {'salesByGrade': {'psa10': {'count': 999999}}}}))
    db.commit()
    result = graded_sales_activity(db)
    assert result['products_with_sales_data'] == 125
    assert len(result['items']) == 50
    assert [x['card_id'] for x in result['items'][:3]] == ['card-124', 'card-122', 'card-123']
    assert graded_sales_activity(db, 'card-000')['items'][0]['sales'] == 0
    assert graded_sales_activity(db, 'card-000')['items'][0]['stale'] is True  # Old snapshots lack separate graded freshness.


def test_cutover_preserves_history_overlap_and_conditions(db, payload, now):
    from app.models import MarketHistoryTransition
    from app.services.market_history import establish_transitions
    yesterday = now - timedelta(days=1)
    db.add(PriceObservation(fingerprint='old', card_id='legacy-card', provider='tcgapi', provider_card_id='old',
        variant_id='normal', printing='Holofoil', condition='Near Mint', price=77, currency='USD',
        observed_at=yesterday, provider_updated_at=yesterday))
    # Unknown-condition points must never be relabeled Near Mint.
    db.add(MarketHistory(card_id='legacy-card', printing='Holofoil', day=yesterday.date(), market_price=88, fetched_at=now))
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now)
    db.commit()
    result = pricing_data(db, 'legacy-card')
    market = next(s for s in result['market_history_series'] if s['condition'] == 'Near Mint' and s['printing'] == 'Holofoil')
    assert [(p['price'], p['source']) for p in market['points']] == [(77, 'tcgapi'), (110, 'pokemonpricetracker')]
    unknown = next(s for s in result['market_history_series'] if s['condition'] is None and not s.get('grade'))
    assert unknown['points'][0]['price'] == 88
    before = [(t.id, t.cutover_date) for t in db.scalars(select(MarketHistoryTransition))]
    establish_transitions(db, product, now + timedelta(days=10))
    db.commit()
    assert [(t.id, t.cutover_date) for t in db.scalars(select(MarketHistoryTransition))] == before
    assert db.scalar(select(PriceObservation.price).where(PriceObservation.fingerprint == 'old')) == 77
    assert db.get(MarketHistory, ('legacy-card', 'Holofoil', yesterday.date())).market_price == 88


def test_partial_refresh_preserves_graded_snapshot_and_freshness(db, payload, now):
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now)
    db.commit()
    original = deepcopy(product.metadata_payload['ebay'])
    original_time = product.metadata_payload['graded_synced_at']
    partial = deepcopy(payload)
    partial.pop('ebay')
    ingest(db, product, partial, now + timedelta(days=2))
    db.commit()
    assert product.metadata_payload['ebay'] == original
    assert product.metadata_payload['graded_synced_at'] == original_time
    partial['ebay'] = {}
    ingest(db, product, partial, now + timedelta(days=3))
    db.commit()
    assert product.metadata_payload['ebay'] == {}
    assert product.metadata_payload['graded_synced_at'] != original_time


def test_manual_refresh_uses_same_ingestion_and_keeps_ids(db, payload, now, monkeypatch):
    from app.services.ppt_refresh import refresh_cards
    monkeypatch.setattr(get_settings(), 'ppt_ingestion_enabled', True)
    product = map_product(db, payload, 'english', 'cards')
    db.commit()
    client = Mock()
    client.request.return_value = [payload]
    result = refresh_cards(db, ['legacy-card'], client=client)
    assert result['cards'] == 1
    assert client.request.call_args.kwargs['tcgPlayerId'] == product.provider_id
    assert db.get(Card, 'legacy-card').set_id == 'legacy-set'
    assert product.last_success_at is not None


def test_retired_schedules_do_not_reappear_when_legacy_flag_is_true(monkeypatch):
    import importlib
    import app.celery_app as module
    monkeypatch.setattr(get_settings(), 'tcgapi_ingestion_enabled', True)
    monkeypatch.setattr(get_settings(), 'ppt_ingestion_enabled', True)
    importlib.reload(module)
    tasks = {x['task'] for x in module.celery_app.conf.beat_schedule.values()}
    assert 'jobs.sync_ppt.sync_ppt' in tasks
    assert 'jobs.collect_ebay_prices.collect_ebay_prices' in tasks
    assert not tasks.intersection({'jobs.collect_prices.collect_prices', 'jobs.sync_catalog.sync_catalog', 'jobs.sync_market_data.sync_market_data'})
    monkeypatch.undo()
    importlib.reload(module)


def test_quarantined_mapping_cannot_supply_public_history(db, payload, now):
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now)
    db.commit()
    assert pricing_data(db, 'legacy-card')['provider_history']
    product.status = 'quarantined'
    db.commit()
    result = pricing_data(db, 'legacy-card')
    assert result['provider_history'] == []
    assert result['market_quotes'] == []
    assert all(s['provider'] == 'tcgapi' for s in result['market_history_series'])


def test_preservation_receipt_detects_loss_but_allows_catalog_additions(db, payload, now):
    from scripts.ppt_migration_audit import audit, preserved
    db.add(PriceObservation(fingerprint='receipt-old', card_id='legacy-card', provider='tcgapi',
        provider_card_id='old', variant_id='raw', price=77, currency='USD', observed_at=now))
    db.commit()
    before = audit(db)
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now)
    db.add(Card(id='new-ppt-card', set_id='legacy-set', name='New card', number='999'))
    db.commit()
    assert preserved(before, audit(db))
    row = db.scalar(select(PriceObservation).where(PriceObservation.fingerprint == 'receipt-old'))
    row.price = 78
    db.commit()
    assert not preserved(before, audit(db))


def test_portfolio_history_inputs_have_fixed_query_count(db, payload, now):
    from sqlalchemy import event
    from app.services.market_history import load_history_inputs
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now)
    db.commit()
    statements = []
    def record(*args):
        statements.append(args[2])
    event.listen(db.get_bind(), 'before_cursor_execute', record)
    try:
        stored = load_history_inputs(db, ['legacy-card', 'missing'], 180)
        assert len(statements) == 6
        pricing_data(db, 'legacy-card', stored=stored['legacy-card'])
        pricing_data(db, 'missing', stored=stored['missing'])
        assert len(statements) == 6
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', record)


def test_recorded_transition_cannot_be_downgraded(db, payload, now, monkeypatch):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path('alembic/versions/0012_market_history_transitions.py')
    spec = importlib.util.spec_from_file_location('transition_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now)
    db.commit()
    monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(db.connection())))
    with pytest.raises(RuntimeError, match='Roll back application code'):
        migration.downgrade()
    assert pricing_data(db, 'legacy-card')['market_history_series']


def test_unknown_legacy_prefix_continues_single_ppt_series(db, payload, now):
    yesterday = now - timedelta(days=1)
    db.add(MarketHistory(card_id='legacy-card', printing='Holofoil', day=yesterday.date(),
                         market_price=88, fetched_at=now))
    product = map_product(db, payload, 'english', 'cards')
    ingest(db, product, payload, now)
    db.commit()
    series = [s for s in pricing_data(db, 'legacy-card')['market_history_series']
              if not s.get('grade') and s['printing'] == 'Holofoil']
    assert len(series) == 1
    assert [(p['price'], p['source']) for p in series[0]['points']] == [(88, 'tcgapi'), (110, 'pokemonpricetracker')]
    assert series[0]['points'][0]['condition'] is None
    assert db.get(MarketHistory, ('legacy-card', 'Holofoil', yesterday.date())).market_price == 88


def test_worker_ingestion_leads_live_feed_and_skips_unchanged_quotes(db, payload, now):
    from fastapi import Response
    from app.routers.market import get_live_feed
    db.add(PriceObservation(fingerprint="legacy-old", card_id="legacy-card", provider="tcgapi", provider_card_id="x",
                            variant_id="raw", price=5, currency="USD", observed_at=now - timedelta(hours=1)))
    product = map_product(db, payload, "english", "cards")
    ingest(db, product, payload, now)
    db.commit()
    page = get_live_feed(Response(), "pokemonpricetracker", "all", None, None, 1, 24, db)
    assert page.items and all(i.provider == "pokemonpricetracker" for i in page.items)
    assert page.items[0].observed_at.replace(tzinfo=UTC) == now
    newest = get_live_feed(Response(), "all", "all", None, None, 1, 1, db).items[0]
    assert newest.provider == "pokemonpricetracker"
    count = db.scalar(select(func.count()).select_from(PriceObservation))

    ingest(db, product, payload, now + timedelta(minutes=5))  # same price and price date
    db.commit()
    assert db.scalar(select(func.count()).select_from(PriceObservation)) == count

    changed = deepcopy(payload)
    changed["prices"]["market"] = changed["variants"]["Holofoil"]["marketPrice"] = 120
    ingest(db, product, changed, now + timedelta(minutes=10))
    db.commit()
    top = get_live_feed(Response(), "pokemonpricetracker", "all", None, None, 1, 1, db).items[0]
    assert top.price == 120
