import json
import logging
import math
import time
from functools import lru_cache
from datetime import UTC, datetime, timedelta
import re
from urllib.parse import urlparse
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import case, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.common.formatters import (
    escape_like as _escape_like,
    extract_float as _extract_float,
    parse_iso_datetime as _parse_iso_datetime,
)
from app.services.catalog_service import (
    build_card_summary as _summary,
    calculate_top_pokemon_volume,
    get_pokemon_search_terms as _get_pokemon_search_terms,
    get_set_statistics,
    query_pokemon_cards,
)
from app.services.grading_service import calculate_grading_profit
from app.services.sealed_service import (
    calculate_sealed_signals,
    classify_sealed_product as _classify_sealed_product,
)
from app.config import get_settings
from app.database import get_db
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.tcgapi import TCGAPIClient
from app.schemas.cards import (
    CardDetail,
    CardPricingResponse,
    CardSetOption,
    CardSummary,
    GradingProfitItem,
    GradingProfitResponse,
    MarketMoverItem,
    MarketMoversResponse,
    PriceObservationItem,
    ProviderPricingState,
    SealedSignalItem,
    SealedSignalsResponse,
    SetStatsResponse,
    PokemonVolumeItem,
    PokemonVolumeResponse,
    TrendingCardItem,
    TrendingPokemonItem,
    TrendingDashboardResponse,
    TrackActionRequest,
    LiveUpdateItem,
    LiveUpdatesResponse,
    PokemonCardsResponse,
    PokemonSetCount,
)
from app.services.catalog_service import match_to_pokemon
from app.services.trending_service import (
    get_trending_dashboard,
    record_action,
    reset_trending_analytics,
)

from app.common.rate_limiter import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["Cards"])

ALLOWED_MARKETPLACE_DOMAINS = {"ebay.com", "tcgplayer.com"}
RE_SAFE_CARD_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")
_S3_CLIENT = None


def _get_s3_client(region_name: str) -> Any:
    global _S3_CLIENT
    if _S3_CLIENT is None:
        try:
            import boto3
            _S3_CLIENT = boto3.client("s3", region_name=region_name)
        except Exception as exc:
            logger.warning("Failed initializing boto3 S3 client error=%s: %s", type(exc).__name__, exc)
            return None
    return _S3_CLIENT


ADMIN_TOKEN_HEADER = "x-admin-token"


def verify_admin_token(x_admin_token: str | None = Header(default=None, alias=ADMIN_TOKEN_HEADER)) -> None:
    settings = get_settings()
    configured_token = (settings.admin_api_key or "").strip()
    if not configured_token:
        logger.warning("Admin action attempted but ADMIN_API_KEY is not configured on server")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin functionality is not enabled",
        )
    if not x_admin_token or x_admin_token != configured_token:
        logger.warning("Unauthorized admin access attempt with token present=%s", bool(x_admin_token))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing admin token",
        )


@lru_cache
def get_tcgapi_client() -> TCGAPIClient:
    # Public web endpoints (market-movers, card images) must not be
    # throttled or blocked by background Celery worker daily scraping limits.
    return TCGAPIClient(acquire_request=lambda: None)


# ---------------------------------------------------------------------------
# Shared Redis client from app.common.redis (market movers, live-updates KPIs,
# broken image IDs). Initialised lazily; degrades gracefully to no-op when
# Redis is unavailable (e.g. unit tests that don’t spin up Redis).
# ---------------------------------------------------------------------------
from app.common.redis import get_redis as _get_redis


def _build_mover_item(
    raw: dict[str, Any],
    direction: str,
    period: str,
    card_map: dict[str, tuple[Card, Set]],
) -> MarketMoverItem | None:
    card_id = str(raw.get("card_id") or raw.get("id") or "")
    if not card_id:
        return None
    name = str(raw.get("name") or raw.get("card_name") or "")
    set_name = str(raw.get("set_name") or "")
    printing = raw.get("printing")
    price_val = raw.get("market_price") if raw.get("market_price") is not None else raw.get("price")
    if price_val is None:
        return None
    try:
        market_price = float(price_val)
    except (ValueError, TypeError):
        return None
    pct_val = (
        raw.get("price_change")
        if raw.get("price_change") is not None
        else raw.get(f"price_change_{period}")
        if raw.get(f"price_change_{period}") is not None
        else raw.get("price_change_percentage")
    )
    try:
        pct = float(pct_val) if pct_val is not None else 0.0
    except (ValueError, TypeError):
        pct = 0.0

    # Calculate approximate dollar change from percentage change
    if pct != 0.0 and (1.0 + (pct / 100.0)) > 0:
        old_price = market_price / (1.0 + (pct / 100.0))
        price_change_amount = round(market_price - old_price, 2)
    else:
        price_change_amount = None

    last_updated_at = _parse_iso_datetime(raw.get("last_updated_at"))

    local_entry = card_map.get(card_id)
    if local_entry:
        card, card_set = local_entry
        return MarketMoverItem(
            card_id=card.id,
            name=card.name,
            set_id=card.set_id,
            set_name=card_set.name,
            number=card.number,
            rarity=card.rarity,
            image_url=f"/cards/{card.id}/image",
            printing=printing,
            market_price=market_price,
            price_change_percentage=round(pct, 2),
            price_change_amount=price_change_amount,
            period=period,
            direction=direction,
            last_updated_at=last_updated_at or card.updated_at,
        )
    else:
        return MarketMoverItem(
            card_id=card_id,
            name=name,
            set_id=None,
            set_name=set_name,
            number=None,
            rarity=None,
            image_url=f"/cards/{card_id}/image",
            printing=printing,
            market_price=market_price,
            price_change_percentage=round(pct, 2),
            price_change_amount=price_change_amount,
            period=period,
            direction=direction,
            last_updated_at=last_updated_at,
        )


