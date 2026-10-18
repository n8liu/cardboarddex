from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Card, Set, PriceObservation, ListingAssessment
from app.services.listing_quality import assess_text, eligible_observation, MATCHER_VERSION
from app.routers.cards import get_card_prices
from parsers.title_matcher import parse_ebay_title, image_number_matches, is_sealed_product
from jobs.check_listing_images import check_one, backfill


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        s = Set(id="base", name="Base Set", printed_total=102)
        c = Card(id="c", name="Charizard", number="4", set=s, rarity="Rare Holo", image_url="https://images.pokemontcg.io/base1/4.png")
        session.add_all([s, c])
        session.commit()
        yield session
    engine.dispose()


@pytest.mark.parametrize("title,expected", [
    ("Charizard Base Set 4/102 Holo Near Mint", "matched"),
    ("Charizard Base Set 4/130 Holo Near Mint", "rejected"),
    ("Charizard Base Set PSA 4", "uncertain"),
    ("Charizard 4/102 Holo", "uncertain"),
    ("Charizard ex Base Set 4/102", "rejected"),
    ("Charizard Base Set 4/102 choose your card", "rejected"),
    ("Charizard Base Set 4/102 PSA 10 proxy", "rejected"),
    ("Charizard Base Set 4/102 Japanese", "rejected"),
])
def test_strict_identity(title, expected):
    result = parse_ebay_title(title, "Charizard", "4", "Base Set", strict=True, target_printed_total=102)
    assert result.status == expected


def item(id="1", **extra):
    return {"itemId": id, "title": "Charizard Base Set 4/102 Holo Near Mint", "image": {"imageUrl": "https://i.ebayimg.com/a.jpg"}, "seller": {"username": id}, **extra}


def test_pending_reused_and_source_changes_invalidate(db):
    card = db.get(Card, "c")
    a, result = assess_text(db, card, item())
    assert a.status == "pending"
    assert a is assess_text(db, card, item())[0]
    b, _ = assess_text(db, card, item(title="Charizard Base Set 4/102 Holo Damaged"))
    assert a.fingerprint != b.fingerprint
    assert result.printing == "Holofoil"


def add_quote(db, listing, price, *, status="matched", seller=None, days=1, printing="Holofoil", condition="Near Mint"):
    a, _ = assess_text(db, db.get(Card, "c"), item(listing))
    a.status = a.image_status = status
    a.evidence = {**a.evidence, "seller": seller or listing}
    row = PriceObservation(fingerprint=f"{listing}-{price}-{days}", card_id="c", provider="ebay", provider_card_id=listing,
        variant_id=listing, price=Decimal(str(price)), currency="USD", printing=printing, condition=condition,
        observed_at=datetime.now(UTC)-timedelta(days=days), payload={"assessment_fingerprint": a.fingerprint, "item": item(listing)})
    db.add(row)
    return row


def test_shared_eligibility_and_group_statistics(db):
    add_quote(db, "a", 1, days=2)
    add_quote(db, "a", 30)
    add_quote(db, "b", 60)
    add_quote(db, "c", 90)
    add_quote(db, "fake", .01, status="rejected")
    add_quote(db, "pending", .02, status="pending")
    add_quote(db, "old", 9000, days=8)
    add_quote(db, "damaged", 2, condition="Damaged")
    add_quote(db, "different", 3, printing="Reverse Holofoil")
    db.commit()
    result = get_card_prices("c", Response(), days=1, db=db)
    group = next(g for g in result.listing_groups if g.printing == "Holofoil" and g.condition == "Near Mint")
    assert (group.lowest_matched_price, group.avg_listing_price, group.median_listing_price) == (30, 60, 60)
    assert group.listing_sample_count == group.listing_seller_count == 3
    assert result.excluded_listing_count == 2
    assert all(x.provider_card_id not in {"fake", "pending"} for x in result.observations)
    # The same SQL rule is usable before feed pagination and grading ranking.
    assert len(list(db.scalars(select(PriceObservation).where(eligible_observation())))) == 7


def test_single_seller_has_no_average(db):
    for i in range(3):
        add_quote(db, str(i), 10+i, seller="one")
    db.commit()
    group = next(g for g in get_card_prices("c", Response(), days=365, db=db).listing_groups if g.printing == "Holofoil")
    assert group.avg_listing_price is None
    assert group.median_listing_price is None
    assert group.lowest_matched_price == 10


def test_cross_card_assessment_cannot_be_reused(db):
    row = add_quote(db, "a", 1)
    db.add(Card(id="other", name="Other", number="5", set_id="base"))
    row.card_id = "other"
    db.commit()
    assert not list(db.scalars(select(PriceObservation).where(eligible_observation())))


