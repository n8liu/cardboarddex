import hashlib
import json
import logging
import math
import time
from datetime import UTC, datetime
from typing import Literal

from redis.exceptions import RedisError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.formatters import escape_like
from app.common.redis import get_redis
from app.config import get_settings
from app.models import Card, PriceObservation, Set
from app.schemas.cards import GradingProfitItem, GradingProfitResponse

logger = logging.getLogger(__name__)

_GRADING_PROFIT_LOCAL_FALLBACK: dict[str, tuple[float, GradingProfitResponse]] = {}
_GRADING_CACHE_TTL = 300  # 5 minutes


def calculate_grading_profit(
    db: Session,
    *,
    grading_fee: float | None = None,
    sort_by: Literal[
        "psa10_profit_desc",
        "psa10_roi_desc",
        "psa9_profit_desc",
        "psa9_roi_desc",
        "ev_desc",
        "spread_desc",
        "raw_price_asc",
        "raw_price_desc",
    ] = "psa10_profit_desc",
    target_grade: Literal["all", "psa10", "psa9"] = "all",
    min_profit: float | None = None,
    max_raw_price: float | None = None,
    min_spread: float | None = None,
    psa9_safe_only: bool = False,
    set_id: str | None = None,
    q: str = "",
    page: int = 1,
    per_page: int = 24,
) -> GradingProfitResponse:
    """Calculate potential grading profit and ROI metrics across raw and graded comps."""
    now = time.time()
    cache_key_raw = (
        f"{grading_fee}:{sort_by}:{target_grade}:{min_profit}:{max_raw_price}:"
        f"{min_spread}:{psa9_safe_only}:{set_id}:{q.strip().lower()}:{page}:{per_page}"
    )
    cache_hash = hashlib.md5(cache_key_raw.encode()).hexdigest()
    redis_key = f"cardboarddex:grading_profit:{cache_hash}"

    # 1. Try Redis cache first
    r = get_redis()
    if r is not None:
        try:
            cached_data = r.get(redis_key)
            if cached_data:
                return GradingProfitResponse.model_validate_json(cached_data)
        except (RedisError, Exception) as exc:
            logger.warning("Redis grading profit cache read failed error=%s: %s", type(exc).__name__, exc)

    # 2. Try in-process fallback
    local_cached = _GRADING_PROFIT_LOCAL_FALLBACK.get(redis_key)
    if local_cached and (now - local_cached[0]) < _GRADING_CACHE_TTL:
        return local_cached[1]

    settings = get_settings()
    active_fee = grading_fee if grading_fee is not None else settings.psa_value_fee

    # Query all card IDs with at least one graded comp
    graded_card_ids_stmt = select(PriceObservation.card_id).where(
        PriceObservation.grading_company.is_not(None)
    ).distinct()
    graded_card_ids = list(db.scalars(graded_card_ids_stmt))

    if not graded_card_ids:
        return GradingProfitResponse(
            page=page,
            per_page=per_page,
            total_cards=0,
            total_pages=1,
            grading_fee=active_fee,
            sort_by=sort_by,
            items=[],
            updated_at=datetime.now(UTC),
        )

    # Fetch Card & Set for all matching cards
    card_query = (
        select(Card, Set)
        .join(Set, Card.set_id == Set.id)
        .where(Card.id.in_(graded_card_ids))
    )
    if set_id:
        card_query = card_query.where(Card.set_id == set_id)
    query_str = q.strip().lower()
    if query_str:
        pattern = f"%{escape_like(query_str)}%"
        card_query = card_query.where(
            or_(Card.name.ilike(pattern, escape="\\"), Set.name.ilike(pattern, escape="\\"))
        )

    cards_and_sets = db.execute(card_query).all()
    filtered_card_ids = [card.id for card, _ in cards_and_sets]
    if not filtered_card_ids:
        return GradingProfitResponse(
            page=page,
            per_page=per_page,
            total_cards=0,
            total_pages=1,
            grading_fee=active_fee,
            sort_by=sort_by,
            items=[],
            updated_at=datetime.now(UTC),
        )

    # Fetch all price observations for these cards
    all_obs = db.scalars(
        select(PriceObservation)
        .where(PriceObservation.card_id.in_(filtered_card_ids))
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    ).all()

    obs_by_card: dict[str, list[PriceObservation]] = {}
    for o in all_obs:
        obs_by_card.setdefault(o.card_id, []).append(o)

    items: list[GradingProfitItem] = []
    for card, cset in cards_and_sets:
        c_obs = obs_by_card.get(card.id, [])
        if not c_obs:
            continue

        raw_price: float | None = None
        psa10_price: float | None = None
        psa9_price: float | None = None
        latest_obs_time: datetime | None = None

        for o in c_obs:
            if latest_obs_time is None:
                latest_obs_time = o.observed_at

            # Raw check
            if o.grading_company is None and raw_price is None:
                try:
                    raw_price = float(o.price)
                except (ValueError, TypeError) as exc:
                    logger.debug("Failed parsing raw price for card %s: %s", card.id, exc)

            # PSA 10 check
            if (
                o.grading_company
                and o.grading_company.upper() == "PSA"
                and o.grade is not None
                and float(o.grade) == 10.0
                and psa10_price is None
            ):
                try:
                    psa10_price = float(o.price)
                except (ValueError, TypeError) as exc:
                    logger.debug("Failed parsing PSA 10 price for card %s: %s", card.id, exc)

            # PSA 9 check
            if (
                o.grading_company
                and o.grading_company.upper() == "PSA"
                and o.grade is not None
                and float(o.grade) == 9.0
                and psa9_price is None
            ):
                try:
                    psa9_price = float(o.price)
                except (ValueError, TypeError) as exc:
                    logger.debug("Failed parsing PSA 9 price for card %s: %s", card.id, exc)

        if raw_price is None or raw_price <= 0:
            continue
        if psa10_price is None and psa9_price is None:
            continue

        fee = float(active_fee)
        total_cost = raw_price + fee

        # Calculate PSA 10 metrics
        psa10_profit = round(psa10_price - total_cost, 2) if psa10_price is not None else None
        psa10_roi = (
            round((psa10_profit / total_cost) * 100, 1)
            if psa10_profit is not None and total_cost > 0
            else None
        )

        # Calculate PSA 9 metrics
        psa9_profit = round(psa9_price - total_cost, 2) if psa9_price is not None else None
        psa9_roi = (
            round((psa9_profit / total_cost) * 100, 1)
            if psa9_profit is not None and total_cost > 0
            else None
        )

        spread_multiplier = (
            round(psa10_price / raw_price, 2)
            if psa10_price is not None and raw_price > 0
            else None
        )

        # Weighted Expected Value: 60% PSA 10 + 35% PSA 9 + 5% Raw floor break-even
        ev_p10 = psa10_profit if psa10_profit is not None else 0.0
        ev_p9 = psa9_profit if psa9_profit is not None else 0.0
        expected_value = round((0.60 * ev_p10) + (0.35 * ev_p9), 2)

        # PSA 9 Safe: Does PSA 9 yield positive or break-even profit?
        psa9_safe = psa9_profit is not None and psa9_profit >= 0.0

        # Filter criteria
        if target_grade == "psa10" and psa10_price is None:
            continue
        if target_grade == "psa9" and psa9_price is None:
            continue
        if max_raw_price is not None and raw_price > max_raw_price:
            continue
        if min_spread is not None and (spread_multiplier is None or spread_multiplier < min_spread):
            continue
        if psa9_safe_only and not psa9_safe:
            continue
        if min_profit is not None:
            has_min_p10 = psa10_profit is not None and psa10_profit >= min_profit
            has_min_p9 = psa9_profit is not None and psa9_profit >= min_profit
            if not (has_min_p10 or has_min_p9):
                continue

        items.append(
            GradingProfitItem(
                card_id=card.id,
                name=card.name,
                set_id=card.set_id,
                set_name=cset.name,
                number=card.number,
                rarity=card.rarity,
                image_url=f"/cards/{card.id}/image",
                raw_price=round(raw_price, 2),
                psa10_price=round(psa10_price, 2) if psa10_price is not None else None,
                psa10_profit=psa10_profit,
                psa10_roi=psa10_roi,
                psa9_price=round(psa9_price, 2) if psa9_price is not None else None,
                psa9_profit=psa9_profit,
                psa9_roi=psa9_roi,
                spread_multiplier=spread_multiplier,
                expected_value=expected_value,
                psa9_safe=psa9_safe,
                grading_fee=round(fee, 2),
                last_updated_at=latest_obs_time or card.updated_at,
            )
        )

    # Sorting
    if sort_by == "psa10_roi_desc":
        items.sort(key=lambda x: (x.psa10_roi is not None, x.psa10_roi or -999999.0), reverse=True)
    elif sort_by == "psa9_profit_desc":
        items.sort(key=lambda x: (x.psa9_profit is not None, x.psa9_profit or -999999.0), reverse=True)
    elif sort_by == "psa9_roi_desc":
        items.sort(key=lambda x: (x.psa9_roi is not None, x.psa9_roi or -999999.0), reverse=True)
    elif sort_by == "ev_desc":
        items.sort(key=lambda x: (x.expected_value is not None, x.expected_value or -999999.0), reverse=True)
    elif sort_by == "spread_desc":
        items.sort(key=lambda x: (x.spread_multiplier is not None, x.spread_multiplier or -999999.0), reverse=True)
    elif sort_by == "raw_price_asc":
        items.sort(key=lambda x: x.raw_price)
    elif sort_by == "raw_price_desc":
        items.sort(key=lambda x: x.raw_price, reverse=True)
    else:  # default "psa10_profit_desc"
        items.sort(key=lambda x: (x.psa10_profit is not None, x.psa10_profit or -999999.0), reverse=True)

    total_cards = len(items)
    total_pages = max(1, math.ceil(total_cards / per_page))
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_items = items[start_idx:end_idx]

    response = GradingProfitResponse(
        page=page,
        per_page=per_page,
        total_cards=total_cards,
        total_pages=total_pages,
        grading_fee=round(float(active_fee), 2),
        sort_by=sort_by,
        items=paged_items,
        updated_at=datetime.now(UTC),
    )

    if r is not None:
        try:
            r.setex(redis_key, _GRADING_CACHE_TTL, response.model_dump_json())
        except (RedisError, Exception) as exc:
            logger.warning("Redis grading profit cache write failed error=%s: %s", type(exc).__name__, exc)

    _GRADING_PROFIT_LOCAL_FALLBACK[redis_key] = (now, response)
    return response

