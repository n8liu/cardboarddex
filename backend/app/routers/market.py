import json
import logging
import math
import time
from functools import lru_cache
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, Response
from redis.exceptions import RedisError
from sqlalchemy import case, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.common.formatters import (
    extract_float as _extract_float,
    parse_iso_datetime as _parse_iso_datetime,
)
from app.common.redis import get_redis as _get_redis
from app.database import get_db
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.schemas.cards import (
    GradingProfitResponse,
    LiveUpdateItem,
    LiveUpdatesResponse,
    MarketMoverItem,
    MarketMoversResponse,
    SealedSignalsResponse,
)
from app.services.grading_service import calculate_grading_profit
from app.services.sealed_service import calculate_sealed_signals
from app.tcgapi import TCGAPIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["Market"])

ALLOWED_MARKETPLACE_DOMAINS = {"ebay.com", "tcgplayer.com"}


@lru_cache
def get_tcgapi_client() -> TCGAPIClient:
    return TCGAPIClient(acquire_request=lambda: None)


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

    if not _served_from_cache:
        _local = _MOVERS_LOCAL_FALLBACK.get(redis_cache_key)
        if _local and (now - _local[0]) < _MOVERS_CACHE_TTL:
            _, gainers_raw, losers_raw = _local
            _served_from_cache = True

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
            _MOVERS_LOCAL_FALLBACK[redis_cache_key] = (now, gainers_raw, losers_raw)
        elif _MOVERS_LOCAL_FALLBACK.get(redis_cache_key):
            logger.warning(
                "Serving stale market movers (provider error) cache_key=%s",
                redis_cache_key,
            )
            _, gainers_raw, losers_raw = _MOVERS_LOCAL_FALLBACK[redis_cache_key]

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
    per_page: int = Query(default=30, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> LiveUpdatesResponse:
    response.headers["Cache-Control"] = "public, max-age=5, s-maxage=10, stale-while-revalidate=30"

    stmt = select(PriceObservation, Card, Set).join(Card, PriceObservation.card_id == Card.id).join(Set, Card.set_id == Set.id)

    if provider == "ebay":
        stmt = stmt.where(PriceObservation.provider == "ebay")
    elif provider == "tcgapi":
        stmt = stmt.where(PriceObservation.provider == "tcgapi")

    if grade_filter == "graded":
        stmt = stmt.where(PriceObservation.grading_company.is_not(None))
    elif grade_filter == "psa10":
        stmt = stmt.where(
            PriceObservation.grading_company == "PSA",
            PriceObservation.grade == 10.0,
        )
    elif grade_filter == "psa9":
        stmt = stmt.where(
            PriceObservation.grading_company == "PSA",
            PriceObservation.grade == 9.0,
        )
    elif grade_filter == "raw":
        stmt = stmt.where(PriceObservation.grading_company.is_(None))

    if set_id:
        stmt = stmt.where(Card.set_id == set_id)

    if q and q.strip():
        search_term = q.strip()
        from app.common.formatters import escape_like as _escape_like
        pattern = f"%{_escape_like(search_term)}%"
        stmt = stmt.where(
            or_(
                Card.name.ilike(pattern, escape="\\"),
                Card.number.ilike(pattern, escape="\\"),
                Set.name.ilike(pattern, escape="\\"),
            )
        )

    is_unfiltered = (
        provider == "all"
        and grade_filter == "all"
        and set_id is None
        and not (q and q.strip())
    )

    r = _get_redis()
    total_items: int | None = None
    if is_unfiltered and r is not None:
        try:
            cached_total = r.get("cardboarddex:live_updates:total_count")
            if cached_total:
                total_items = int(cached_total)
        except Exception:
            pass

    if total_items is None:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_items = db.scalar(count_stmt) or 0
        if is_unfiltered and r is not None:
            try:
                r.setex("cardboarddex:live_updates:total_count", 60, str(total_items))
            except Exception:
                pass

    total_pages = max(1, math.ceil(total_items / per_page))
    offset = (page - 1) * per_page

    order_col = func.coalesce(PriceObservation.observed_at, PriceObservation.provider_updated_at)
    stmt = stmt.order_by(order_col.desc(), PriceObservation.id.desc()).offset(offset).limit(per_page)
    rows = db.execute(stmt).all()

    kpi_cache_key = "cardboarddex:live_updates:kpi"
    total_ebay: int | None = None
    total_tcg: int | None = None
    total_graded: int | None = None

    if r is not None:
        try:
            kpi_raw = r.get(kpi_cache_key)
            if kpi_raw:
                kpi_data = json.loads(kpi_raw)
                total_ebay = kpi_data.get("ebay")
                total_tcg = kpi_data.get("tcg")
                total_graded = kpi_data.get("graded")
        except Exception as exc:
            logger.warning("Redis live-updates KPI read failed: %s", exc)

    if total_ebay is None or total_tcg is None or total_graded is None:
        kpi_stmt = select(
            func.count(case((PriceObservation.provider == "ebay", 1))),
            func.count(case((PriceObservation.provider == "tcgapi", 1))),
            func.count(case((PriceObservation.grading_company.is_not(None), 1))),
        )
        kpi_result = db.execute(kpi_stmt).one()
        total_ebay, total_tcg, total_graded = kpi_result[0] or 0, kpi_result[1] or 0, kpi_result[2] or 0
        if r is not None:
            try:
                r.setex(
                    kpi_cache_key,
                    60,
                    json.dumps({"ebay": total_ebay, "tcg": total_tcg, "graded": total_graded}),
                )
            except Exception as exc:
                logger.warning("Redis live-updates KPI write failed: %s", exc)

    items: list[LiveUpdateItem] = []
    for obs, card, card_set in rows:
        listing_url = _extract_listing_url(obs)
        listing_title: str | None = None
        if isinstance(obs.payload, dict):
            listing_title = (
                obs.payload.get("listing_title")
                or obs.payload.get("title")
                or (obs.payload.get("item") or {}).get("title")
            )
        if not listing_title:
            components = [card.name]
            if card.number:
                components.append(f"#{card.number}")
            if obs.printing:
                components.append(f"({obs.printing})")
            if obs.grading_company and obs.grade is not None:
                components.append(f"{obs.grading_company} {obs.grade}")
            listing_title = " ".join(components)

        price_val = float(obs.price) if obs.price is not None else 0.0
        items.append(
            LiveUpdateItem(
                id=str(obs.id),
                card_id=card.id,
                card_name=card.name,
                set_name=card_set.name,
                set_id=card.set_id,
                card_number=card.number,
                image_url=f"/cards/{card.id}/image",
                provider=obs.provider,
                price=price_val,
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