@pytest.mark.parametrize("primary", [False, True])
def test_joined_live_totals_match_eligibility(db, monkeypatch, primary):
    from app.config import get_settings
    from app.services.collection_stats import live_observation_totals
    monkeypatch.setattr(get_settings(), "ppt_primary_enabled", primary)
    db.add(Card(id="other", name="Other", number="5", set_id="base"))
    for name in ("valid", "rejected", "pending", "wrong-card", "wrong-item", "old-version", "missing", "alias"):
        row = add_quote(db, name, 10)
        row.grading_company = "PSA"
        assessment = db.get(ListingAssessment, row.payload["assessment_fingerprint"])
        if name in ("rejected", "pending"):
            assessment.status = name
        elif name == "wrong-card":
            row.card_id = "other"
        elif name == "wrong-item":
            row.provider_card_id = "different-item"
        elif name == "old-version":
            assessment.version = "obsolete"
        elif name == "missing":
            row.payload = {}
        elif name == "alias":
            row.provider = "ebay_legacy"
    for provider in ("tcgapi", "pokemonpricetracker"):
        db.add(PriceObservation(fingerprint=provider, card_id="c", provider=provider,
            provider_card_id="x", variant_id="raw", price=20, currency="USD", grading_company="PSA"))
    db.commit()
    eligible = list(db.scalars(select(PriceObservation).where(eligible_observation())))
    expected = (sum(r.provider == "ebay" for r in eligible),
                sum(r.provider == "tcgapi" for r in eligible),
                sum(r.grading_company is not None for r in eligible))
    assert expected == (1, 1, 4 if primary else 3)
    assert live_observation_totals(db) == expected


def test_backfill_is_bounded_idempotent_and_preserves_source(db):
    for i in range(3):
        row = add_quote(db, str(i), i+1)
        row.payload = {"item": item(str(i)), "original": True}
    db.commit()
    assert backfill(db, 2) == 2
    assert backfill(db, 2) == 1
    assert backfill(db, 2) == 0
    assert all(x.payload["original"] for x in db.scalars(select(PriceObservation)))


def test_image_check_failure_retries_then_excludes(db, monkeypatch):
    import jobs.check_listing_images as job
    a, _ = assess_text(db, db.get(Card, "c"), item())
    monkeypatch.setattr(job, "compare_images", Mock(side_effect=ValueError("bad image")))
    for _ in range(3):
        check_one(db, a)
    assert a.attempts == 3 and a.status == "uncertain"
    assert a.reasons == ["image_check_failed"]


def test_contradicting_photo_overrides_match(db, monkeypatch):
    import jobs.check_listing_images as job
    a, _ = assess_text(db, db.get(Card, "c"), item(additionalImages=[{"imageUrl": "https://i.ebayimg.com/b.jpg"}]))
    monkeypatch.setattr(job, "compare_images", Mock(side_effect=[("matched", "match", {}), ("rejected", "wrong_number", {})]))
    check_one(db, a)
    assert a.status == "rejected"


def test_unvalidated_acceptance_stays_uncertain(db, monkeypatch):
    import jobs.check_listing_images as job
    a, _ = assess_text(db, db.get(Card, "c"), item())
    monkeypatch.setattr(job, "compare_images", lambda *args: ("matched", "match", {}))
    monkeypatch.setattr(job, "get_settings", lambda: SimpleNamespace(listing_image_acceptance_enabled=False))
    check_one(db, a)
    assert a.status == "uncertain"


def test_ocr_and_sealed_identity():
    assert image_number_matches("004/102", "4", 102)[0] == "matched"
    assert image_number_matches("004/130", "4", 102)[0] == "rejected"
    assert image_number_matches("HP 120", "4", 102)[0] == "uncertain"
    assert not is_sealed_product("Charizard")
    assert is_sealed_product("Pokemon GO Booster Box")


def test_price_only_update_reuses_check_but_changed_title_supersedes(db):
    card = db.get(Card, "c")
    a, _ = assess_text(db, card, item(price={"value": "20"}))
    a.status = "matched"
    assert assess_text(db, card, item(price={"value": "30"}))[0] is a
    assess_text(db, card, item(title="Charizard Base Set 4/102 Proxy"))
    assert a.status == "superseded"


def test_image_acceptance_when_enabled(db, monkeypatch):
    import jobs.check_listing_images as job
    a, _ = assess_text(db, db.get(Card, "c"), item())
    monkeypatch.setattr(job, "compare_images", lambda *args: ("matched", "match", {"image_sha256": "hash"}))
    monkeypatch.setattr(job, "get_settings", lambda: SimpleNamespace(listing_image_acceptance_enabled=True))
    check_one(db, a)
    assert a.status == "matched"
    assert a.evidence["image_sha256"] == "hash"


