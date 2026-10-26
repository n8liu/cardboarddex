from app.services import asking_prices
from app.services.price_sources import grading_observation
from app.services.image_delivery import card_image_url, image_generation
from app.common.cache import TTLCache
import hashlib
import json
import logging
import math
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

from redis.exceptions import RedisError
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, load_only

from app.common.redis import get_redis
from app.config import get_settings
from app.models import Card, PriceObservation, Set
from app.schemas.cards import GradingProfitItem, GradingProfitResponse
from app.services import market_snapshots

logger = logging.getLogger(__name__)

_GRADING_PROFIT_LOCAL_FALLBACK = TTLCache(max_entries=64, ttl=300)
_GRADING_CACHE_TTL = 300  # 5 minutes
SNAPSHOT_NAME = "grading-identity-v2"
# Positional rows keep the snapshot small: one per card with a raw and a PSA 9/10 price.
FIELDS = ("card_id", "name", "set_id", "set_name", "number", "rarity", "raw_price", "psa10_price",
          "psa9_price", "graded_source", "graded_metric", "last_updated_at")


def build_snapshot(db: Session, now: datetime) -> dict:
    """Latest raw, PSA 9 and PSA 10 price for every graded card. The fee and filters apply per request."""
    snapshot = {"updated_at": now.isoformat(), "fields": FIELDS, "rows": []}
    # Query all card IDs with at least one graded comp
    graded_card_ids_stmt = select(PriceObservation.card_id).where(
        PriceObservation.grading_company.is_not(None), grading_observation()
    ).distinct()
    graded_card_ids = list(db.scalars(graded_card_ids_stmt))
    if not graded_card_ids:
        return snapshot

    # Bound ORM objects and asking-listing pools to one batch within the worker budget.
    for start in range(0, len(graded_card_ids), 256):
        snapshot["rows"].extend(_graded_rows(db, graded_card_ids[start:start + 256], now))
    return snapshot


def _graded_rows(db: Session, card_ids: list[str], now: datetime) -> list[list]:
    rows = []
    cards_and_sets = db.execute(
        select(Card, Set)
        .join(Set, Card.set_id == Set.id)
        .where(Card.id.in_(card_ids))
    ).all()

    # The latest row per category suffices for raw, PPT medians and "other" (kept for
    # the most-recent-observation timestamp). eBay PSA rows are single asking listings,
    # so up to MAX_LISTINGS recent ones are kept and reduced to a robust median below.
    category = case(
        (PriceObservation.grading_company.is_(None), "raw"),
        (and_(func.upper(PriceObservation.grading_company) == "PSA", PriceObservation.grade == 9), "psa9"),
        (and_(func.upper(PriceObservation.grading_company) == "PSA", PriceObservation.grade == 10), "psa10"),
        else_="other",
    )
    ranked = (
        select(
            PriceObservation.id,
            func.row_number().over(
                partition_by=(PriceObservation.card_id, category),
                order_by=(PriceObservation.observed_at.desc(), PriceObservation.id.desc()),
            ).label("position"),
            category.label("category"),
            PriceObservation.provider.ilike("%ebay%").label("is_ebay"),
            PriceObservation.observed_at,
        )
        .where(PriceObservation.card_id.in_([card.id for card, _ in cards_and_sets]), grading_observation())
        .subquery()
    )
    asking_since = now - timedelta(days=asking_prices.WINDOW_DAYS)
    all_obs = db.scalars(
        select(PriceObservation)
        .join(ranked, ranked.c.id == PriceObservation.id)
        .where(or_(and_(ranked.c.position == 1, ~and_(
            ranked.c.is_ebay, ranked.c.category.in_(("psa9", "psa10")))), and_(
            ranked.c.is_ebay, ranked.c.category.in_(("psa9", "psa10")),
            ranked.c.position <= asking_prices.MAX_LISTINGS, ranked.c.observed_at >= asking_since)))
        .options(load_only(
            PriceObservation.card_id, PriceObservation.price,
            PriceObservation.grading_company, PriceObservation.grade,
            PriceObservation.observed_at, PriceObservation.provider,
        ))
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    ).all()

    obs_by_card: dict[str, list[PriceObservation]] = {}
    for o in all_obs:
        obs_by_card.setdefault(o.card_id, []).append(o)

    for card, cset in cards_and_sets:
        c_obs = obs_by_card.get(card.id, [])
        if not c_obs:
            continue

        raw_price: float | None = None
        latest_obs_time: datetime | None = c_obs[0].observed_at
        graded: dict[float, list[PriceObservation]] = {10.0: [], 9.0: []}

        for o in c_obs:
            if o.grading_company is None:
                if raw_price is None:
                    try:
                        raw_price = float(o.price)
                    except (ValueError, TypeError) as exc:
                        logger.debug("Failed parsing raw price for card %s: %s", card.id, exc)
                continue
            if o.grading_company.upper() == "PSA" and o.grade is not None and float(o.grade) in graded:
                graded[float(o.grade)].append(o)

        def graded_price(rows: list[PriceObservation], grade: float) -> float | None:
            if not rows:
                return None
            try:
                # Rows are newest first. A PPT median stands on its own; eBay asks are pooled.
                if "ebay" not in (rows[0].provider or "").lower():
                    return float(rows[0].price)
                asks = [float(o.price) for o in rows if "ebay" in (o.provider or "").lower()]
                return asking_prices.robust_asking_price(asks, reference=raw_price)
            except (ValueError, TypeError) as exc:
                logger.debug("Failed parsing PSA %s price for card %s: %s", grade, card.id, exc)
                return None

        psa10_price = graded_price(graded[10.0], 10)
        psa9_price = graded_price(graded[9.0], 9)

        if raw_price is None or raw_price <= 0:
            continue
        if psa10_price is None and psa9_price is None:
            continue

        ppt_graded = any(o.provider == "pokemonpricetracker" and o.grading_company for o in c_obs)
        updated = latest_obs_time or card.updated_at
        rows.append([
            card.id, card.name, card.set_id, cset.name, card.number, card.rarity, raw_price, psa10_price, psa9_price,
            "pokemonpricetracker" if ppt_graded else "ebay", "median_7d" if ppt_graded else "asking_listing",
            updated.isoformat() if updated else None,
        ])
    return rows


