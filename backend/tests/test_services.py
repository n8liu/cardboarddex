from datetime import date, datetime, UTC
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Card, PriceObservation, Set
from app.services.catalog_service import (
    build_card_summary,
    get_pokemon_search_terms,
    match_to_pokemon,
    query_pokemon_cards,
)
from app.services.grading_service import calculate_grading_profit
from app.services.sealed_service import (
    calculate_sealed_signals,
    classify_sealed_product,
)


@pytest.fixture
def memory_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_classify_sealed_product():
    assert classify_sealed_product("Surging Sparks Booster Box")[0] == "Booster Box"
    assert classify_sealed_product("151 Elite Trainer Box")[0] == "Elite Trainer Box"
    assert classify_sealed_product("Paldean Fates ETB")[0] == "Elite Trainer Box"
    assert classify_sealed_product("Crown Zenith Booster Bundle")[0] == "Booster Bundle"
    assert classify_sealed_product("Evolving Skies Sealed Case")[0] == "Case"
    assert classify_sealed_product("Base Set Booster Pack")[0] == "Booster Pack"
    assert classify_sealed_product("Ultra Premium Collection Box")[0] == "Collection Box"
    assert classify_sealed_product("Single Blister Pack")[0] == "Blister Pack"
    assert classify_sealed_product("Random Mystery Item")[0] == "Sealed Product"


def test_get_pokemon_search_terms():
    assert "Charizard" in get_pokemon_search_terms("Charizard")
    # Edge cases
    farfetchd = get_pokemon_search_terms("Farfetch'd")
    assert "Farfetchd" in farfetchd or "Farfetch'd" in farfetchd

    nidoran_f = get_pokemon_search_terms("Nidoran♀")
    assert any("Female" in term or "Nidoran F" in term for term in nidoran_f)

    type_null = get_pokemon_search_terms("Type: Null")
    assert any("Type Null" in term for term in type_null)

    # PokéAPI form-suffixed names must resolve to base TCG species names
    aegislash_terms = get_pokemon_search_terms("Aegislash Shield")
    assert "Aegislash" in aegislash_terms
    aegislash_slug_terms = get_pokemon_search_terms("aegislash-shield")
    assert "Aegislash" in aegislash_slug_terms

    deoxys_terms = get_pokemon_search_terms("Deoxys Normal")
    assert "Deoxys" in deoxys_terms
    giratina_terms = get_pokemon_search_terms("Giratina Altered")
    assert "Giratina" in giratina_terms
    mimikyu_terms = get_pokemon_search_terms("Mimikyu Disguised")
    assert "Mimikyu" in mimikyu_terms

    # Multi-word Pokémon must preserve their full names
    tapu_koko = get_pokemon_search_terms("Tapu Koko")
    assert "Tapu Koko" in tapu_koko
    iron_bundle = get_pokemon_search_terms("Iron Bundle")
    assert "Iron Bundle" in iron_bundle

    # Empty string
    assert get_pokemon_search_terms("") == []


def test_match_to_pokemon_word_boundary():
    # Boundary test: Mew should not match Mewtwo
    assert match_to_pokemon("Mewtwo GX") == "Mewtwo"
    assert match_to_pokemon("Mew ex") == "Mew"
    assert match_to_pokemon("Charizard ex") == "Charizard"
    assert match_to_pokemon("Non-existent Digimon") is None


def test_build_card_summary():
    card = Card(
        id="base1-4",
        name="Charizard",
        set_id="base1",
        number="4",
        printed_total=102,
        rarity="Rare Holo",
        image_url="https://images.tcgapi.com/base1-4.png",
    )
    cset = Set(id="base1", name="Base Set", series="Base", printed_total=102)
    summary = build_card_summary(
        card=card,
        card_set=cset,
        market_price=350.0,
        market_currency="USD",
    )
    assert summary.id == "base1-4"
    assert summary.name == "Charizard"
    assert summary.set_name == "Base Set"
    assert summary.market_price == 350.0
    assert summary.market_currency == "USD"


def test_calculate_grading_profit_empty_db(memory_db):
    res = calculate_grading_profit(memory_db, q="Charizard")
    assert res.total_cards == 0
    assert res.items == []


def test_calculate_grading_profit_with_comps(memory_db):
    cset = Set(id="base1", name="Base Set", release_date=date(1999, 1, 9))
    card = Card(id="base1-4", name="Charizard", set_id="base1", number="4", rarity="Rare Holo")
    memory_db.add_all([cset, card])
    memory_db.flush()

    # Raw observation
    obs_raw = PriceObservation(
        fingerprint="fp-raw-1",
        card_id="base1-4",
        provider="tcgapi",
        provider_card_id="tcg-base1-4",
        variant_id="default",
        price=Decimal("100.00"),
        observed_at=datetime.now(UTC),
    )
    # PSA 10 observation
    obs_psa10 = PriceObservation(
        fingerprint="fp-psa10-1",
        card_id="base1-4",
        provider="ebay",
        provider_card_id="ebay-psa10-1",
        variant_id="psa-10",
        grading_company="PSA",
        grade=Decimal("10.0"),
        price=Decimal("1000.00"),
        observed_at=datetime.now(UTC),
    )
    # PSA 9 observation
    obs_psa9 = PriceObservation(
        fingerprint="fp-psa9-1",
        card_id="base1-4",
        provider="ebay",
        provider_card_id="ebay-psa9-1",
        variant_id="psa-9",
        grading_company="PSA",
        grade=Decimal("9.0"),
        price=Decimal("250.00"),
        observed_at=datetime.now(UTC),
    )
    memory_db.add_all([obs_raw, obs_psa10, obs_psa9])
    memory_db.commit()

    res = calculate_grading_profit(memory_db, grading_fee=25.0)
    assert res.total_cards == 1
    item = res.items[0]
    assert item.card_id == "base1-4"
    assert item.raw_price == 100.0
    assert item.psa10_price == 1000.0
    # Cost = 100 + 25 = 125. Profit PSA 10 = 1000 - 125 = 875.0
    assert item.psa10_profit == 875.0
    # ROI = (875 / 125) * 100 = 700.0%
    assert item.psa10_roi == 700.0
    # PSA 9 profit = 250 - 125 = 125.0
    assert item.psa9_profit == 125.0
    assert item.psa9_safe is True
    assert item.spread_multiplier == 10.0


def test_calculate_sealed_signals_scoring(memory_db):
    cset = Set(id="swsh7", name="Evolving Skies", release_date=date(2021, 8, 27))
    sealed_box = Card(id="swsh7-box", name="Evolving Skies Booster Box", set_id="swsh7", number="BB", rarity=None)
    memory_db.add_all([cset, sealed_box])
    memory_db.flush()

    obs = PriceObservation(
        fingerprint="fp-sealed-1",
        card_id="swsh7-box",
        provider="tcgapi",
        provider_card_id="tcg-swsh7-box",
        variant_id="default",
        price=Decimal("750.00"),
        observed_at=datetime.now(UTC),
        payload={
            "market_price": 750.0,
            "total_listings": 10,
            "low_price": 720.0,
            "median_price": 760.0,
            "buylist_price": 600.0,
            "price_change_30d": 12.5,
        },
    )
    memory_db.add(obs)
    memory_db.commit()

    res = calculate_sealed_signals(memory_db)
    assert res.total_items == 1
    item = res.items[0]
    assert item.product_type == "Booster Box"
    assert item.supply_rating == "Ultra Scarce"
    assert item.supply_score == 30
    assert item.signal_score >= 60
    assert item.signal_label in ("STRONG BUY", "BUY")
