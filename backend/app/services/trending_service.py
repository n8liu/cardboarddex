import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.redis import get_redis
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.schemas.cards import (
    TrendingCardItem,
    TrendingDashboardResponse,
    TrendingPokemonItem,
)
from app.services.catalog_service import (
    POKEMON_DEX_NUMBERS,
    POKEMON_TOP_50_NAMES,
    calculate_top_pokemon_volume,
    match_to_pokemon,
)

logger = logging.getLogger(__name__)

# Redis Analytics Keys
REDIS_KEY_CARD_CLICKS = "cardboarddex:analytics:card_clicks"
REDIS_KEY_POKE_CLICKS = "cardboarddex:analytics:pokemon_clicks"
REDIS_KEY_SEARCHES = "cardboarddex:analytics:searches"
TRENDING_CACHE_TTL = 180  # 3 minutes

# In-memory fallback if Redis is unavailable with size bounds to prevent memory bloat
_MAX_ANALYTICS_ENTRIES = 2000
_IN_MEMORY_CARD_CLICKS: dict[str, int] = {}
_IN_MEMORY_POKE_CLICKS: dict[str, int] = {}
_IN_MEMORY_SEARCHES: dict[str, int] = {}
_TRENDING_CACHE: dict[str, tuple[datetime, TrendingDashboardResponse]] = {}


def _safe_increment_in_memory(store: dict[str, int], key: str) -> None:
    """Increment count in bounded in-memory store, evicting lowest entry if full."""
    if key not in store and len(store) >= _MAX_ANALYTICS_ENTRIES:
        min_key = min(store, key=store.get)  # type: ignore[arg-type]
        store.pop(min_key, None)
    store[key] = store.get(key, 0) + 1


def invalidate_trending_cache() -> None:
    """Clear memory cache and delete Redis cache keys for trending dashboard using non-blocking SCAN."""
    _TRENDING_CACHE.clear()
    r = get_redis()
    if r is not None:
        try:
            keys = list(r.scan_iter(match="cardboarddex:trending:*", count=100))
            if keys:
                r.delete(*keys)
        except (RedisError, Exception) as exc:
            logger.warning(
                "Failed to invalidate trending Redis cache error=%s: %s",
                type(exc).__name__,
                exc,
            )


def reset_trending_analytics() -> None:
    """Reset all click and search counters to zero and invalidate cached dashboards."""
    _IN_MEMORY_CARD_CLICKS.clear()
    _IN_MEMORY_POKE_CLICKS.clear()
    _IN_MEMORY_SEARCHES.clear()
    _TRENDING_CACHE.clear()
    r = get_redis()
    if r is not None:
        try:
            r.delete(REDIS_KEY_CARD_CLICKS, REDIS_KEY_POKE_CLICKS, REDIS_KEY_SEARCHES)
        except (RedisError, Exception) as exc:
            logger.warning(
                "Failed to reset Redis analytics keys error=%s: %s",
                type(exc).__name__,
                exc,
            )
    invalidate_trending_cache()


def record_action(
    entity_type: Literal["card", "pokemon", "search"],
    entity_id: str,
    action: Literal["click", "search", "view"] = "click",
) -> None:
    """Record a user click, search, or view action for trending analytics with bounded memory."""
    clean_id = entity_id.strip()[:100]
    if not clean_id:
        return

    # In-memory and Redis updates
    r = get_redis()

    if action == "search" or entity_type == "search":
        term = clean_id.lower()
        _safe_increment_in_memory(_IN_MEMORY_SEARCHES, term)
        if r is not None:
            try:
                r.zincrby(REDIS_KEY_SEARCHES, 1, term)
                if r.zcard(REDIS_KEY_SEARCHES) > 2500:
                    r.zremrangebyrank(REDIS_KEY_SEARCHES, 0, -2001)
            except (RedisError, Exception) as exc:
                logger.warning(
                    "Failed to record analytics action in Redis entity_type=%s id=%s error=%s: %s",
                    entity_type,
                    clean_id,
                    type(exc).__name__,
                    exc,
                )
    elif entity_type == "card":
        _safe_increment_in_memory(_IN_MEMORY_CARD_CLICKS, clean_id)
        if r is not None:
            try:
                r.zincrby(REDIS_KEY_CARD_CLICKS, 1, clean_id)
                if r.zcard(REDIS_KEY_CARD_CLICKS) > 2500:
                    r.zremrangebyrank(REDIS_KEY_CARD_CLICKS, 0, -2001)
            except (RedisError, Exception) as exc:
                logger.warning(
                    "Failed to record analytics action in Redis entity_type=%s id=%s error=%s: %s",
                    entity_type,
                    clean_id,
                    type(exc).__name__,
                    exc,
                )
    elif entity_type == "pokemon":
        norm_poke = clean_id.capitalize()
        _safe_increment_in_memory(_IN_MEMORY_POKE_CLICKS, norm_poke)
        if r is not None:
            try:
                r.zincrby(REDIS_KEY_POKE_CLICKS, 1, norm_poke)
                if r.zcard(REDIS_KEY_POKE_CLICKS) > 2500:
                    r.zremrangebyrank(REDIS_KEY_POKE_CLICKS, 0, -2001)
            except (RedisError, Exception) as exc:
                logger.warning(
                    "Failed to record analytics action in Redis entity_type=%s id=%s error=%s: %s",
                    entity_type,
                    clean_id,
                    type(exc).__name__,
                    exc,
                )

    # Invalidate cached dashboard so counts reflect immediately
    invalidate_trending_cache()


