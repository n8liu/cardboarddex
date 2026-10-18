from app.services.price_sources import market_observation, catalog_price_join
from app.common.response_cache import cached_read, response_cache
from app.services.image_delivery import card_image_url
from app.common.cache import TTLCache
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, case, func, literal, not_, or_, select
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
    response_cache.clear()
    _SEARCH_LOCAL_CACHE.clear()
    _SETS_LOCAL_CACHE.clear()


@router.get("/search", response_model=list[CardSummary])
@cached_read("search_cards", fresh=60, maximum=300)
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
    clean_q = q.strip()
    selected, price_rows, price_join = catalog_price_join(dialect=db.get_bind().dialect.name, broad=not clean_q and not set_id and (
        sort_by in {"price_asc", "price_desc"} or min_price is not None or max_price is not None))
    latest_price = selected.price
    latest_currency = literal("USD").label("market_currency")
    latest_synced = selected.provider_updated_at

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
    statement = statement.outerjoin(price_rows, price_join)

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

    from app.services.ppt_prices import label_market_sources
    label_market_sources(db, results)
    return results


@router.get("/pokemon/{name}", response_model=PokemonCardsResponse)
@cached_read("get_pokemon_cards", fresh=60, maximum=300)
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
@cached_read("list_card_sets", fresh=3600, maximum=7200)
def list_card_sets(
    response: Response,
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(
        default="pokemon",
        description="Filter sets by game language: 'pokemon' (English), 'pokemon-japan' (Japanese), or 'all'",
    ),
    db: Session = Depends(get_db),
) -> list[CardSetOption]:
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
            image_url=card_image_url(set_images[card_set.id]) if card_set.id in set_images else None,
        )
        for card_set in card_sets
    ]

    return results


@router.get("/sets/{set_id}/stats", response_model=SetStatsResponse)
@cached_read("get_set_stats", fresh=60, maximum=300)
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
    return _cards_router.get_set_statistics(
        db,
        use_cache=False,
        set_id=set_id,
        q=q,
        hide_sealed=hide_sealed,
        sealed_only=sealed_only,
        game=game,
        min_price=min_price,
        max_price=max_price,
    )
