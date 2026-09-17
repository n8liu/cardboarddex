from app.common.cache import TTLCache
import json
import logging
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from redis.exceptions import RedisError
from sqlalchemy import case, func, literal, not_, or_, select
from sqlalchemy.orm import Session

from app.common.formatters import escape_like as _escape_like
from app.routers import cards as _cards_router

def _get_redis():
    return _cards_router._get_redis()
from app.database import get_db
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.schemas.cards import (
    CardSetOption,
    CardSummary,
    PokemonCardsResponse,
    SetStatsResponse,
)
from app.services.catalog_service import (
    build_card_summary as _summary,
    get_pokemon_search_terms as _get_pokemon_search_terms,
    get_set_statistics,
    query_pokemon_cards,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["Catalog"])

_SEARCH_CACHE_TTL = 300  # 5 minutes in Redis
_SEARCH_LOCAL_CACHE = TTLCache(max_entries=64, ttl=60)
_SEARCH_LOCAL_CACHE_TTL = 60  # 1 minute in-process fallback
_MAX_SEARCH_LOCAL_ENTRIES = 200

_SETS_CACHE_TTL = 3600  # 1 hour in Redis
_SETS_LOCAL_CACHE = TTLCache(max_entries=64, ttl=300)
_SETS_LOCAL_CACHE_TTL = 300  # 5 minutes in-process fallback


def _evict_oldest_cache_entries(cache: dict[str, tuple[float, Any]], count: int = 50) -> None:
    """Evict oldest entries when an in-process cache exceeds capacity."""
    oldest_keys = sorted(cache.keys(), key=lambda k: cache[k][0])[:count]
    for k in oldest_keys:
        cache.pop(k, None)


def clear_catalog_caches() -> None:
    """Reset in-process catalog search and sets caches (used by tests)."""
    _SEARCH_LOCAL_CACHE.clear()
    _SETS_LOCAL_CACHE.clear()