def _get_redis_scores(redis_key: str, fallback_dict: dict[str, int]) -> dict[str, int]:
    """Retrieve score mapping from Redis sorted set with in-memory fallback."""
    scores: dict[str, int] = dict(fallback_dict)
    r = get_redis()
    if r is not None:
        try:
            entries = r.zrevrange(redis_key, 0, 500, withscores=True)
            for member, score in entries:
                key = member if isinstance(member, str) else member.decode("utf-8")
                scores[key] = max(scores.get(key, 0), int(score))
        except (RedisError, Exception) as exc:
            logger.warning("Failed to fetch Redis scores key=%s error=%s: %s", redis_key, type(exc).__name__, exc)
    return scores


def calculate_trending_cards(
    db: Session,
    *,
    limit: int = 50,
    q: str | None = None,
) -> list[TrendingCardItem]:
    """Calculate the top trending/most searched or clicked cards."""
    card_clicks = _get_redis_scores(REDIS_KEY_CARD_CLICKS, _IN_MEMORY_CARD_CLICKS)

    # Base query template
    base_stmt = (
        select(
            Card.id,
            Card.name,
            Card.number,
            Card.rarity,
            Set.id.label("set_id"),
            Set.name.label("set_name"),
            func.count(PriceObservation.id).label("obs_cnt"),
            func.avg(PriceObservation.price).label("avg_price"),
            func.max(PriceObservation.price).label("max_price"),
        )
        .join(Set, Card.set_id == Set.id)
        .outerjoin(PriceObservation, PriceObservation.card_id == Card.id)
        .where(Card.name.not_ilike("%code card%"))
        .group_by(Card.id, Card.name, Card.number, Card.rarity, Set.id, Set.name)
    )

    # 1. Top cards by observation count
    obs_stmt = base_stmt.order_by(func.count(PriceObservation.id).desc()).limit(200)
    if q and q.strip():
        clean_q = q.strip().lower()
        obs_stmt = obs_stmt.where(or_(Card.name.ilike(f"%{clean_q}%"), Set.name.ilike(f"%{clean_q}%")))

    rows_map: dict[str, Any] = {r.id: r for r in db.execute(obs_stmt).all()}

    # 2. Ensure all clicked cards are included even if low or 0 price observation count
    clicked_ids = [cid for cid, cnt in card_clicks.items() if cnt > 0 and cid not in rows_map]
    if clicked_ids:
        clicked_stmt = base_stmt.where(Card.id.in_(clicked_ids[:100]))
        if q and q.strip():
            clean_q = q.strip().lower()
            clicked_stmt = clicked_stmt.where(or_(Card.name.ilike(f"%{clean_q}%"), Set.name.ilike(f"%{clean_q}%")))
        for r in db.execute(clicked_stmt).all():
            rows_map[r.id] = r

    rows = list(rows_map.values())
    card_ids = list(rows_map.keys())

    # Fetch provider state payload for market price and 7-day change
    payload_map: dict[str, dict[str, Any]] = {}
    if card_ids:
        state_rows = db.execute(
            select(ProviderCardState.card_id, ProviderCardState.payload)
            .where(ProviderCardState.card_id.in_(card_ids), ProviderCardState.payload.is_not(None))
        ).all()
        for cid, pl in state_rows:
            if pl and isinstance(pl, dict):
                payload_map[cid] = pl

    candidates: list[dict[str, Any]] = []
    for r in rows:
        cid = r.id
        clicks = card_clicks.get(cid, 0)
        obs_cnt = int(r.obs_cnt or 0)
        avg_price = float(r.avg_price or 0)
        pl = payload_map.get(cid, {})

        # Resolve market price
        market_price: float | None = None
        if pl.get("market_price") is not None:
            try:
                market_price = float(pl["market_price"])
            except (ValueError, TypeError):
                market_price = avg_price
        elif avg_price > 0:
            market_price = round(avg_price, 2)

        # Resolve 7-day change
        price_change_7d: float | None = None
        if pl.get("price_change_7d") is not None:
            try:
                price_change_7d = float(pl["price_change_7d"])
            except (ValueError, TypeError):
                price_change_7d = 0.0

        # Algorithmic Trending Score
        price_factor = min(market_price or 0, 500.0) * 0.08
        change_factor = abs(price_change_7d or 0.0) * 1.5
        obs_factor = min(obs_cnt, 150) * 1.5
        click_factor = clicks * 150.0
        trend_score = round(click_factor + obs_factor + price_factor + change_factor, 1)

        # Direction
        if (price_change_7d is not None and price_change_7d > 1.5) or clicks > 0:
            trend_direction: Literal["up", "down", "flat"] = "up"
        elif price_change_7d is not None and price_change_7d < -1.5:
            trend_direction = "down"
        else:
            trend_direction = "flat"

        candidates.append({
            "card_id": cid,
            "name": r.name,
            "set_name": r.set_name,
            "set_id": r.set_id,
            "number": r.number,
            "rarity": r.rarity,
            "image_url": f"/cards/{cid}/image",
            "market_price": market_price,
            "price_change_7d": price_change_7d,
            "clicks_count": clicks,
            "trend_score": trend_score,
            "trend_direction": trend_direction,
        })

    # Sort by trending score descending (prioritizing actively clicked cards)
    candidates.sort(
        key=lambda x: (x["clicks_count"] > 0, x["trend_score"], x["clicks_count"], x["market_price"] or 0),
        reverse=True,
    )

    items: list[TrendingCardItem] = []
    for rank, c in enumerate(candidates[:limit], start=1):
        items.append(
            TrendingCardItem(
                rank=rank,
                card_id=c["card_id"],
                name=c["name"],
                set_name=c["set_name"],
                set_id=c["set_id"],
                number=c["number"],
                rarity=c["rarity"],
                image_url=c["image_url"],
                market_price=c["market_price"],
                price_change_7d=c["price_change_7d"],
                clicks_count=c["clicks_count"],
                trend_score=c["trend_score"],
                trend_direction=c["trend_direction"],
            )
        )
    return items


