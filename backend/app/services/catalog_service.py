from app.common.cache import TTLCache
import logging
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import case, func, not_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.common.formatters import escape_like
from app.common.redis import get_redis
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.schemas.cards import (
    CardSummary,
    PokemonCardsResponse,
    PokemonSetCount,
    PokemonVolumeItem,
    PokemonVolumeResponse,
    SetStatsResponse,
)

logger = logging.getLogger(__name__)


def build_card_summary(
    card: Card,
    card_set: Set,
    market_price: object | None = None,
    market_currency: str | None = None,
    last_updated_at: datetime | None = None,
) -> CardSummary:
    """Build a standard CardSummary response object."""
    return CardSummary(
        id=card.id,
        name=card.name,
        set_id=card.set_id,
        set_name=card_set.name,
        number=card.number,
        printed_total=card.printed_total,
        rarity=card.rarity,
        image_url=f"/cards/{card.id}/image",
        market_price=float(market_price) if market_price is not None else None,
        market_currency=market_currency,
        last_updated_at=last_updated_at or card.updated_at,
    )


# Common PokéAPI form suffixes to strip when matching base TCG card names
POKEMON_FORM_SUFFIXES: tuple[str, ...] = (
    "shield", "blade",
    "normal", "altered", "origin",
    "land", "sky",
    "red striped", "blue striped", "white striped",
    "standard", "zen",
    "incarnate", "therian",
    "ordinary", "resolute",
    "aria", "pirouette",
    "male", "female",
    "average", "small", "large", "super",
    "50", "10", "complete",
    "baile", "pom pom", "pau", "sensu",
    "midday", "midnight", "dusk",
    "solo", "school",
    "red meteor", "meteor",
    "disguised", "busted",
    "amped", "low key",
    "ice", "noice",
    "full belly", "hangry",
    "single strike", "rapid strike",
    "family of four", "family of three",
    "green plumage", "blue plumage", "yellow plumage", "white plumage",
    "zero", "hero",
    "curly", "droopy", "stretchy",
    "two segment", "three segment",
    "plant", "sandy", "trash",
)


def get_pokemon_search_terms(name: str) -> list[str]:
    """Generate search variations for a Pokémon character name."""
    raw = name.strip()
    if not raw:
        return []
    ascii_name = unicodedata.normalize("NFKD", raw).encode("ASCII", "ignore").decode("utf-8")
    terms = {raw, ascii_name, raw.replace("-", " ")}
    lower = raw.lower()

    # Strip PokéAPI form variations (e.g. "Aegislash Shield" -> "Aegislash", "Deoxys Normal" -> "Deoxys")
    normalized_space = re.sub(r"[\s-]+", " ", raw).strip()
    for suffix in POKEMON_FORM_SUFFIXES:
        pattern = rf"^(.*?)\s+{re.escape(suffix)}$"
        m = re.match(pattern, normalized_space, re.IGNORECASE)
        if m:
            base = m.group(1).strip()
            if base:
                terms.add(base)
                terms.add(base.replace("-", " "))

    if "aegislash" in lower:
        terms.add("Aegislash")
    if "mr." in lower or "mr " in lower:
        terms.add(raw.replace("Mr.", "Mr").strip())
        terms.add(raw.replace("Mr ", "Mr. ").strip())
    if "nidoran" in lower:
        if "f" in lower or "♀" in raw:
            terms.update(["Nidoran F", "Nidoran (Female)"])
        elif "m" in lower or "♂" in raw:
            terms.update(["Nidoran M", "Nidoran (Male)"])
        else:
            terms.add("Nidoran")
    if "type:" in lower or "type " in lower:
        terms.update(["Type: Null", "Type Null"])
    if "farfetch" in lower:
        terms.update(["Farfetch'd", "Farfetchd", "Farfetch"])
    if "sirfetch" in lower:
        terms.update(["Sirfetch'd", "Sirfetchd", "Sirfetch"])
    return [t for t in terms if t]