@router.get("/search", response_model=list[CardSummary])
def search_cards(
    response: Response,
    q: str = Query(default="", max_length=120),
    sort_by: Literal["price_asc", "price_desc", "name", "number_asc", "number_desc", "set"] = Query(
        default="price_desc"
    ),
    limit: int = Query(default=60, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    set_id: str | None = Query(default=None),
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(
        default="pokemon",
        description="Filter by game language: 'pokemon' (English), 'pokemon-japan' (Japanese), or 'all'",
    ),
    hide_sealed: bool = Query(default=True),
    sealed_only: bool = Query(default=False),
    min_price: float | None = Query(default=None, ge=0.0),
    max_price: float | None = Query(default=None, ge=0.0),
    db: Session = Depends(get_db),
) -> list[CardSummary]:
    response.headers["Cache-Control"] = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"
    clean_q = q.strip()
    cache_key = f"{game}:{sort_by}:{limit}:{offset}:{hide_sealed}:{sealed_only}:{min_price}:{max_price}:{set_id}:{clean_q}"
    redis_key = f"cardboarddex:catalog:search:{cache_key}"

    now = time.time()
    # 1. Fast in-process cache (<0.1ms)
    local_hit = _SEARCH_LOCAL_CACHE.get(cache_key)
    if local_hit and (now - local_hit[0]) < _SEARCH_LOCAL_CACHE_TTL:
        return [CardSummary.model_validate(item) for item in local_hit[1]]

    # 2. Shared Redis cache across workers (<5ms)
    r = _get_redis()
    if r is not None:
        try:
            cached_raw = r.get(redis_key)
            if cached_raw:
                data = json.loads(cached_raw)
                _SEARCH_LOCAL_CACHE[cache_key] = (now, data)
                if len(_SEARCH_LOCAL_CACHE) > _MAX_SEARCH_LOCAL_ENTRIES:
                    _evict_oldest_cache_entries(_SEARCH_LOCAL_CACHE, 50)
                return [CardSummary.model_validate(item) for item in data]
        except (RedisError, Exception) as exc:
            logger.warning("Redis search cache read failed error=%s: %s", type(exc).__name__, exc)

    # 3. Database query on cache miss
    # Aligned with ix_price_observations_search_lookup: (card_id, provider, grading_company, provider_updated_at, observed_at)
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
        )
        .limit(1)
        .correlate(Card)
        .scalar_subquery()
    )

    # Query Optimization: TCG API observations are uniformly in USD; derive directly without duplicate 60k-row correlated subquery
    latest_currency = literal("USD").label("market_currency")

    latest_synced = (
        select(PriceObservation.provider_updated_at)
        .where(
            PriceObservation.card_id == Card.id,
            PriceObservation.provider == "tcgapi",
            PriceObservation.grading_company.is_(None),
        )
        .order_by(
            PriceObservation.provider_updated_at.desc().nullslast(),
            PriceObservation.observed_at.desc(),
        )
        .limit(1)
        .correlate(Card)
        .scalar_subquery()
    )

    statement = (
        select(
            Card,
            Set,
            latest_price.label("market_price"),
            latest_currency,
            latest_synced.label("latest_synced"),
        )
        .join(Set, Card.set_id == Set.id)
        .where(Card.name.not_ilike("%code card%"))
    )

    # Language/series filtering
    if game == "pokemon":
        statement = statement.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))
    elif game == "pokemon-japan":
        statement = statement.where(Set.series == "Pokemon Japan")

    if clean_q:
        pattern = f"%{_escape_like(clean_q)}%"
        statement = statement.where(
            or_(Card.name.ilike(pattern, escape="\\"), Set.name.ilike(pattern, escape="\\"))
        )
    if set_id:
        statement = statement.where(Card.set_id == set_id)

    is_none_or_sealed = or_(
        Card.rarity.is_(None),
        Card.rarity == "",
        Card.rarity == "None",
        Card.rarity.ilike("none"),
    )
    if sealed_only:
        statement = statement.where(is_none_or_sealed)
    elif hide_sealed:
        statement = statement.where(not_(is_none_or_sealed))

    # Price range filtering
    if min_price is not None and min_price > 0:
        statement = statement.where(latest_price >= min_price)
    if max_price is not None:
        statement = statement.where(latest_price <= max_price)

    if sort_by == "price_asc":
        order = (latest_price.asc().nullslast(), Card.name.asc(), Card.id.asc())
    elif sort_by == "price_desc":
        order = (latest_price.desc().nullslast(), Card.name.asc(), Card.id.asc())
    elif sort_by == "number_asc":
        order = (Card.number.asc(), Card.name.asc(), Card.id.asc())
    elif sort_by == "number_desc":
        order = (Card.number.desc(), Card.name.asc(), Card.id.asc())
    elif sort_by == "set":
        order = (Set.name.asc(), Card.number.asc(), Card.name.asc(), Card.id.asc())
    else:
        order = (
            Card.name.asc(),
            latest_price.desc().nullslast(),
            Card.id.asc(),
        )

    rows = db.execute(statement.order_by(*order).offset(offset).limit(limit)).all()
    results = [
        _summary(card, card_set, market_price, market_currency, latest_synced)
        for card, card_set, market_price, market_currency, latest_synced in rows
    ]

    # Save to local cache & Redis
    serialized = [item.model_dump(mode="json") for item in results]
    _SEARCH_LOCAL_CACHE[cache_key] = (now, serialized)
    if len(_SEARCH_LOCAL_CACHE) > _MAX_SEARCH_LOCAL_ENTRIES:
        _evict_oldest_cache_entries(_SEARCH_LOCAL_CACHE, 50)
    if r is not None:
        try:
            r.setex(redis_key, _SEARCH_CACHE_TTL, json.dumps(serialized))
        except (RedisError, Exception) as exc:
            logger.warning("Redis search cache write failed error=%s: %s", type(exc).__name__, exc)

    return results