def calculate_trending_pokemon(
    db: Session,
    *,
    limit: int = 50,
    q: str | None = None,
) -> list[TrendingPokemonItem]:
    """Calculate the most clicked or searched on Pokémon characters."""
    poke_clicks = _get_redis_scores(REDIS_KEY_POKE_CLICKS, _IN_MEMORY_POKE_CLICKS)
    searches = _get_redis_scores(REDIS_KEY_SEARCHES, _IN_MEMORY_SEARCHES)

    active_pokemon_names = list(POKEMON_TOP_50_NAMES)
    for p_name, cnt in poke_clicks.items():
        cap_p = p_name.capitalize()
        if cnt > 0 and cap_p not in active_pokemon_names:
            active_pokemon_names.append(cap_p)
    for s_name, cnt in searches.items():
        cap_s = s_name.capitalize()
        if cnt > 0 and cap_s not in active_pokemon_names:
            active_pokemon_names.append(cap_s)

    name_filter = or_(*[Card.name.ilike(f"%{n}%") for n in active_pokemon_names])
    enrichment_rows = db.execute(
        select(Card.id, Card.name, PriceObservation.price)
        .outerjoin(PriceObservation, PriceObservation.card_id == Card.id)
        .where(name_filter, Card.name.not_ilike("%code card%"))
    ).all()

    cards_per_pokemon: dict[str, set[str]] = {n: set() for n in active_pokemon_names}
    top_cards: dict[str, tuple[str, str, float] | None] = {n: None for n in active_pokemon_names}

    for card_id, card_name, obs_price in enrichment_rows:
        poke = match_to_pokemon(card_name)
        if poke is None or poke not in cards_per_pokemon:
            continue
        cards_per_pokemon[poke].add(card_id)
        if obs_price is not None:
            price_flt = float(obs_price)
            current_top = top_cards[poke]
            if current_top is None or price_flt > current_top[2]:
                top_cards[poke] = (card_id, card_name, price_flt)

    search_filter = (q or "").strip().lower()
    candidates: list[dict[str, Any]] = []

    for poke_name in active_pokemon_names:
        if search_filter and search_filter not in poke_name.lower():
            continue

        dex = POKEMON_DEX_NUMBERS.get(poke_name, 0)
        clicks = poke_clicks.get(poke_name, 0)
        search_cnt = searches.get(poke_name.lower(), 0)
        cards_cnt = len(cards_per_pokemon[poke_name])
        top_card = top_cards[poke_name]
        top_price = top_card[2] if top_card else 0.0

        # Algorithmic Popularity Score
        # Algorithmic Popularity Score: Clicks + Searches + Card Depth + Top Comp Price
        card_factor = min(cards_cnt, 200) * 0.8
        price_factor = min(top_price, 2000.0) * 0.03
        click_factor = clicks * 150.0
        search_factor = search_cnt * 100.0
        trend_score = round(click_factor + search_factor + card_factor + price_factor, 1)

        trend_direction: Literal["up", "down", "flat"] = (
            "up" if (clicks > 0 or search_cnt > 0 or trend_score > 60.0) else "flat"
        )

        sprite_url = (
            f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/"
            f"pokemon/other/official-artwork/{dex}.png"
        )

        candidates.append({
            "pokemon_name": poke_name,
            "dex_number": dex,
            "sprite_url": sprite_url,
            "clicks_count": clicks,
            "searches_count": search_cnt,
            "cards_count": cards_cnt,
            "trend_score": trend_score,
            "trend_direction": trend_direction,
            "top_card_name": top_card[1] if top_card else None,
            "top_card_price": top_card[2] if top_card else None,
            "top_card_id": top_card[0] if top_card else None,
        })

    # Sort by trend score descending (prioritizing actively clicked or searched species)
    candidates.sort(
        key=lambda x: (
            x["clicks_count"] > 0 or x["searches_count"] > 0,
            x["trend_score"],
            x["clicks_count"],
            x["cards_count"],
        ),
        reverse=True,
    )

    items: list[TrendingPokemonItem] = []
    for rank, c in enumerate(candidates[:limit], start=1):
        items.append(
            TrendingPokemonItem(
                rank=rank,
                pokemon_name=c["pokemon_name"],
                dex_number=c["dex_number"],
                sprite_url=c["sprite_url"],
                clicks_count=c["clicks_count"],
                searches_count=c["searches_count"],
                cards_count=c["cards_count"],
                trend_score=c["trend_score"],
                trend_direction=c["trend_direction"],
                top_card_name=c["top_card_name"],
                top_card_price=c["top_card_price"],
                top_card_id=c["top_card_id"],
            )
        )
    return items