from app.common.pokemon_data import (
    POKEMON_DEX_NUMBERS,
    POKEMON_NAMES_BY_LENGTH,
    get_pokemon_canonical_name,
    get_pokemon_dex_number,
    get_pokemon_sprite_url,
)

# Top established market leaders tracked for volume analytics
POKEMON_TOP_50_NAMES: list[str] = [
    "Charizard", "Pikachu", "Gengar", "Mew", "Umbreon",
    "Mewtwo", "Rayquaza", "Dragonite", "Lugia", "Blastoise",
    "Eevee", "Gyarados", "Venusaur", "Magikarp", "Snorlax",
    "Latias", "Psyduck", "Espeon", "Greninja", "Charmander",
    "Latios", "Mimikyu", "Zapdos", "Giratina", "Moltres",
    "Squirtle", "Sylveon", "Reshiram", "Zekrom", "Tyranitar", "Alakazam",
    "Deoxys", "Raichu", "Gardevoir", "Articuno", "Bulbasaur",
    "Lucario", "Darkrai", "Flareon", "Vaporeon", "Jolteon",
    "Celebi", "Jirachi", "Kyogre", "Groudon", "Suicune",
    "Entei", "Raikou", "Dialga", "Palkia", "Arceus",
]

_MASTER_POKEMON_REGEX = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in POKEMON_NAMES_BY_LENGTH) + r")\b",
    re.IGNORECASE,
)
_POKEMON_NAME_CANONICAL_MAP: dict[str, str] = {name.lower(): name for name in POKEMON_DEX_NUMBERS}

_pokemon_volume_cache = TTLCache(max_entries=64, ttl=300)
POKEMON_VOLUME_CACHE_TTL = 300  # 5 minutes


def match_to_pokemon(card_name: str) -> str | None:
    """Attribute a card name to a Pokémon character via word-boundary regex across all species."""
    if not card_name:
        return None
    m = _MASTER_POKEMON_REGEX.search(card_name)
    if m:
        matched_str = m.group(1).lower()
        return _POKEMON_NAME_CANONICAL_MAP.get(matched_str)
    return None


def get_cards_for_pokemon(
    db: Session,
    name: str,
    limit: int | None = None,
) -> list[Card]:
    """Retrieve all Card models in the catalog belonging to a specific Pokémon character."""
    clean_name = name.strip()
    search_terms = get_pokemon_search_terms(clean_name)
    if not search_terms:
        return []

    name_filters = [
        Card.name.ilike(f"%{escape_like(term)}%", escape="\\")
        for term in search_terms
    ]
    base_conditions = [
        or_(*name_filters),
        Card.name.not_ilike("%code card%"),
        or_(Card.rarity.is_(None), Card.rarity.not_ilike("%code card%")),
    ]
    if clean_name.lower() == "mew":
        base_conditions.append(
            or_(
                Card.name.not_ilike("%mewtwo%"),
                Card.name.ilike("%mew &%"),
                Card.name.ilike("%& mew%"),
            )
        )

    stmt = (
        select(Card)
        .options(joinedload(Card.set))
        .join(Set, Card.set_id == Set.id)
        .where(*base_conditions)
        .order_by(Card.name.asc(), Card.id.asc())
    )
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).unique())