# Redis-backed market movers cache (TTL matches the 15-minute alternating cycle).
# _MOVERS_LOCAL_FALLBACK acts as an in-process backup when Redis is unreachable
# so that a Redis blip doesn’t immediately trigger redundant upstream API calls.
_MOVERS_LOCAL_FALLBACK: dict[str, tuple[float, list[dict[str, Any]], list[dict[str, Any]]]] = {}
_MOVERS_CACHE_TTL = 900  # seconds


def _compute_db_market_movers(
    db: Session,
    period: str = "24h",
    game: str = "pokemon",
    limit: int = 50,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute market movers from locally cached provider card states or price observations when upstream API is unavailable."""
    try:
        candidates: list[dict[str, Any]] = []

        # 1. First pass: check ProviderCardState payload for explicit price changes
        stmt = (
            select(ProviderCardState.card_id, ProviderCardState.payload, Card.name, Set.name.label("set_name"))
            .join(Card, ProviderCardState.card_id == Card.id)
            .join(Set, Card.set_id == Set.id)
            .where(ProviderCardState.payload.is_not(None))
        )
        if game == "pokemon-japan":
            stmt = stmt.where(Set.series == "Pokemon Japan")
        elif game == "pokemon":
            stmt = stmt.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))

        rows = db.execute(stmt.limit(500)).all()
        for r in rows:
            pl = r.payload if isinstance(r.payload, dict) else {}
            price_val = pl.get("market_price") if pl.get("market_price") is not None else pl.get("price")
            if price_val is None:
                continue
            try:
                price = float(price_val)
            except (ValueError, TypeError):
                continue
            if price <= 0:
                continue

            pct_val = (
                pl.get(f"price_change_{period}")
                if pl.get(f"price_change_{period}") is not None
                else pl.get("price_change")
                if pl.get("price_change") is not None
                else pl.get("price_change_percentage")
                if pl.get("price_change_percentage") is not None
                else pl.get("price_change_7d")
            )
            try:
                pct = float(pct_val) if pct_val is not None else 0.0
            except (ValueError, TypeError):
                pct = 0.0

            candidates.append({
                "card_id": r.card_id,
                "name": r.name,
                "set_name": r.set_name,
                "market_price": price,
                "price_change": pct,
                "last_updated_at": pl.get("last_updated_at") or pl.get("updated_at"),
            })

        gainers = sorted([c for c in candidates if c["price_change"] > 0], key=lambda x: x["price_change"], reverse=True)[:limit]
        losers = sorted([c for c in candidates if c["price_change"] < 0], key=lambda x: x["price_change"])[:limit]

        # 2. Second pass: if either gainers or losers are missing/empty, calculate real deltas from PriceObservation
        if not gainers or not losers:
            subq = (
                select(
                    PriceObservation.card_id,
                    PriceObservation.price,
                    PriceObservation.observed_at,
                    func.row_number().over(
                        partition_by=PriceObservation.card_id,
                        order_by=PriceObservation.observed_at.desc(),
                    ).label("rn"),
                )
                .where(PriceObservation.price > 0)
                .subquery()
            )
            p1 = aliased(subq, name="p1")
            p2 = aliased(subq, name="p2")
            delta_stmt = (
                select(
                    Card.id,
                    Card.name,
                    Set.name.label("set_name"),
                    p1.c.price.label("latest_price"),
                    p1.c.observed_at,
                    ((p1.c.price - p2.c.price) / p2.c.price * 100.0).label("pct_change"),
                )
                .join(Card, Card.id == p1.c.card_id)
                .join(Set, Card.set_id == Set.id)
                .join(p2, (p2.c.card_id == p1.c.card_id) & (p2.c.rn == 2))
                .where(p1.c.rn == 1)
            )
            if game == "pokemon-japan":
                delta_stmt = delta_stmt.where(Set.series == "Pokemon Japan")
            elif game == "pokemon":
                delta_stmt = delta_stmt.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))

            obs_rows = db.execute(delta_stmt.limit(500)).all()
            obs_gainers: list[dict[str, Any]] = []
            obs_losers: list[dict[str, Any]] = []
            for obr in obs_rows:
                try:
                    pct = round(float(obr.pct_change), 2)
                    price = float(obr.latest_price)
                except (ValueError, TypeError):
                    continue
                item = {
                    "card_id": obr.id,
                    "name": obr.name,
                    "set_name": obr.set_name,
                    "market_price": price,
                    "price_change": pct,
                    "last_updated_at": obr.observed_at.isoformat() if obr.observed_at else None,
                }
                if pct > 0:
                    obs_gainers.append(item)
                elif pct < 0:
                    obs_losers.append(item)

            if not gainers and obs_gainers:
                gainers = sorted(obs_gainers, key=lambda x: x["price_change"], reverse=True)[:limit]
            if not losers and obs_losers:
                losers = sorted(obs_losers, key=lambda x: x["price_change"])[:limit]

        # 3. Third pass: If still empty (e.g. database only has single static observations),
        # query available priced cards and ensure neither gainers nor losers is empty
        if not gainers or not losers:
            if not candidates:
                subq_single = (
                    select(
                        PriceObservation.card_id,
                        PriceObservation.price,
                        PriceObservation.observed_at,
                        func.row_number().over(
                            partition_by=PriceObservation.card_id,
                            order_by=PriceObservation.observed_at.desc(),
                        ).label("rn"),
                    )
                    .where(PriceObservation.price > 0)
                    .subquery()
                )
                card_stmt = (
                    select(Card.id, Card.name, Set.name.label("set_name"), subq_single.c.price, subq_single.c.observed_at)
                    .join(Set, Card.set_id == Set.id)
                    .join(subq_single, (Card.id == subq_single.c.card_id) & (subq_single.c.rn == 1))
                )
                if game == "pokemon-japan":
                    card_stmt = card_stmt.where(Set.series == "Pokemon Japan")
                elif game == "pokemon":
                    card_stmt = card_stmt.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))
                card_rows = db.execute(card_stmt.limit(limit * 2)).all()
                for cr in card_rows:
                    if cr.price:
                        candidates.append({
                            "card_id": cr.id,
                            "name": cr.name,
                            "set_name": cr.set_name,
                            "market_price": float(cr.price),
                            "price_change": 0.0,
                            "last_updated_at": cr.observed_at.isoformat() if cr.observed_at else None,
                        })

            if not gainers and candidates:
                half = max(1, len(candidates) // 2)
                gainers = candidates[:half]
            if not losers and candidates:
                half = max(1, len(candidates) // 2)
                losers_source = candidates[half:] if len(candidates) > half else candidates
                losers = [
                    {**c, "price_change": c.get("price_change", 0.0)}
                    for c in losers_source[:limit]
                ]

        return gainers, losers
    except Exception as exc:
        logger.error("Failed to compute database market movers error=%s: %s", type(exc).__name__, exc)
        return [], []


@router.get("/market-movers", response_model=MarketMoversResponse)
def get_market_movers(
    response: Response,
    direction: Literal["up", "down", "all"] = Query(default="all"),
    period: Literal["24h", "7d", "30d"] = Query(default="24h"),
    game: Literal["pokemon", "pokemon-japan"] = Query(default="pokemon"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    client: TCGAPIClient = Depends(get_tcgapi_client),
) -> MarketMoversResponse:
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    now = time.time()
    redis_cache_key = f"cardboarddex:movers:{game}:{period}"

    # 1. Try shared Redis cache first (survives worker restarts and multi-process deployments)
    gainers_raw: list[dict[str, Any]] = []
    losers_raw: list[dict[str, Any]] = []
    _served_from_cache = False
    _mover_redis = _get_redis()
    if _mover_redis is not None:
        try:
            _cached_raw = _mover_redis.get(redis_cache_key)
            if _cached_raw:
                _cached_payload = json.loads(_cached_raw)
                gainers_raw = _cached_payload.get("gainers") or []
                losers_raw = _cached_payload.get("losers") or []
                _served_from_cache = True
                logger.debug("Serving market movers from Redis cache key=%s", redis_cache_key)
        except (RedisError, json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "Redis market movers cache read failed key=%s error=%s: %s; fetching live",
                redis_cache_key,
                type(exc).__name__,
                exc,
            )

    # 2. In-process fallback when Redis is unavailable
    if not _served_from_cache:
        _local = _MOVERS_LOCAL_FALLBACK.get(redis_cache_key)
        if _local and (now - _local[0]) < _MOVERS_CACHE_TTL:
            _, gainers_raw, losers_raw = _local
            _served_from_cache = True

    # 3. Fetch live from TCG API on full cache miss
    if not _served_from_cache:
        gainers_raw = []
        losers_raw = []
        try:
            up_payload = client.get_top_movers(game=game, direction="up", period=period, limit=50)
            gainers_raw = up_payload.get("data") or []
        except Exception as exc:
            logger.error(
                "Failed fetching top gainers game=%s period=%s error=%s: %s",
                game,
                period,
                type(exc).__name__,
                exc,
            )

        try:
            down_payload = client.get_top_movers(game=game, direction="down", period=period, limit=50)
            losers_raw = down_payload.get("data") or []
        except Exception as exc:
            logger.error(
                "Failed fetching top losers game=%s period=%s error=%s: %s",
                game,
                period,
                type(exc).__name__,
                exc,
            )

        # 4. Fallback from database if either gainers or losers are missing from upstream
        if not gainers_raw or not losers_raw:
            logger.info(
                "Upstream missing movers (gainers=%d, losers=%d), computing DB fallback for game=%s period=%s",
                len(gainers_raw),
                len(losers_raw),
                game,
                period,
            )
            db_gainers, db_losers = _compute_db_market_movers(db, period=period, game=game, limit=50)
            if not gainers_raw:
                gainers_raw = db_gainers
            if not losers_raw:
                losers_raw = db_losers

        if gainers_raw or losers_raw:
            # Write to Redis (primary, shared across all workers)
            if _mover_redis is not None:
                try:
                    _mover_redis.setex(
                        redis_cache_key,
                        _MOVERS_CACHE_TTL,
                        json.dumps({"gainers": gainers_raw, "losers": losers_raw}),
                    )
                except (RedisError, Exception) as exc:
                    logger.warning(
                        "Redis market movers cache write failed key=%s error=%s: %s",
                        redis_cache_key,
                        type(exc).__name__,
                        exc,
                    )
            # Always mirror to in-process fallback so Redis blips don’t immediately hit TCG API
            _MOVERS_LOCAL_FALLBACK[redis_cache_key] = (now, gainers_raw, losers_raw)
        elif _MOVERS_LOCAL_FALLBACK.get(redis_cache_key):
            # Stale-while-revalidate: serve previously cached data on provider error
            logger.warning(
                "Serving stale market movers (provider error) cache_key=%s",
                redis_cache_key,
            )
            _, gainers_raw, losers_raw = _MOVERS_LOCAL_FALLBACK[redis_cache_key]

    # Collect card IDs to fetch local metadata in one batch query
    all_card_ids = {
        str(item.get("card_id") or item.get("id"))
        for item in (gainers_raw + losers_raw)
        if (item.get("card_id") or item.get("id"))
    }
    card_map: dict[str, tuple[Card, Set]] = {}
    if all_card_ids:
        rows = db.execute(
            select(Card, Set).join(Set, Card.set_id == Set.id).where(Card.id.in_(all_card_ids))
        ).all()
        for card, card_set in rows:
            card_map[card.id] = (card, card_set)

    all_gainers = [
        item for item in (_build_mover_item(raw, "up", period, card_map) for raw in gainers_raw)
        if item is not None
    ]
    all_losers = [
        item for item in (_build_mover_item(raw, "down", period, card_map) for raw in losers_raw)
        if item is not None
    ]

    total_gainers = len(all_gainers)
    total_losers = len(all_losers)

    if direction == "up":
        total_items = total_gainers
    elif direction == "down":
        total_items = total_losers
    else:
        total_items = max(total_gainers, total_losers)

    total_pages = max(1, math.ceil(total_items / per_page))
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    paged_gainers = all_gainers[start_idx:end_idx] if direction in ("up", "all") else []
    paged_losers = all_losers[start_idx:end_idx] if direction in ("down", "all") else []

    return MarketMoversResponse(
        period=period,
        direction=direction,
        page=page,
        per_page=per_page,
        total_gainers=total_gainers,
        total_losers=total_losers,
        total_pages=total_pages,
        gainers=paged_gainers,
        losers=paged_losers,
        updated_at=datetime.now(UTC),
    )


@router.get("/search", response_model=list[CardSummary])
def search_cards(
    response: Response,
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=24, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
    set_id: str | None = Query(default=None, max_length=64),
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(default="all"),
    sort_by: Literal["price_desc", "price_asc", "number_asc", "number_desc", "name", "set"] | None = Query(
        default="price_desc"
    ),
    hide_sealed: bool = Query(default=True),
    sealed_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[CardSummary]:
    response.headers["Cache-Control"] = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"
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
    statement = (
        select(Card, Set, latest_price, latest_currency, latest_synced)
        .join(Set, Card.set_id == Set.id)
        .where(
            Card.name.not_ilike("%code card%"),
            or_(Card.rarity.is_(None), Card.rarity.not_ilike("%code card%")),
        )
    )
    if game == "pokemon":
        statement = statement.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))
    elif game == "pokemon-japan":
        statement = statement.where(Set.series == "Pokemon Japan")

    query = q.strip()
    if query:
        pattern = f"%{_escape_like(query)}%"
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

    rows = db.execute(statement.order_by(*order).offset(offset).limit(limit)).all()
    return [
        _summary(card, card_set, market_price, market_currency, latest_synced)
        for card, card_set, market_price, market_currency, latest_synced in rows
    ]


@router.get("/pokemon/{name}", response_model=PokemonCardsResponse)
def get_pokemon_cards(
    name: str,
    response: Response,
    set_id: str | None = Query(default=None, max_length=64),
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(default="all"),
    sort_by: Literal["price_desc", "price_asc", "number_asc", "number_desc", "name", "set"] = Query(
        default="price_desc"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    ref: str | None = Query(default=None, description="Navigation referrer tag"),
    db: Session = Depends(get_db),
) -> PokemonCardsResponse:
    """Retrieve all trading cards for a specific Pokémon character."""
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    if ref != "trending":
        record_action("pokemon", name, "view")
    return query_pokemon_cards(
        db,
        name,
        set_id=set_id,
        game=game,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


@router.get("/sets", response_model=list[CardSetOption])
def list_card_sets(
    response: Response,
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(default="all"),
    db: Session = Depends(get_db),
) -> list[CardSetOption]:
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=86400, stale-while-revalidate=3600"
    stmt = select(Set).where(Set.id.in_(select(Card.set_id).distinct()))
    if game == "pokemon":
        stmt = stmt.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))
    elif game == "pokemon-japan":
        stmt = stmt.where(Set.series == "Pokemon Japan")

    card_sets = list(
        db.scalars(
            stmt.order_by(Set.release_date.desc().nullslast(), Set.name.asc(), Set.id.asc())
        )
    )

    # Resolve representative set images (preferring booster products, else first card)
    set_images: dict[str, str] = {}
    try:
        base_img_rows = db.execute(
            select(Card.set_id, func.min(Card.id))
            .where(Card.image_url.is_not(None))
            .group_by(Card.set_id)
        ).all()
        set_images = {s_id: c_id for s_id, c_id in base_img_rows}

        booster_rows = db.execute(
            select(Card.set_id, func.min(Card.id))
            .where(Card.image_url.is_not(None), Card.name.ilike("%booster%"))
            .group_by(Card.set_id)
        ).all()
        for s_id, c_id in booster_rows:
            set_images[s_id] = c_id
    except Exception as exc:
        logger.warning("Failed to resolve set images error=%s: %s", type(exc).__name__, exc)

    return [
        CardSetOption(
            id=card_set.id,
            name=card_set.name,
            series=card_set.series,
            release_date=card_set.release_date,
            image_url=f"/cards/{set_images[card_set.id]}/image" if card_set.id in set_images else None,
        )
        for card_set in card_sets
    ]


@router.get("/sets/{set_id}/stats", response_model=SetStatsResponse)
def get_set_stats(
    set_id: str,
    response: Response,
    q: str = Query(default="", max_length=120),
    hide_sealed: bool = Query(default=True),
    sealed_only: bool = Query(default=False),
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(default="all"),
    db: Session = Depends(get_db),
) -> SetStatsResponse:
    """Retrieve aggregate market price statistics for a card set."""
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    return get_set_statistics(
        db,
        set_id=set_id,
        q=q,
        hide_sealed=hide_sealed,
        sealed_only=sealed_only,
        game=game,
    )


@router.get("/grading-profit", response_model=GradingProfitResponse)
def get_grading_profit(
    response: Response,
    grading_fee: float | None = Query(default=None, ge=0.0, le=1000.0),
    sort_by: Literal[
        "psa10_profit_desc",
        "psa10_roi_desc",
        "psa9_profit_desc",
        "psa9_roi_desc",
        "ev_desc",
        "spread_desc",
        "raw_price_asc",
        "raw_price_desc",
    ] = Query(default="psa10_profit_desc"),
    target_grade: Literal["all", "psa10", "psa9"] = Query(default="all"),
    min_profit: float | None = Query(default=None),
    max_raw_price: float | None = Query(default=None, ge=0.0, description="Only include cards with raw price ≤ this value"),
    min_spread: float | None = Query(default=None, ge=0.0, description="Only include cards whose PSA10/raw multiplier ≥ this value"),
    psa9_safe_only: bool = Query(default=False),
    set_id: str | None = Query(default=None, max_length=64),
    q: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> GradingProfitResponse:
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    return calculate_grading_profit(
        db,
        grading_fee=grading_fee,
        sort_by=sort_by,
        target_grade=target_grade,
        min_profit=min_profit,
        max_raw_price=max_raw_price,
        min_spread=min_spread,
        psa9_safe_only=psa9_safe_only,
        set_id=set_id,
        q=q,
        page=page,
        per_page=per_page,
    )


@router.get("/sealed-signals", response_model=SealedSignalsResponse)
def get_sealed_signals(
    response: Response,
    signal: Literal["all", "strong_buy", "buy", "hold", "underperform"] = Query(default="all"),
    product_type: Literal[
        "all",
        "booster_box",
        "etb",
        "bundle",
        "case",
        "pack",
        "blister",
        "collection",
    ] = Query(default="all"),
    sort_by: Literal[
        "score_desc",
        "supply_asc",
        "momentum_desc",
        "price_desc",
        "price_asc",
        "age_desc",
    ] = Query(default="score_desc"),
    set_id: str | None = Query(default=None, max_length=64),
    q: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SealedSignalsResponse:
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    return calculate_sealed_signals(
        db,
        signal=signal,
        product_type=product_type,
        sort_by=sort_by,
        set_id=set_id,
        q=q,
        page=page,
        per_page=per_page,
    )


@router.get("/top-pokemon-volume", response_model=PokemonVolumeResponse)
def get_top_pokemon_volume(
    response: Response,
    timeframe: Literal["24h", "7d", "30d", "all_time", "2026_ytd"] = Query(
        default="7d", description="Observed market value timeframe"
    ),
    sort_by: Literal["volume_desc", "sales_desc", "growth_desc", "avg_price_desc"] = Query(
        default="volume_desc", description="Rank sorting metric"
    ),
    q: str | None = Query(default=None, max_length=100, description="Search Pokémon by name"),
    db: Session = Depends(get_db),
) -> PokemonVolumeResponse:
    """Top 50 Pokémon ranked by aggregated observed market value — computed live from the database."""
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=600, stale-while-revalidate=1200"
    return calculate_top_pokemon_volume(db, timeframe=timeframe, sort_by=sort_by, q=q)


@router.get("/trending", response_model=TrendingDashboardResponse)
def get_trending(
    response: Response,
    timeframe: Literal["24h", "7d", "30d", "all_time", "2026_ytd"] = Query(
        default="7d", description="Timeframe for trending volume calculations"
    ),
    q: str | None = Query(default=None, max_length=100, description="Search cards and Pokémon"),
    db: Session = Depends(get_db),
) -> TrendingDashboardResponse:
    """Returns the 3-column Trending Dashboard: Trending Cards, Popular Pokémon, and Volume Leaders."""
    response.headers["Cache-Control"] = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"
    return get_trending_dashboard(db, timeframe=timeframe, q=q)


@router.post("/trending/reset", dependencies=[Depends(verify_admin_token)])
def reset_trending() -> dict[str, str]:
    """Reset all click and search counters to zero and invalidate trending caches."""
    reset_trending_analytics()
    return {"status": "ok", "message": "Trending analytics reset to zero"}


@router.post(
    "/track-action",
    dependencies=[
        Depends(
            rate_limit(
                max_requests=get_settings().rate_limit_track_action_per_minute,
                bucket="track_action",
            )
        )
    ],
)
def track_user_action(payload: TrackActionRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """Track user clicks, searches, and views for real-time trending analytics."""
    record_action(entity_type=payload.entity_type, entity_id=payload.entity_id, action=payload.action)
    if payload.entity_type == "card":
        card = db.query(Card).filter(Card.id == payload.entity_id).first()
        if card:
            poke = match_to_pokemon(card.name)
            if poke:
                record_action("pokemon", poke, payload.action)
    return {"status": "ok"}



@router.get("/live-updates", response_model=LiveUpdatesResponse)
def get_live_updates(
    response: Response,
    provider: Literal["all", "ebay", "tcgapi"] = Query(default="all", description="Source provider filter"),
    grade_filter: Literal["all", "graded", "psa10", "psa9", "raw"] = Query(
        default="all", description="Grading filter"
    ),
    set_id: str | None = Query(default=None, description="Filter by set ID"),
    q: str | None = Query(default=None, max_length=100, description="Search card by name or number"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=24, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> LiveUpdatesResponse:
    """Returns chronologically ordered live price observations and comp updates."""
    response.headers["Cache-Control"] = "public, max-age=5, s-maxage=10"
    stmt = (
        select(PriceObservation, Card, Set)
        .join(Card, PriceObservation.card_id == Card.id)
        .join(Set, Card.set_id == Set.id)
        .where(
            Card.name.not_ilike("%code card%"),
            PriceObservation.price.is_not(None),
            PriceObservation.price > 0,
        )
    )

    # Provider filter
    if provider == "ebay":
        stmt = stmt.where(PriceObservation.provider.ilike("%ebay%"))
    elif provider == "tcgapi":
        stmt = stmt.where(PriceObservation.provider == "tcgapi")

    # Grade filter
    if grade_filter == "graded":
        stmt = stmt.where(PriceObservation.grading_company.is_not(None))
    elif grade_filter == "psa10":
        stmt = stmt.where(
            PriceObservation.grading_company == "PSA",
            PriceObservation.grade.in_(["10", 10, "10.0", 10.0]),
        )
    elif grade_filter == "psa9":
        stmt = stmt.where(
            PriceObservation.grading_company == "PSA",
            PriceObservation.grade.in_(["9", 9, "9.0", 9.0]),
        )
    elif grade_filter == "raw":
        stmt = stmt.where(PriceObservation.grading_company.is_(None))

    # Set filter
    if set_id:
        stmt = stmt.where(Card.set_id == set_id)

    # Search filter
    if q and q.strip():
        search_pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                Card.name.ilike(search_pattern, escape="\\"),
                Card.number.ilike(search_pattern, escape="\\"),
                Set.name.ilike(search_pattern, escape="\\"),
            )
        )

    # Total items count: cache default unfiltered count for 60s to prevent full table scans every 15s
    is_unfiltered = (provider == "all" and grade_filter == "all" and not set_id and not (q and q.strip()))
    _TOTAL_ITEMS_KEY = "cardboarddex:live_updates:total_items"
    total_items: int | None = None
    _count_redis = _get_redis()
    if is_unfiltered and _count_redis is not None:
        try:
            cached_val = _count_redis.get(_TOTAL_ITEMS_KEY)
            if cached_val is not None:
                total_items = int(cached_val)
        except (RedisError, ValueError, Exception) as exc:
            logger.warning("Failed reading cached live-updates total_items: %s", exc)

    if total_items is None:
        total_items = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        if is_unfiltered and _count_redis is not None:
            try:
                _count_redis.setex(_TOTAL_ITEMS_KEY, 60, str(total_items))
            except (RedisError, Exception) as exc:
                logger.warning("Failed caching live-updates total_items: %s", exc)

    total_pages = max(1, math.ceil(total_items / per_page))

    # Global KPI summary counts are unfiltered and change slowly, so we cache them in
    # Redis for 60 s to avoid 3 separate full-table COUNT scans on every 15-second poll.
    _KPI_KEY = "cardboarddex:live_updates:kpi"
    total_ebay = total_tcg = total_graded = 0
    _kpi_redis = _get_redis()
    _kpi_cached = False
    if _kpi_redis is not None:
        try:
            _raw_kpi = _kpi_redis.get(_KPI_KEY)
            if _raw_kpi:
                _kpi = json.loads(_raw_kpi)
                total_ebay = _kpi.get("ebay", 0)
                total_tcg = _kpi.get("tcg", 0)
                total_graded = _kpi.get("graded", 0)
                _kpi_cached = True
        except (RedisError, json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "live-updates KPI Redis cache read failed error=%s: %s",
                type(exc).__name__,
                exc,
            )

    if not _kpi_cached:
        # Single combined aggregate query (3 FILTER expressions) replaces 3 separate COUNTs
        _kpi_row = db.execute(
            select(
                func.count(case((PriceObservation.provider.ilike("%ebay%"), 1))).label("ebay"),
                func.count(case((PriceObservation.provider == "tcgapi", 1))).label("tcg"),
                func.count(case((PriceObservation.grading_company.is_not(None), 1))).label("graded"),
            )
        ).one()
        total_ebay = _kpi_row.ebay or 0
        total_tcg = _kpi_row.tcg or 0
        total_graded = _kpi_row.graded or 0
        if _kpi_redis is not None:
            try:
                _kpi_redis.setex(
                    _KPI_KEY,
                    60,
                    json.dumps({"ebay": total_ebay, "tcg": total_tcg, "graded": total_graded}),
                )
            except (RedisError, Exception) as exc:
                logger.warning(
                    "live-updates KPI Redis cache write failed error=%s: %s",
                    type(exc).__name__,
                    exc,
                )

    # Paginated results ordered by observed_at descending
    offset = (page - 1) * per_page
    rows = db.execute(
        stmt.order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        .offset(offset)
        .limit(per_page)
    ).all()

    items: list[LiveUpdateItem] = []
    for obs, card, cset in rows:
        listing_title = None
        listing_url = None
        if isinstance(obs.payload, dict):
            listing_title = obs.payload.get("title") or obs.payload.get("item", {}).get("title")
            listing_url = (
                obs.payload.get("item_url")
                or obs.payload.get("item", {}).get("itemWebUrl")
                or obs.payload.get("item", {}).get("item_url")
            )

        items.append(
            LiveUpdateItem(
                id=str(obs.id),
                card_id=card.id,
                card_name=card.name,
                set_id=card.set_id,
                set_name=cset.name,
                number=card.number,
                rarity=card.rarity,
                image_url=f"/cards/{card.id}/image",
                provider=obs.provider,
                price=float(obs.price),
                currency=obs.currency or "USD",
                condition=obs.condition,
                printing=obs.printing,
                grading_company=obs.grading_company,
                grade=str(obs.grade) if obs.grade is not None else None,
                listing_title=listing_title,
                listing_url=listing_url,
                observed_at=obs.observed_at or obs.provider_updated_at or datetime.now(UTC),
            )
        )

    return LiveUpdatesResponse(
        page=page,
        per_page=per_page,
        total_items=total_items,
        total_pages=total_pages,
        provider_filter=provider,
        grade_filter=grade_filter,
        total_ebay_updates=total_ebay,
        total_tcg_updates=total_tcg,
        graded_updates_count=total_graded,
        items=items,
        updated_at=datetime.now(UTC),
    )


@router.get("/{card_id}", response_model=CardDetail)
def get_card(
    card_id: str,
    response: Response,
    ref: str | None = Query(default=None, description="Navigation referrer tag"),
    db: Session = Depends(get_db),
) -> CardDetail:
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    row = db.execute(
        select(Card, Set).join(Set, Card.set_id == Set.id).where(Card.id == card_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    card, card_set = row
    if ref != "trending":
        record_action("card", card_id, "view")
        poke = match_to_pokemon(card.name)
        if poke:
            record_action("pokemon", poke, "view")
    latest_synced = db.scalar(
        select(func.max(ProviderCardState.last_synced_at)).where(ProviderCardState.card_id == card_id)
    )
    summary = _summary(card, card_set, last_updated_at=latest_synced)
    return CardDetail(
        **summary.model_dump(),
        series=card_set.series,
        release_date=card_set.release_date,
    )


def _extract_listing_url(item: PriceObservation) -> str | None:
    candidate: str | None = None
    if isinstance(item.payload, dict):
        raw_item = item.payload.get("item")
        if isinstance(raw_item, dict) and raw_item.get("itemWebUrl"):
            candidate = str(raw_item["itemWebUrl"])
        elif item.payload.get("itemWebUrl"):
            candidate = str(item.payload["itemWebUrl"])
        elif item.payload.get("item_url"):
            candidate = str(item.payload["item_url"])
    if not candidate and item.provider == "ebay" and item.provider_card_id:
        clean_id = item.provider_card_id.replace("v1|", "").split("|")[0]
        if clean_id.isdigit():
            candidate = f"https://www.ebay.com/itm/{clean_id}"

    if candidate:
        try:
            parsed = urlparse(candidate)
            if parsed.scheme in ("https", "http"):
                host = (parsed.hostname or "").lower()
                if any(host == d or host.endswith(f".{d}") for d in ALLOWED_MARKETPLACE_DOMAINS):
                    return candidate
        except Exception as exc:
            logger.debug("Failed parsing listing URL candidate=%s: %s", candidate, exc)
    return None


@router.get("/{card_id}/prices", response_model=CardPricingResponse)
def get_card_prices(
    card_id: str,
    response: Response,
    days: int = Query(default=365, ge=1, le=730),
    db: Session = Depends(get_db),
) -> CardPricingResponse:
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    if db.get(Card, card_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    cutoff = datetime.now(UTC) - timedelta(days=days)
    states = list(db.scalars(
        select(ProviderCardState)
        .where(
            ProviderCardState.card_id == card_id,
            or_(
                ProviderCardState.provider == "tcgapi",
                ProviderCardState.provider.ilike("%ebay%"),
            ),
        )
        .order_by(ProviderCardState.provider)
    ))
    observations = list(db.scalars(
        select(PriceObservation)
        .where(
            PriceObservation.card_id == card_id,
            or_(
                PriceObservation.provider == "tcgapi",
                PriceObservation.provider.ilike("%ebay%"),
            ),
            or_(
                PriceObservation.observed_at >= cutoff,
                PriceObservation.provider_updated_at >= cutoff,
                PriceObservation.provider_updated_at.is_(None),
            ),
        )
        .order_by(
            func.coalesce(PriceObservation.observed_at, PriceObservation.provider_updated_at).asc(),
            PriceObservation.id.asc(),
        )
        .limit(3000)
    ))
    tcg_state = next((s for s in states if s.provider == "tcgapi"), None)
    tcg_price_map: dict[str, dict[str, Any]] = {}
    if tcg_state and isinstance(tcg_state.payload, dict):
        raw_prices = tcg_state.payload.get("prices")
        if isinstance(raw_prices, dict):
            pdata = raw_prices.get("data")
            if isinstance(pdata, list):
                for p in pdata:
                    if isinstance(p, dict) and p.get("printing"):
                        tcg_price_map[str(p["printing"]).lower()] = p
            elif isinstance(pdata, dict) and pdata.get("printing"):
                tcg_price_map[str(pdata["printing"]).lower()] = pdata

    def _resolve_obs_payload(item: PriceObservation) -> dict[str, Any]:
        """Merge pricing sub-fields from different payload shapes into a flat dict.

        sync_catalog observations store fields nested under a "variant" key.
        collect_prices observations store fields directly at the top level.
        This helper handles both, giving priority to top-level values when present.
        """
        res: dict[str, Any] = {}
        if item.provider == "tcgapi" and item.printing:
            mapped = tcg_price_map.get(item.printing.lower())
            if mapped:
                res.update(mapped)
        if isinstance(item.payload, dict):
            # Step 1: merge nested "variant" sub-key (written by sync_catalog.py)
            variant_data = item.payload.get("variant")
            if isinstance(variant_data, dict):
                for k, v in variant_data.items():
                    if k not in res or res.get(k) is None:
                        res[k] = v
            # Step 2: merge top-level keys (written by collect_prices.py, or new sync_catalog format)
            for k, v in item.payload.items():
                if k in ("variant", "raw_card"):
                    continue
                if v is not None or k not in res:
                    res[k] = v
        return res

    def _build_obs_item(obs: PriceObservation) -> PriceObservationItem:
        """Resolve the payload dict exactly once per observation (was called 7× previously)."""
        resolved = _resolve_obs_payload(obs)
        return PriceObservationItem(
            provider=obs.provider,
            provider_card_id=obs.provider_card_id,
            variant_id=obs.variant_id,
            condition=obs.condition,
            printing=obs.printing,
            grading_company=obs.grading_company,
            grade=float(obs.grade) if obs.grade is not None else None,
            price=float(obs.price),
            currency=obs.currency,
            provider_updated_at=obs.provider_updated_at,
            observed_at=obs.observed_at,
            listing_url=_extract_listing_url(obs),
            low_price=_extract_float(resolved, "low_price"),
            median_price=_extract_float(resolved, "median_price"),
            lowest_with_shipping=_extract_float(resolved, "lowest_with_shipping"),
            buylist_price=_extract_float(resolved, "buylist_price"),
            price_change_24h=_extract_float(resolved, "price_change_24h"),
            price_change_7d=_extract_float(resolved, "price_change_7d"),
            price_change_30d=_extract_float(resolved, "price_change_30d"),
        )

    obs_items = [_build_obs_item(obs) for obs in observations]

    # Deduplicate observations so that only the latest price per active listing/variant is used
    latest_obs_map: dict[str, PriceObservationItem] = {}
    for obs_item in obs_items:
        if "ebay" in obs_item.provider.lower():
            key = f"{obs_item.provider}:{obs_item.variant_id}:{obs_item.provider_card_id}"
        else:
            key = f"{obs_item.provider}:{obs_item.variant_id}"
        latest_obs_map[key] = obs_item
    latest_items = list(latest_obs_map.values())

    # Calculate average listing price across active observations
    # Priority:
    # 1. Raw verified eBay listings (ungraded)
    # 2. All verified eBay listings
    # 3. TCG active listing estimates (median_price / low_price)
    raw_ebay_prices = [
        item.price
        for item in latest_items
        if "ebay" in item.provider.lower() and not item.grading_company
    ]
    if raw_ebay_prices:
        avg_listing_price = round(sum(raw_ebay_prices) / len(raw_ebay_prices), 2)
    else:
        all_ebay_prices = [
            item.price
            for item in latest_items
            if "ebay" in item.provider.lower()
        ]
        if all_ebay_prices:
            avg_listing_price = round(sum(all_ebay_prices) / len(all_ebay_prices), 2)
        else:
            tcg_prices: list[float] = []
            for item in latest_items:
                if item.provider == "tcgapi":
                    if item.median_price is not None:
                        tcg_prices.append(item.median_price)
                    elif item.low_price is not None:
                        tcg_prices.append(item.low_price)
            avg_listing_price = round(sum(tcg_prices) / len(tcg_prices), 2) if tcg_prices else None

    return CardPricingResponse(
        card_id=card_id,
        provider_states=[ProviderPricingState(
            provider=item.provider,
            match_status=item.match_status,
            last_synced_at=item.last_synced_at,
        ) for item in states],
        observations=obs_items,
        avg_listing_price=avg_listing_price,
    )


# Broken card image IDs are tracked in Redis with a 24-hour TTL so they persist across
# server restarts (preventing repeat CDN 404 calls) and self-heal after images are fixed.
# Key per card: cardboarddex:broken_img:{card_id} → "1"  (with TTL = _BROKEN_IMG_TTL)
_BROKEN_IMG_TTL = 86400  # 24 hours
_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="560" viewBox="0 0 400 560" fill="none">'
    b'<rect width="400" height="560" rx="16" fill="#1e293b"/>'
    b'<rect x="20" y="20" width="360" height="520" rx="12" stroke="#334155" stroke-width="2" stroke-dasharray="8 8"/>'
    b'<circle cx="200" cy="260" r="32" fill="#334155"/>'
    b'<path d="M190 260h20M200 250v20" stroke="#64748b" stroke-width="3" stroke-linecap="round"/>'
    b'<text x="200" y="320" fill="#94a3b8" font-size="13" font-family="system-ui, -apple-system, sans-serif" font-weight="600" text-anchor="middle">Image Not Available</text>'
    b'</svg>'
)


@router.get("/{card_id}/image")
def get_card_image(
    card_id: str,
    db: Session = Depends(get_db),
    client: TCGAPIClient = Depends(get_tcgapi_client),
) -> Response:
    # 1. Path traversal and injection protection
    if not RE_SAFE_CARD_ID.match(card_id) or len(card_id) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid card ID format",
        )

    # Check Redis-backed broken image registry before hitting the DB or CDN.
    # Each broken card ID is stored as a standalone key with a 24-hour TTL so
    # temporarily unavailable images self-heal after the TTL expires.
    _img_redis = _get_redis()
    _broken_key = f"cardboarddex:broken_img:{card_id}"
    _is_broken = False
    if _img_redis is not None:
        try:
            _is_broken = bool(_img_redis.exists(_broken_key))
        except RedisError as exc:
            logger.warning(
                "Broken image Redis check failed card_id=%s error=%s: %s",
                card_id,
                type(exc).__name__,
                exc,
            )
    if _is_broken:
        return Response(
            content=_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    card = db.get(Card, card_id)
    if card is None or not card.image_url:
        return Response(
            content=_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    settings = get_settings()
    if settings.s3_bucket_name:
        s3_url = f"https://{settings.s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/cards/{card_id}.png"
        if settings.cloudfront_domain:
            s3_url = f"https://{settings.cloudfront_domain}/cards/{card_id}.png"
        try:
            s3_resp = httpx.head(s3_url, timeout=1.5)
            if s3_resp.status_code == 200:
                return Response(
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                    headers={
                        "Location": s3_url,
                        "Cache-Control": "public, max-age=31536000, immutable",
                    },
                )
        except Exception as exc:
            logger.debug("S3 image check skipped card_id=%s: %s", card_id, exc)

    try:
        content, content_type = client.get_image(card.image_url)
        if settings.s3_bucket_name:
            try:
                _s3 = _get_s3_client(settings.aws_region)
                if _s3 is not None:
                    _s3.put_object(
                        Bucket=settings.s3_bucket_name,
                        Key=f"cards/{card_id}.png",
                        Body=content,
                        ContentType=content_type or "image/png",
                        CacheControl="public, max-age=31536000, immutable",
                    )
            except Exception as s3_err:
                logger.debug("Background S3 cache upload skipped card_id=%s: %s", card_id, s3_err)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            if _img_redis is not None:
                try:
                    _img_redis.setex(_broken_key, _BROKEN_IMG_TTL, "1")
                except RedisError as exc2:
                    logger.warning(
                        "Failed to mark broken image in Redis card_id=%s error=%s: %s",
                        card_id,
                        type(exc2).__name__,
                        exc2,
                    )
            logger.info(
                "Card image not found upstream card_id=%s url=%s; caching 404 fallback",
                card_id,
                card.image_url,
            )
            return Response(
                content=_PLACEHOLDER_SVG,
                media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Image provider rejected request") from exc
    except (httpx.RequestError, ValueError) as exc:
        if _img_redis is not None:
            try:
                _img_redis.setex(_broken_key, _BROKEN_IMG_TTL, "1")
            except RedisError as exc2:
                logger.warning(
                    "Failed to mark broken image in Redis card_id=%s error=%s: %s",
                    card_id,
                    type(exc2).__name__,
                    exc2,
                )
        logger.warning(
            "Card image request failed card_id=%s error=%s: %s; serving placeholder",
            card_id,
            type(exc).__name__,
            exc,
        )
        return Response(
            content=_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "CDN-Cache-Control": "public, max-age=31536000, immutable",
        },
    )