def get_trending_dashboard(
    db: Session,
    *,
    timeframe: Literal["24h", "7d", "30d", "all_time", "2026_ytd"] = "7d",
    q: str | None = None,
) -> TrendingDashboardResponse:
    """Calculate all three trending columns in a single unified payload with caching."""
    clean_q = (q or "").strip().lower()
    cache_key = f"{timeframe}:{clean_q}"
    redis_key = f"cardboarddex:trending:{cache_key}"
    now = datetime.now(UTC)

    # 1. Redis Cache
    r = get_redis()
    if r is not None:
        try:
            cached = r.get(redis_key)
            if cached:
                return TrendingDashboardResponse.model_validate_json(cached)
        except (RedisError, Exception) as exc:
            logger.warning("Redis read error for key=%s: %s", redis_key, exc)

    # 2. In-memory Fallback
    if cache_key in _TRENDING_CACHE:
        cached_time, cached_res = _TRENDING_CACHE[cache_key]
        if (now - cached_time).total_seconds() < TRENDING_CACHE_TTL:
            return cached_res

    # 3. Compute Column 1: Trending Cards
    trending_cards = calculate_trending_cards(db, limit=50, q=q)

    # 4. Compute Column 2: Trending Pokémon
    trending_pokemon = calculate_trending_pokemon(db, limit=50, q=q)

    # 5. Compute Column 3: Volume Leaders
    volume_res = calculate_top_pokemon_volume(db, timeframe=timeframe, sort_by="volume_desc", q=q)

    response = TrendingDashboardResponse(
        timeframe=timeframe,
        trending_cards=trending_cards,
        trending_pokemon=trending_pokemon,
        volume_pokemon=volume_res.items,
        total_volume_usd=volume_res.total_volume_usd,
        total_sales_count=volume_res.total_sales_count,
        updated_at=now,
    )

    # Store in Redis & in-memory cache
    if r is not None:
        try:
            r.setex(redis_key, TRENDING_CACHE_TTL, response.model_dump_json())
        except (RedisError, Exception) as exc:
            logger.warning("Redis write error for key=%s: %s", redis_key, exc)

    _TRENDING_CACHE[cache_key] = (now, response)
    return response