def select_grading_profit(
    snapshot: dict,
    *,
    grading_fee: float | None = None,
    sort_by: str = "psa10_profit_desc",
    target_grade: str = "all",
    min_profit: float | None = None,
    max_raw_price: float | None = None,
    min_spread: float | None = None,
    psa9_safe_only: bool = False,
    set_id: str | None = None,
    q: str = "",
    page: int = 1,
    per_page: int = 24,
) -> GradingProfitResponse:
    """Apply the fee, filters, sort and page to the snapshot's per-card prices."""
    active_fee = grading_fee if grading_fee is not None else get_settings().psa_value_fee
    fee = float(active_fee)
    query_str = q.strip().lower()
    items: list[GradingProfitItem] = []
    for values in snapshot["rows"]:
        row = dict(zip(snapshot["fields"], values))
        if set_id and row["set_id"] != set_id:
            continue
        if query_str and query_str not in row["name"].lower() and query_str not in row["set_name"].lower():
            continue
        raw_price, psa10_price, psa9_price = row["raw_price"], row["psa10_price"], row["psa9_price"]
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
        # An unavailable outcome is not a break-even outcome.
        expected_value = (
            round((0.60 * psa10_profit) + (0.35 * psa9_profit), 2)
            if psa10_profit is not None and psa9_profit is not None else None
        )

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
                card_id=row["card_id"],
                name=row["name"],
                set_id=row["set_id"],
                set_name=row["set_name"],
                number=row["number"],
                rarity=row["rarity"],
                image_url="",
                graded_source=row["graded_source"],
                graded_metric=row["graded_metric"],
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
                last_updated_at=row["last_updated_at"],
            )
        )

    # Sorting
    if sort_by == "psa10_roi_desc":
        items.sort(key=lambda x: (x.psa10_roi is not None, x.psa10_roi if x.psa10_roi is not None else 0.0), reverse=True)
    elif sort_by == "psa9_profit_desc":
        items.sort(key=lambda x: (x.psa9_profit is not None, x.psa9_profit if x.psa9_profit is not None else 0.0), reverse=True)
    elif sort_by == "psa9_roi_desc":
        items.sort(key=lambda x: (x.psa9_roi is not None, x.psa9_roi if x.psa9_roi is not None else 0.0), reverse=True)
    elif sort_by == "ev_desc":
        items.sort(key=lambda x: (x.expected_value is not None, x.expected_value if x.expected_value is not None else 0.0), reverse=True)
    elif sort_by == "spread_desc":
        items.sort(key=lambda x: (x.spread_multiplier is not None, x.spread_multiplier if x.spread_multiplier is not None else 0.0), reverse=True)
    elif sort_by == "raw_price_asc":
        items.sort(key=lambda x: x.raw_price)
    elif sort_by == "raw_price_desc":
        items.sort(key=lambda x: x.raw_price, reverse=True)
    else:  # default "psa10_profit_desc"
        items.sort(key=lambda x: (x.psa10_profit is not None, x.psa10_profit if x.psa10_profit is not None else 0.0), reverse=True)

    total_cards = len(items)
    total_pages = max(1, math.ceil(total_cards / per_page))
    start_idx = (page - 1) * per_page
    # The worker does not mount the image manifest; resolve image URLs for this page only.
    paged_items = [item.model_copy(update={"image_url": card_image_url(item.card_id)})
                   for item in items[start_idx:start_idx + per_page]]

    return GradingProfitResponse(
        page=page,
        per_page=per_page,
        total_cards=total_cards,
        total_pages=total_pages,
        grading_fee=round(fee, 2),
        sort_by=sort_by,
        items=paged_items,
        updated_at=datetime.fromisoformat(snapshot["updated_at"]),
    )


