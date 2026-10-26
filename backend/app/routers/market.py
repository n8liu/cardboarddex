from app.services.listing_quality import eligible_observation
from app.services.collection_stats import live_observation_count
from app.common.response_cache import cached_read
from app.services.movers_service import stored_movers
from app.services.image_delivery import card_image_url
from app.common.cache import TTLCache

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
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from app.common.formatters import (
    parse_iso_datetime as _parse_iso_datetime,
)
from app.common.redis import get_redis as _get_redis
from app.database import get_db
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.schemas.cards import (
    GradingProfitResponse,
    LiveUpdateItem,
    LiveUpdatesResponse,
    LiveFeedResponse,
    LiveStatsResponse,
    MarketMoverItem,
    MarketMoversResponse,
    SealedSignalsResponse,
)
from app.services.grading_service import calculate_grading_profit
from app.services.sealed_service import calculate_sealed_signals
from app.services.image_download import ImageClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["Market"])

ALLOWED_MARKETPLACE_DOMAINS = {"ebay.com", "tcgplayer.com"}


@lru_cache
def get_image_client() -> ImageClient:
    return ImageClient()


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
            image_url=card_image_url(card.id),
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
            image_url=card_image_url(card_id),
            printing=printing,
            market_price=market_price,
            price_change_percentage=round(pct, 2),
            price_change_amount=price_change_amount,
            period=period,
            direction=direction,
            last_updated_at=last_updated_at,
        )


_MOVERS_LOCAL_FALLBACK = TTLCache(max_entries=64, ttl=900)
_MOVERS_CACHE_TTL = 900  # seconds