def query_pokemon_cards(
    db: Session,
    name: str,
    *,
    set_id: str | None = None,
    game: Literal["all", "pokemon", "pokemon-japan"] = "all",
    sort_by: Literal["price_desc", "price_asc", "number_asc", "number_desc", "name", "set"] = "price_desc",
    limit: int = 50,
    offset: int = 0,
) -> PokemonCardsResponse:
    """Retrieve all trading cards for a specific Pokémon character."""
    clean_name = name.strip()
    search_terms = get_pokemon_search_terms(clean_name)
    if not search_terms:
        return PokemonCardsResponse(
            pokemon_name=clean_name,
            total_cards=0,
            highest_price=None,
            lowest_price=None,
            available_sets=[],
            cards=[],
        )

    name_filters = [
        Card.name.ilike(f"%{escape_like(term)}%", escape="\\")
        for term in search_terms
    ]
    base_conditions = [
        or_(*name_filters),
        Card.name.not_ilike("%code card%"),
        or_(Card.rarity.is_(None), Card.rarity.not_ilike("%code card%")),
    ]

    # Special boundary exclusion: Mew should not match Mewtwo unless tag-teamed
    if clean_name.lower() == "mew":
        base_conditions.append(
            or_(
                Card.name.not_ilike("%mewtwo%"),
                Card.name.ilike("%mew &%"),
                Card.name.ilike("%& mew%"),
            )
        )

    # Game language filtering on base conditions
    if game == "pokemon":
        base_conditions.append(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))
    elif game == "pokemon-japan":
        base_conditions.append(Set.series == "Pokemon Japan")

    # 1. Total matching cards count
    total_cards = db.scalar(
        select(func.count(Card.id))
        .join(Set, Card.set_id == Set.id)
        .where(*base_conditions)
    ) or 0

    # 2. Price summary across all matching cards (highest & lowest market price)
    matching_cards_subquery = (
        select(Card.id)
        .join(Set, Card.set_id == Set.id)
        .where(*base_conditions)
    )
    price_stats = db.execute(
        select(
            func.max(PriceObservation.price),
            func.min(PriceObservation.price),
        ).where(
            PriceObservation.card_id.in_(matching_cards_subquery),
            PriceObservation.provider == "tcgapi",
            PriceObservation.grading_company.is_(None),
            PriceObservation.price > 0,
        )
    ).one_or_none()

    highest_price = float(price_stats[0]) if price_stats and price_stats[0] is not None else None
    lowest_price = float(price_stats[1]) if price_stats and price_stats[1] is not None else None

    # 3. Available sets breakdown
    set_count_rows = db.execute(
        select(Set.id, Set.name, func.count(Card.id).label("card_count"))
        .join(Set, Card.set_id == Set.id)
        .where(*base_conditions)
        .group_by(Set.id, Set.name)
        .order_by(func.count(Card.id).desc(), Set.name.asc())
    ).all()
    available_sets = [
        PokemonSetCount(id=str(row[0]), name=str(row[1]), count=int(row[2]))
        for row in set_count_rows
    ]

    # 4. Detailed card query with set filter and sorting applied
    detail_conditions = list(base_conditions)
    if set_id:
        detail_conditions.append(Card.set_id == set_id)

    latest_price = (
        select(PriceObservation.price)
        .where(
            PriceObservation.card_id == Card.id,
            PriceObservation.provider == "tcgapi",
            PriceObservation.grading_company.is_(None),
        )
        .order_by(
            PriceObservation.provider_updated_at.desc().nullslast(),
            PriceObservation.observed_at.desc(),
            PriceObservation.id.desc(),
        )
        .limit(1)
        .correlate(Card)
        .scalar_subquery()
    )
    latest_currency = (
        select(PriceObservation.currency)
        .where(
            PriceObservation.card_id == Card.id,
            PriceObservation.provider == "tcgapi",
            PriceObservation.grading_company.is_(None),
        )
        .order_by(
            PriceObservation.provider_updated_at.desc().nullslast(),
            PriceObservation.observed_at.desc(),
            PriceObservation.id.desc(),
        )
        .limit(1)
        .correlate(Card)
        .scalar_subquery()
    )
    latest_synced = (
        select(func.max(ProviderCardState.last_synced_at))
        .where(ProviderCardState.card_id == Card.id)
        .correlate(Card)
        .scalar_subquery()
    )

    query_stmt = (
        select(Card, Set, latest_price, latest_currency, latest_synced)
        .join(Set, Card.set_id == Set.id)
        .where(*detail_conditions)
    )

    is_none_or_sealed = or_(
        Card.rarity.is_(None),
        Card.rarity == "",
        Card.rarity == "None",
        Card.rarity.ilike("none"),
    )
    is_sealed = case((is_none_or_sealed, 0), else_=1)

    if sort_by == "price_asc":
        order = (
            latest_price.asc().nullslast(),
            Card.name.asc(),
            Card.id.asc(),
        )
    elif sort_by == "number_asc":
        order = (
            Set.name.asc(),
            is_sealed.asc(),
            func.length(Card.number).asc(),
            Card.number.asc(),
            Card.name.asc(),
            Card.id.asc(),
        )
    elif sort_by == "number_desc":
        order = (
            Set.name.asc(),
            is_sealed.asc(),
            func.length(Card.number).desc(),
            Card.number.desc(),
            Card.name.asc(),
            Card.id.asc(),
        )
    elif sort_by == "name":
        order = (
            Card.name.asc(),
            Set.name.asc(),
            Card.number.asc(),
            Card.id.asc(),
        )
    elif sort_by == "set":
        order = (
            Set.release_date.desc().nullslast(),
            Set.name.asc(),
            is_sealed.asc(),
            func.length(Card.number).asc(),
            Card.number.asc(),
            Card.name.asc(),
            Card.id.asc(),
        )
    else:  # default "price_desc"
        order = (
            latest_price.desc().nullslast(),
            Card.name.asc(),
            Card.id.asc(),
        )

    rows = db.execute(query_stmt.order_by(*order).offset(offset).limit(limit)).all()
    cards = [
        build_card_summary(card, card_set, card_price, card_curr, card_sync)
        for card, card_set, card_price, card_curr, card_sync in rows
    ]

    return PokemonCardsResponse(
        pokemon_name=clean_name,
        total_cards=total_cards,
        highest_price=highest_price,
        lowest_price=lowest_price,
        available_sets=available_sets,
        cards=cards,
    )