def _snapshot_now(db: Session) -> dict:
    # A JSON round trip gives exactly the shape the worker publishes.
    return json.loads(json.dumps(build_snapshot(db, datetime.now(UTC))))


def refresh_snapshot(*, force=False) -> bool:
    return market_snapshots.refresh(SNAPSHOT_NAME, ["all"], lambda db, now: {"all": json.dumps(build_snapshot(db, now))},
                                    force=force)


def stored_grading_profit(db: Session, **filters) -> GradingProfitResponse:
    """Serve the worker snapshot; compute on request only when Redis is unreachable."""
    snapshot = market_snapshots.read(SNAPSHOT_NAME)
    if snapshot is None:
        snapshot = _snapshot_now(market_snapshots.on_demand_session(db))
    return select_grading_profit(snapshot, **filters)


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
    use_cache: bool = True,
) -> GradingProfitResponse:
    """Calculate potential grading profit and ROI metrics across raw and graded comps on demand."""
    now = time.time()
    cache_key_raw = (
        f"{grading_fee}:{sort_by}:{target_grade}:{min_profit}:{max_raw_price}:"
        f"{min_spread}:{psa9_safe_only}:{set_id}:{q.strip().lower()}:{page}:{per_page}"
    )
    cache_hash = hashlib.md5(cache_key_raw.encode()).hexdigest()
    source_key = "ppt" if get_settings().ppt_primary_enabled else "legacy"
    redis_key = f"cardboarddex:{source_key}:grading_profit:identity-v3:{cache_hash}"
    redis_key = f"{image_generation()}:{redis_key}"

    # 1. Try Redis cache first
    r = get_redis() if use_cache else None
    if r is not None:
        try:
            cached_data = r.get(redis_key)
            if cached_data:
                return GradingProfitResponse.model_validate_json(cached_data)
        except (RedisError, Exception) as exc:
            logger.warning("Redis grading profit cache read failed error=%s: %s", type(exc).__name__, exc)

    # 2. Try in-process fallback
    local_cached = _GRADING_PROFIT_LOCAL_FALLBACK.get(redis_key)
    if use_cache and local_cached and (now - local_cached[0]) < _GRADING_CACHE_TTL:
        return local_cached[1]

    response = select_grading_profit(
        _snapshot_now(db), grading_fee=grading_fee, sort_by=sort_by, target_grade=target_grade,
        min_profit=min_profit, max_raw_price=max_raw_price, min_spread=min_spread,
        psa9_safe_only=psa9_safe_only, set_id=set_id, q=q, page=page, per_page=per_page,
    )

    if r is not None:
        try:
            r.setex(redis_key, _GRADING_CACHE_TTL, response.model_dump_json())
        except (RedisError, Exception) as exc:
            logger.warning("Redis grading profit cache write failed error=%s: %s", type(exc).__name__, exc)

    if use_cache:
        _GRADING_PROFIT_LOCAL_FALLBACK[redis_key] = (now, response)
    return response