def test_migration_preserves_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    from alembic import command
    from alembic.config import Config
    from app.config import get_settings
    from sqlalchemy import inspect, text
    path = tmp_path / "migration.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "0007_market_data")
        engine = create_engine(f"sqlite:///{path}")
        before = {name: inspect(engine).get_columns(name) for name in ("cards", "sets")}
        command.upgrade(config, "head")
        assert "listing_assessments" in inspect(engine).get_table_names()
        for name in before:
            assert [c["name"] for c in before[name]] == [c["name"] for c in inspect(engine).get_columns(name)]
        command.downgrade(config, "0007_market_data")
        assert "listing_assessments" not in inspect(engine).get_table_names()
        assert "cards" in inspect(engine).get_table_names()
        engine.dispose()
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("extra", [
    {"itemGroupType": "SELLER_DEFINED_VARIATIONS"},
    {"buyingOptions": ["AUCTION"]},
    {"localizedAspects": [{"name": "Card Number", "value": "8/102"}]},
    {"localizedAspects": [{"name": "Set", "value": "Base Set 2"}]},
    {"localizedAspects": [{"name": "Graded", "value": "Yes"}]},
])
def test_conflicting_listing_specifics_are_excluded(db, extra):
    a, _ = assess_text(db, db.get(Card, "c"), item(**extra))
    assert a.status == "rejected"


def test_changed_identity_is_not_lost_to_observation_dedup(db):
    from jobs.collect_ebay_prices import _collect_ebay_for_card
    card = db.get(Card, "c")
    client = Mock()
    client.search_item_summaries.return_value = [item(price={"value": "30", "currency": "USD"})]
    _collect_ebay_for_card(db, card, client)
    db.commit()
    client.search_item_summaries.return_value = [item(price={"value": "30", "currency": "USD"}, image={"imageUrl": "https://i.ebayimg.com/changed.jpg"})]
    _collect_ebay_for_card(db, card, client)
    db.commit()
    rows = list(db.scalars(select(PriceObservation)))
    assert len(rows) == 2
    assert rows[0].payload["assessment_fingerprint"] != rows[1].payload["assessment_fingerprint"]


def test_retry_and_report_are_bounded(db):
    from jobs.check_listing_images import retry_images, assessment_report
    a, _ = assess_text(db, db.get(Card, "c"), item())
    a.status = a.image_status = "uncertain"
    a.reasons = ["image_acceptance_not_validated"]
    a.attempts = 1
    db.commit()
    assert assessment_report(db)["counts"] == {"uncertain": 1}
    assert retry_images(db, 1) == 1
    assert a.status == "pending" and a.attempts == 0
    assert assessment_report(db)["oldest_pending_at"]


def test_disabled_and_locked_worker_do_no_image_work(monkeypatch):
    import jobs.check_listing_images as job
    monkeypatch.setattr(job, "get_settings", lambda: SimpleNamespace(listing_image_checks_enabled=False))
    assert job.check_listing_images() == {"disabled": True}
    monkeypatch.setattr(job, "get_settings", lambda: SimpleNamespace(listing_image_checks_enabled=True, redis_url="redis://unused"))
    client = Mock()
    client.lock.return_value.acquire.return_value = False
    monkeypatch.setattr(job.redis.Redis, "from_url", lambda *args, **kwargs: client)
    assert job.check_listing_images() == {"busy": True}


def test_identity_rechecks_old_images_and_does_not_treat_non_holo_as_holo(db):
    a, result = assess_text(db, db.get(Card, "c"), item(title="Charizard Base Set 4/102 Non-Holo Near Mint"))
    assert result.printing == "Normal"
    a.status = a.image_status = "matched"
    a.checked_at = datetime.now(UTC) - timedelta(days=8)
    db.commit()
    a, _ = assess_text(db, db.get(Card, "c"), item(title="Charizard Base Set 4/102 Non-Holo Near Mint"))
    assert a.status == "pending" and a.attempts == 0


def test_analytics_windows_exclude_unmatched_and_ppt(db):
    from app.services.observation_stats import card_observation_stats
    now = datetime.now(UTC)
    start = now - timedelta(days=7)
    for label, value, at, status in (
        ('current', 10, start, 'matched'),
        ('prior', 20, start-timedelta(seconds=1), 'matched'),
        ('end', 30, now, 'matched'),
        ('fake-window', 9999, now-timedelta(days=1), 'rejected'),
    ):
        row = add_quote(db, label, value, status=status)
        row.observed_at = at
    db.add(PriceObservation(fingerprint='ppt-window', card_id='c', provider='pokemonpricetracker',
        provider_card_id='x', variant_id='raw', price=5000, currency='USD', observed_at=start))
    db.commit()
    stats = card_observation_stats(start, now, start-timedelta(days=7), start)
    row = db.execute(select(stats)).mappings().one()
    assert row['obs_cnt'] == 3
    assert row['total_price'] == 60
    assert row['current_volume'] == 10 and row['current_count'] == 1
    assert row['prior_volume'] == 20
    assert row['max_price'] == 30