def _bulk_pokemon_window_stats(
    db: Session,
    start_time: datetime | None,
    end_time: datetime | None = None,
) -> dict[str, tuple[float, int]]:
    """Return (volume_usd, sales_count) per tracked Pokémon, filtered by optional [start_time, end_time)."""
    name_filter = or_(*[Card.name.ilike(f"%{n}%") for n in POKEMON_TOP_50_NAMES])
    stmt = (
        select(
            Card.name,
            func.sum(PriceObservation.price).label("vol"),
            func.count(PriceObservation.id).label("sales_cnt"),
        )
        .join(PriceObservation, PriceObservation.card_id == Card.id)
        .where(name_filter, Card.name.not_ilike("%code card%"))
        .group_by(Card.name)
    )
    if start_time is not None:
        stmt = stmt.where(PriceObservation.observed_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(PriceObservation.observed_at < end_time)
    rows = db.execute(stmt).all()
    stats: dict[str, tuple[float, int]] = {n: (0.0, 0) for n in POKEMON_TOP_50_NAMES}
    for card_name, amount, cnt in rows:
        poke = match_to_pokemon(card_name)
        if poke is not None and poke in stats:
            cur_vol, cur_cnt = stats[poke]
            stats[poke] = (cur_vol + float(amount or 0), cur_cnt + int(cnt or 0))
    return stats


def calculate_top_pokemon_volume(
    db: Session,
    *,
    timeframe: Literal["24h", "7d", "30d", "all_time", "2026_ytd"] = "7d",
    sort_by: Literal["volume_desc", "sales_desc", "growth_desc", "avg_price_desc"] = "volume_desc",
    q: str | None = None,
) -> PokemonVolumeResponse:
    """Calculate top 50 Pokémon ranked by aggregated observed market value, sales count, or momentum."""
    clean_q = (q or "").strip().lower()
    cache_key = f"{timeframe}:{sort_by}:{clean_q}"
    redis_key = f"cardboarddex:top_volume:{cache_key}"
    now = datetime.now(UTC)

    # 1. Try Redis cache first
    r = get_redis()
    if r is not None:
        try:
            cached_data = r.get(redis_key)
            if cached_data:
                return PokemonVolumeResponse.model_validate_json(cached_data)
        except (RedisError, Exception) as exc:
            logger.warning("Redis volume cache read failed error=%s: %s", type(exc).__name__, exc)

    # 2. Try in-process fallback
    if cache_key in _pokemon_volume_cache:
        cached_time, cached_res = _pokemon_volume_cache[cache_key]
        if (now - cached_time).total_seconds() < POKEMON_VOLUME_CACHE_TTL:
            return cached_res

    # Define current and prior windows for period-over-period momentum
    if timeframe == "24h":
        cur_start: datetime | None = now - timedelta(hours=24)
        cur_end: datetime | None = now
        prior_start: datetime | None = now - timedelta(hours=48)
        prior_end: datetime | None = now - timedelta(hours=24)
    elif timeframe == "7d":
        cur_start = now - timedelta(days=7)
        cur_end = now
        prior_start = now - timedelta(days=14)
        prior_end = now - timedelta(days=7)
    elif timeframe == "30d":
        cur_start = now - timedelta(days=30)
        cur_end = now
        prior_start = now - timedelta(days=60)
        prior_end = now - timedelta(days=30)
    elif timeframe == "2026_ytd":
        cur_start = datetime(2026, 1, 1, tzinfo=UTC)
        cur_end = now
        prior_start = now - timedelta(days=30)
        prior_end = now
    else:  # all_time
        cur_start = None
        cur_end = None
        prior_start = now - timedelta(days=30)
        prior_end = now

    # Current window stats & prior window stats
    curr_stats = _bulk_pokemon_window_stats(db, cur_start, cur_end)
    prior_stats = _bulk_pokemon_window_stats(db, prior_start, prior_end)

    # Bulk Database Enrichment: card counts, top card, catalog average price
    name_filter = or_(*[Card.name.ilike(f"%{n}%") for n in POKEMON_TOP_50_NAMES])
    enrichment_rows = db.execute(
        select(Card.id, Card.name, PriceObservation.price)
        .outerjoin(PriceObservation, PriceObservation.card_id == Card.id)
        .where(name_filter, Card.name.not_ilike("%code card%"))
    ).all()

    cards_per_pokemon: dict[str, set[str]] = {n: set() for n in POKEMON_TOP_50_NAMES}
    price_totals: dict[str, float] = {n: 0.0 for n in POKEMON_TOP_50_NAMES}
    price_counts: dict[str, int] = {n: 0 for n in POKEMON_TOP_50_NAMES}
    top_cards: dict[str, tuple[str, str, float] | None] = {n: None for n in POKEMON_TOP_50_NAMES}

    for card_id, card_name, obs_price in enrichment_rows:
        poke = match_to_pokemon(card_name)
        if poke is None or poke not in cards_per_pokemon:
            continue
        cards_per_pokemon[poke].add(card_id)
        if obs_price is not None:
            price_flt = float(obs_price)
            price_totals[poke] += price_flt
            price_counts[poke] += 1
            current_top = top_cards[poke]
            if current_top is None or price_flt > current_top[2]:
                top_cards[poke] = (card_id, card_name, price_flt)

    # Build items (unsorted)
    search_filter = (q or "").strip().lower()
    raw_items: list[dict[str, Any]] = []

    for poke_name in POKEMON_TOP_50_NAMES:
        if search_filter and search_filter not in poke_name.lower():
            continue

        cur_vol, cur_sales = curr_stats[poke_name]
        prior_vol, _ = prior_stats[poke_name]

        if prior_vol > 0:
            momentum_pct = round(((cur_vol - prior_vol) / prior_vol) * 100, 1)
        elif cur_vol > 0:
            momentum_pct = 100.0
        else:
            momentum_pct = 0.0

        momentum_trend = "up" if momentum_pct > 1.0 else "down" if momentum_pct < -1.0 else "flat"

        cards_count = len(cards_per_pokemon[poke_name])
        # Average card price: window average if sales present, else catalog average
        if cur_sales > 0:
            avg_price = round(cur_vol / cur_sales, 2)
        elif price_counts[poke_name] > 0:
            avg_price = round(price_totals[poke_name] / price_counts[poke_name], 2)
        else:
            avg_price = None

        top_card = top_cards[poke_name]

        raw_items.append({
            "pokemon_name": poke_name,
            "volume_usd": cur_vol,
            "sales_count": cur_sales,
            "momentum_pct": momentum_pct,
            "momentum_trend": momentum_trend,
            "cards_count": cards_count,
            "avg_price": avg_price,
            "top_card_name": top_card[1] if top_card else None,
            "top_card_price": top_card[2] if top_card else None,
            "top_card_id": top_card[0] if top_card else None,
        })

    # Sort items based on sort_by metric
    if sort_by == "sales_desc":
        raw_items.sort(key=lambda x: (x["sales_count"], x["volume_usd"]), reverse=True)
    elif sort_by == "growth_desc":
        raw_items.sort(key=lambda x: (x["momentum_pct"], x["volume_usd"]), reverse=True)
    elif sort_by == "avg_price_desc":
        raw_items.sort(key=lambda x: (x["avg_price"] or 0.0, x["volume_usd"]), reverse=True)
    else:  # volume_desc (default)
        raw_items.sort(key=lambda x: x["volume_usd"], reverse=True)

    total_vol = 0.0
    total_sales = 0
    items: list[PokemonVolumeItem] = []
    for rank, entry in enumerate(raw_items[:50], start=1):
        poke_name = entry["pokemon_name"]
        volume_usd = entry["volume_usd"]
        sales_cnt = entry["sales_count"]
        dex = POKEMON_DEX_NUMBERS.get(poke_name, 0)
        sprite_url = (
            f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/"
            f"pokemon/other/official-artwork/{dex}.png"
        )
        if volume_usd >= 1_000_000:
            volume_formatted = f"${volume_usd / 1_000_000:.1f}M"
        elif volume_usd >= 1_000:
            volume_formatted = f"${volume_usd / 1_000:.1f}K"
        else:
            volume_formatted = f"${volume_usd:,.2f}"

        total_vol += volume_usd
        total_sales += sales_cnt

        items.append(
            PokemonVolumeItem(
                rank=rank,
                pokemon_name=poke_name,
                dex_number=dex,
                sprite_url=sprite_url,
                volume_usd=round(volume_usd, 2),
                volume_formatted=volume_formatted,
                sales_count=sales_cnt,
                momentum_percentage=entry["momentum_pct"],
                momentum_trend=entry["momentum_trend"],
                yoy_percentage=entry["momentum_pct"],
                yoy_trend=entry["momentum_trend"],
                cards_count=entry["cards_count"],
                avg_card_price=entry["avg_price"],
                top_card_name=entry["top_card_name"],
                top_card_price=entry["top_card_price"],
                top_card_id=entry["top_card_id"],
            )
        )

    response = PokemonVolumeResponse(
        timeframe=timeframe,
        sort_by=sort_by,
        total_volume_usd=round(total_vol, 2),
        total_sales_count=total_sales,
        total_pokemon=len(items),
        items=items,
        updated_at=now,
    )
    if r is not None:
        try:
            r.setex(redis_key, POKEMON_VOLUME_CACHE_TTL, response.model_dump_json())
        except (RedisError, Exception) as exc:
            logger.warning("Redis volume cache write failed error=%s: %s", type(exc).__name__, exc)

    _pokemon_volume_cache[cache_key] = (now, response)
    return response


SET_STATS_CACHE_TTL = 300  # 5 minutes


def get_set_statistics(
    db: Session,
    set_id: str,
    *,
    q: str = "",
    hide_sealed: bool = True,
    sealed_only: bool = False,
    game: Literal["all", "pokemon", "pokemon-japan"] = "all",
    min_price: float | None = None,
    max_price: float | None = None,
) -> SetStatsResponse:
    """Calculate aggregate total price and card counts for a set (or filtered set)."""
    clean_q = q.strip()
    cache_key = f"{set_id}:{game}:{hide_sealed}:{sealed_only}:{clean_q}:{min_price}:{max_price}"
    redis_key = f"cardboarddex:set_stats:{cache_key}"

    r = get_redis()
    if r is not None:
        try:
            cached_data = r.get(redis_key)
            if cached_data:
                return SetStatsResponse.model_validate_json(cached_data)
        except (RedisError, Exception) as exc:
            logger.warning("Redis set_stats cache read failed error=%s: %s", type(exc).__name__, exc)

    # Verify set exists
    target_set = db.get(Set, set_id)
    if target_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Set '{set_id}' not found")
    set_name = target_set.name

    latest_price = (
        select(PriceObservation.price)
        .where(
            PriceObservation.card_id == Card.id,
            PriceObservation.provider == "tcgapi",
            PriceObservation.grading_company.is_(None),
        )
        .order_by(
            PriceObservation.provider_updated_at.desc().nullslast(),
            PriceObservation.observed_at.desc(),
            PriceObservation.id.desc(),
        )
        .limit(1)
        .correlate(Card)
        .scalar_subquery()
    )

    latest_currency = (
        select(PriceObservation.currency)
        .where(
            PriceObservation.card_id == Card.id,
            PriceObservation.provider == "tcgapi",
            PriceObservation.grading_company.is_(None),
        )
        .order_by(
            PriceObservation.provider_updated_at.desc().nullslast(),
            PriceObservation.observed_at.desc(),
            PriceObservation.id.desc(),
        )
        .limit(1)
        .correlate(Card)
        .scalar_subquery()
    )

    subq = (
        select(
            Card.id.label("card_id"),
            latest_price.label("price"),
            latest_currency.label("currency"),
        )
        .join(Set, Card.set_id == Set.id)
        .where(
            Card.set_id == set_id,
            Card.name.not_ilike("%code card%"),
            or_(Card.rarity.is_(None), Card.rarity.not_ilike("%code card%")),
        )
    )

    if game == "pokemon":
        subq = subq.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))
    elif game == "pokemon-japan":
        subq = subq.where(Set.series == "Pokemon Japan")

    if clean_q:
        pattern = f"%{escape_like(clean_q)}%"
        subq = subq.where(
            or_(Card.name.ilike(pattern, escape="\\"), Set.name.ilike(pattern, escape="\\"))
        )

    is_none_or_sealed = or_(
        Card.rarity.is_(None),
        Card.rarity == "",
        Card.rarity == "None",
        Card.rarity.ilike("none"),
    )
    if sealed_only:
        subq = subq.where(is_none_or_sealed)
    elif hide_sealed:
        subq = subq.where(not_(is_none_or_sealed))

    if min_price is not None and min_price > 0:
        subq = subq.where(latest_price.isnot(None), latest_price >= min_price)
    if max_price is not None:
        subq = subq.where(latest_price.isnot(None), latest_price <= max_price)

    subquery_alias = subq.subquery()
    stats_query = select(
        func.count(subquery_alias.c.card_id).label("total_cards"),
        func.count(subquery_alias.c.price).label("priced_cards"),
        func.coalesce(func.sum(subquery_alias.c.price), 0.0).label("total_price"),
        func.coalesce(func.avg(subquery_alias.c.price), 0.0).label("avg_price"),
        func.max(subquery_alias.c.currency).label("currency"),
    )

    row = db.execute(stats_query).one_or_none()
    total_cards = int(row.total_cards) if row and row.total_cards is not None else 0
    priced_cards = int(row.priced_cards) if row and row.priced_cards is not None else 0
    total_price = round(float(row.total_price), 2) if row and row.total_price is not None else 0.0
    avg_price = round(float(row.avg_price), 2) if row and priced_cards > 0 and row.avg_price is not None else None
    currency = str(row.currency) if row and row.currency else "USD"

    response = SetStatsResponse(
        set_id=set_id,
        set_name=set_name,
        total_cards=total_cards,
        priced_cards=priced_cards,
        total_price=total_price,
        avg_price=avg_price,
        currency=currency,
    )

    if r is not None:
        try:
            r.setex(redis_key, SET_STATS_CACHE_TTL, response.model_dump_json())
        except (RedisError, Exception) as exc:
            logger.warning("Redis set_stats cache write failed error=%s: %s", type(exc).__name__, exc)

    return response