@router.get("/pokemon/{name}", response_model=PokemonCardsResponse)
def get_pokemon_cards(
    name: str,
    response: Response,
    sort_by: Literal["price_desc", "price_asc", "number_asc", "number_desc", "name", "set"] = Query(
        default="price_desc"
    ),
    set_id: str | None = Query(default=None),
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(
        default="pokemon",
        description="Filter by game language: 'pokemon' (English), 'pokemon-japan' (Japanese), or 'all'",
    ),
    hide_sealed: bool = Query(default=True),
    limit: int = Query(default=60, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PokemonCardsResponse:
    """Retrieve all trading cards matching a canonical Pokémon species name across sets."""
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    return query_pokemon_cards(
        db,
        name=name,
        sort_by=sort_by,
        set_id=set_id,
        game=game,
        limit=limit,
        offset=offset,
    )


@router.get("/sets", response_model=list[CardSetOption])
def list_card_sets(
    response: Response,
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(
        default="pokemon",
        description="Filter sets by game language: 'pokemon' (English), 'pokemon-japan' (Japanese), or 'all'",
    ),
    db: Session = Depends(get_db),
) -> list[CardSetOption]:
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=86400, stale-while-revalidate=3600"
    cache_key = game
    redis_key = f"cardboarddex:catalog:sets:{cache_key}"

    now = time.time()
    # 1. Fast in-process cache (<0.1ms)
    local_hit = _SETS_LOCAL_CACHE.get(cache_key)
    if local_hit and (now - local_hit[0]) < _SETS_LOCAL_CACHE_TTL:
        return [CardSetOption.model_validate(item) for item in local_hit[1]]

    # 2. Shared Redis cache across workers (<5ms)
    r = _get_redis()
    if r is not None:
        try:
            cached_raw = r.get(redis_key)
            if cached_raw:
                data = json.loads(cached_raw)
                _SETS_LOCAL_CACHE[cache_key] = (now, data)
                return [CardSetOption.model_validate(item) for item in data]
        except (RedisError, Exception) as exc:
            logger.warning("Redis sets cache read failed error=%s: %s", type(exc).__name__, exc)

    stmt = select(Set).where(Set.id.in_(select(Card.set_id).distinct()))
    if game == "pokemon":
        stmt = stmt.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))
    elif game == "pokemon-japan":
        stmt = stmt.where(Set.series == "Pokemon Japan")

    card_sets = db.scalars(
        stmt.order_by(Set.release_date.desc().nullslast(), Set.name.asc())
    ).all()

    # Resolve representative set images (preferring booster products, else first card)
    set_ids = [s.id for s in card_sets]
    set_images: dict[str, str] = {}
    try:
        base_img_rows = db.execute(
            select(Card.set_id, func.min(Card.id))
            .where(Card.set_id.in_(set_ids), Card.image_url.is_not(None))
            .group_by(Card.set_id)
        ).all()
        set_images = {s_id: c_id for s_id, c_id in base_img_rows}

        booster_rows = db.execute(
            select(Card.set_id, func.min(Card.id))
            .where(Card.set_id.in_(set_ids), Card.image_url.is_not(None), Card.name.ilike("%booster%"))
            .group_by(Card.set_id)
        ).all()
        for s_id, c_id in booster_rows:
            set_images[s_id] = c_id
    except Exception as exc:
        logger.warning("Failed to resolve set images error=%s: %s", type(exc).__name__, exc)

    results = [
        CardSetOption(
            id=card_set.id,
            name=card_set.name,
            series=card_set.series,
            release_date=card_set.release_date,
            image_url=f"/cards/{set_images[card_set.id]}/image" if card_set.id in set_images else None,
        )
        for card_set in card_sets
    ]

    # Save to local cache & Redis
    serialized = [item.model_dump(mode="json") for item in results]
    _SETS_LOCAL_CACHE[cache_key] = (now, serialized)
    if r is not None:
        try:
            r.setex(redis_key, _SETS_CACHE_TTL, json.dumps(serialized))
        except (RedisError, Exception) as exc:
            logger.warning("Redis sets cache write failed error=%s: %s", type(exc).__name__, exc)

    return results


@router.get("/sets/{set_id}/stats", response_model=SetStatsResponse)
def get_set_stats(
    set_id: str,
    response: Response,
    q: str = Query(default="", max_length=120),
    hide_sealed: bool = Query(default=True),
    sealed_only: bool = Query(default=False),
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(default="all"),
    min_price: float | None = Query(default=None, ge=0.0),
    max_price: float | None = Query(default=None, ge=0.0),
    db: Session = Depends(get_db),
) -> SetStatsResponse:
    """Retrieve aggregate market price statistics for a card set."""
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    return _cards_router.get_set_statistics(
        db,
        set_id=set_id,
        q=q,
        hide_sealed=hide_sealed,
        sealed_only=sealed_only,
        game=game,
        min_price=min_price,
        max_price=max_price,
    )