@router.get("/market-movers", response_model=MarketMoversResponse)
def get_market_movers(
    response: Response,
    direction: Literal["up", "down", "all"] = Query(default="all"),
    period: Literal["24h", "7d", "30d"] = Query(default="24h"),
    game: Literal["pokemon", "pokemon-japan"] = Query(default="pokemon"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MarketMoversResponse:
    ranking, updated_at = stored_movers(db=db, game=game, period=period)
    response.headers['Cache-Control'] = 'public, no-cache, max-age=0, must-revalidate'
    response.headers['X-Cache-Generated-At'] = updated_at.isoformat()
    start = (page - 1) * per_page
    # Pages stop at the snapshot's rows; the totals still count every mover.
    count = max(len(ranking.gainers) if direction != 'down' else 0, len(ranking.losers) if direction != 'up' else 0)
    # The worker does not mount the image manifest, so image URLs resolve per page here.
    page_items = lambda items: [item.model_copy(update={'image_url': card_image_url(item.card_id)})
                                for item in items[start:start + per_page]]
    return MarketMoversResponse(
        period=period, direction=direction, page=page, per_page=per_page,
        total_gainers=ranking.total_gainers, total_losers=ranking.total_losers,
        total_pages=max(1, math.ceil(count / per_page)),
        gainers=page_items(ranking.gainers) if direction != 'down' else [],
        losers=page_items(ranking.losers) if direction != 'up' else [],
        updated_at=updated_at,
    )


@router.get("/grading-profit", response_model=GradingProfitResponse)
@cached_read("get_grading_profit_identity_v1", fresh=300, maximum=1800)
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
    return calculate_grading_profit(
        db,
        use_cache=False,
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
@cached_read("get_sealed_signals_v2", fresh=300, maximum=1800)
def get_sealed_signals(
    response: Response,
    game: Literal["all", "pokemon", "pokemon-japan"] = Query(default="all"),
    period: Literal["30", "90"] = Query(default="30"),
    era: Literal["all", "newer", "older"] = Query(default="all"),
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
    return calculate_sealed_signals(
        db,
        use_cache=False,
        game=game,
        era=era,
        period=int(period),
        signal=signal,
        product_type=product_type,
        sort_by=sort_by,
        set_id=set_id,
        q=q,
        page=page,
        per_page=per_page,
    )


def _live_feed_query(provider, grade_filter, set_id, q):
    stmt = select(PriceObservation, Card, Set).join(Card, PriceObservation.card_id == Card.id).join(Set, Card.set_id == Set.id)

    if provider == "ebay":
        stmt = stmt.where(PriceObservation.provider == "ebay")
    elif provider == "tcgapi":
        stmt = stmt.where(PriceObservation.provider == "tcgapi")

    if provider == "pokemonpricetracker":
        stmt = stmt.where(PriceObservation.provider == "pokemonpricetracker")

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

    stmt = stmt.where(eligible_observation())
    return stmt


def _live_feed_items(rows):
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
                image_url=card_image_url(card.id),
                provider=obs.provider,
                update_type=(obs.payload or {}).get("update_type") or ("asking_listing" if obs.provider == "ebay" else "market_update"),
                price_date=obs.provider_updated_at,
                metric=(obs.payload or {}).get("metric"),
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
    return items


@router.get("/live-updates", response_model=LiveUpdatesResponse)
def get_live_updates(
    response: Response,
    provider: Literal["all", "ebay", "tcgapi", "pokemonpricetracker"] = Query(default="all", description="Source provider filter"),
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

    stmt = _live_feed_query(provider, grade_filter, set_id, q)

    is_unfiltered = (
        provider == "all"
        and grade_filter == "all"
        and set_id is None
        and not (q and q.strip())
    )

    r = _get_redis()
    total_items = live_observation_count(db, r) if is_unfiltered else (
        db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )

    total_pages = max(1, math.ceil(total_items / per_page))
    offset = (page - 1) * per_page

    order_col = func.coalesce(PriceObservation.observed_at, PriceObservation.provider_updated_at)
    stmt = stmt.order_by(order_col.desc(), PriceObservation.id.desc()).offset(offset).limit(per_page)
    rows = db.execute(stmt).all()

    from app.config import get_settings
    kpi_cache_key = "cardboarddex:live_updates:kpi:identity-v1" + (":ppt" if get_settings().ppt_primary_enabled else "")
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
        from app.services.collection_stats import live_observation_totals
        kpi_result = live_observation_totals(db)
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

    items = _live_feed_items(rows)

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


@router.get("/live-updates/feed", response_model=LiveFeedResponse)
def get_live_feed(
    response: Response,
    provider: Literal["all", "ebay", "tcgapi", "pokemonpricetracker"] = Query(default="all"),
    grade_filter: Literal["all", "graded", "psa10", "psa9", "raw"] = Query(default="all"),
    set_id: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> LiveFeedResponse:
    from app.config import get_settings
    if get_settings().live_feed_shared_cache_enabled and page == 1 and not set_id and not (q and q.strip()):
        result = _shared_live_feed(response=response, provider=provider, grade_filter=grade_filter,
                                   per_page=per_page, db=db)
        response.headers["Cache-Control"] = "no-store"
        return result
    response.headers["Cache-Control"] = "no-store"
    return _live_feed_page(db, provider, grade_filter, set_id, q, page, per_page)


# Every open Live Comps tab polls page 1 every 15s; share one query instead of one per tab.
@cached_read("get_live_feed_v1", fresh=10, maximum=60)
def _shared_live_feed(
    response: Response,
    provider: str,
    grade_filter: str,
    per_page: int,
    db: Session,
) -> LiveFeedResponse:
    return _live_feed_page(db, provider, grade_filter, None, None, 1, per_page)


def _live_feed_page(db, provider, grade_filter, set_id, q, page, per_page):
    started = time.monotonic()
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
    stmt = _live_feed_query(provider, grade_filter, set_id, q)
    order_col = func.coalesce(PriceObservation.observed_at, PriceObservation.provider_updated_at)
    rows = db.execute(stmt.order_by(order_col.desc(), PriceObservation.id.desc())
                      .offset((page - 1) * per_page).limit(per_page + 1)).all()
    logger.info("Live feed query page=%s per_page=%s rows=%s duration_ms=%.1f",
                page, per_page, len(rows), (time.monotonic() - started) * 1000)
    return LiveFeedResponse(page=page, per_page=per_page, has_more=len(rows) > per_page,
        items=_live_feed_items(rows[:per_page]), updated_at=datetime.now(UTC))


@router.get("/live-updates/stats", response_model=LiveStatsResponse)
def get_live_stats(response: Response) -> LiveStatsResponse:
    from app.services.live_stats import read_snapshot
    response.headers["Cache-Control"] = "no-store"
    return read_snapshot()
