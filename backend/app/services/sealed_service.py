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
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.common.formatters import escape_like, extract_float
from app.common.redis import get_redis
from app.models import Card, PriceObservation, ProviderCardState, MarketHistory, Set
from app.services.market_data_service import freshness, historical_returns, summarize_history
from app.schemas.cards import SealedSignalItem, SealedSignalsResponse

logger = logging.getLogger(__name__)

_SEALED_SIGNALS_LOCAL_FALLBACK = TTLCache(max_entries=64, ttl=300)
_SEALED_CACHE_TTL = 300  # 5 minutes


def classify_sealed_product(name: str) -> tuple[str, str]:
    """
    Classify sealed products by name pattern.
    Returns (display_type, category_slug)
    """
    lower = name.lower()
    if "case" in lower:
        return "Case", "case"
    if "booster box" in lower:
        return "Booster Box", "booster_box"
    if "elite trainer box" in lower or "etb" in lower or "pokemon center elite" in lower:
        return "Elite Trainer Box", "etb"
    if "booster bundle" in lower:
        return "Booster Bundle", "bundle"
    if "blister" in lower:
        return "Blister Pack", "blister"
    if "sleeved booster" in lower or "booster pack" in lower or "art bundle" in lower:
        return "Booster Pack", "pack"
    if "tin" in lower or "collection" in lower or "box" in lower or "stadium" in lower or "chest" in lower:
        return "Collection Box", "collection"
    return "Sealed Product", "all"


def calculate_sealed_signals(
    db: Session,
    *,
    signal: Literal["all", "strong_buy", "buy", "hold", "underperform"] = "all",
    product_type: Literal[
        "all",
        "booster_box",
        "etb",
        "bundle",
        "case",
        "pack",
        "blister",
        "collection",
    ] = "all",
    sort_by: Literal[
        "score_desc",
        "supply_asc",
        "momentum_desc",
        "price_desc",
        "price_asc",
        "age_desc",
    ] = "score_desc",
    set_id: str | None = None,
    q: str = "",
    era: Literal["all", "newer", "older"] = "all",
    game: Literal["all", "pokemon", "pokemon-japan"] = "all",
    period: Literal[30, 90] = 30,
    page: int = 1,
    per_page: int = 24,
) -> SealedSignalsResponse:
    """Calculate multi-factor sealed market investment signals and scores."""
    now = time.time()
    cache_key_raw = f"v4:{game}:{period}:{era}:{signal}:{product_type}:{sort_by}:{set_id}:{q.strip().lower()}:{page}:{per_page}"
    cache_hash = hashlib.md5(cache_key_raw.encode()).hexdigest()
    redis_key = f"cardboarddex:sealed_signals:{cache_hash}"
    redis_key = f"{image_generation()}:{redis_key}"

    # 1. Try Redis cache first
    r = get_redis()
    if r is not None:
        try:
            cached_data = r.get(redis_key)
            if cached_data:
                return SealedSignalsResponse.model_validate_json(cached_data)
        except (RedisError, Exception) as exc:
            logger.warning("Redis sealed signals cache read failed error=%s: %s", type(exc).__name__, exc)

    # 2. Try in-process fallback
    local_cached = _SEALED_SIGNALS_LOCAL_FALLBACK.get(redis_key)
    if local_cached and (now - local_cached[0]) < _SEALED_CACHE_TTL:
        return local_cached[1]

    # Explicit provider metadata takes precedence over the legacy rarity fallback.
    explicit_type = func.coalesce(
        ProviderCardState.payload["card"]["product_type"].as_string(),
        ProviderCardState.payload["card"]["data"]["product_type"].as_string(),
    )
    query = (
        select(Card, Set)
        .join(Set, Card.set_id == Set.id)
        .outerjoin(ProviderCardState, and_(ProviderCardState.card_id == Card.id, ProviderCardState.provider == "tcgapi"))
        .where(
            or_(explicit_type == "Sealed Products", and_(explicit_type.is_(None), or_(Card.rarity.is_(None), Card.rarity == ""))),
            Card.name.not_ilike("%code card%"),
        )
    )

    # Match the catalog's language marker, including legacy English sets without a series.
    if game == "pokemon-japan":
        query = query.where(Set.series == "Pokemon Japan")
    elif game == "pokemon":
        query = query.where(or_(Set.series.is_(None), Set.series != "Pokemon Japan"))

    today = datetime.now(UTC).date()
    # Calendar years, with Feb 29 clamped to Feb 28 in the cutoff year.
    cutoff = today.replace(year=today.year - 3, day=28 if today.month == 2 and today.day == 29 else today.day)
    if era == "newer":
        query = query.where(Set.release_date > cutoff, Set.release_date <= today)
    elif era == "older":
        query = query.where(Set.release_date <= cutoff)

    if set_id:
        query = query.where(Card.set_id == set_id)
    query_str = q.strip().lower()
    if query_str:
        pattern = f"%{escape_like(query_str)}%"
        query = query.where(
            or_(Card.name.ilike(pattern, escape="\\"), Set.name.ilike(pattern, escape="\\"))
        )

    sealed_rows = db.execute(query).all()
    if not sealed_rows:
        return SealedSignalsResponse(
            page=page,
            per_page=per_page,
            total_items=0,
            total_pages=1,
            signal_filter=signal,
            product_type_filter=product_type,
            sort_by=sort_by,
            strong_buy_count=0,
            buy_count=0,
            hold_count=0,
            underperform_count=0,
            items=[],
            updated_at=datetime.now(UTC),
        )

    card_ids = [c.id for c, _ in sealed_rows]
    # Only materialize the latest payload for each product, not its full history.
    ranked = (
        select(
            PriceObservation.id,
            func.row_number().over(
                partition_by=PriceObservation.card_id,
                order_by=(PriceObservation.observed_at.desc(), PriceObservation.id.desc()),
            ).label("position"),
        )
        .where(PriceObservation.card_id.in_(card_ids), PriceObservation.provider == "tcgapi")
        .subquery()
    )
    obs_list = db.scalars(
        select(PriceObservation)
        .join(ranked, ranked.c.id == PriceObservation.id)
        .where(ranked.c.position == 1)
    ).all()
    obs_map: dict[str, PriceObservation] = {o.card_id: o for o in obs_list}

    returns = historical_returns(db, card_ids, period)
    today = datetime.now(UTC).date()
    all_scored_items: list[tuple[SealedSignalItem, str]] = []
    strong_buy_count = 0
    buy_count = 0
    hold_count = 0
    underperform_count = 0

    for card, cset in sealed_rows:
        obs = obs_map.get(card.id)
        p = obs.payload if obs and isinstance(obs.payload, dict) else {}
        market_price = extract_float(p, "market_price")
        if market_price is None and obs:
            try:
                market_price = float(obs.price)
            except (ValueError, TypeError) as exc:
                logger.debug("Failed parsing obs price for sealed card %s: %s", card.id, exc)
                market_price = None

        if market_price is None or market_price <= 0:
            continue

        clean_name = str(p.get("clean_name") or card.name.lower())
        disp_type, cat_slug = classify_sealed_product(card.name)

        total_listings = int(p.get("total_listings") or 0)
        low_price = extract_float(p, "low_price")
        median_price = extract_float(p, "median_price")
        lowest_with_shipping = extract_float(p, "lowest_with_shipping")
        buylist_price = extract_float(p, "buylist_price")

        # 1. Supply Scarcity Score (0-30 pts)
        if total_listings > 0:
            if total_listings < 15:
                supply_score = 30
                supply_rating = "Ultra Scarce"
            elif total_listings < 40:
                supply_score = 22
                supply_rating = "Low Float"
            elif total_listings < 80:
                supply_score = 14
                supply_rating = "Moderate"
            elif total_listings < 150:
                supply_score = 8
                supply_rating = "Moderate"
            else:
                supply_score = 4
                supply_rating = "High Supply"
        else:
            supply_score = 15
            supply_rating = "Moderate"

        # 2. Set Vintage & Out-of-Print Age (0-20 pts)
        set_age_months = 0
        if cset.release_date:
            delta_days = (today - cset.release_date).days
            set_age_months = max(0, delta_days // 30)
            if set_age_months >= 36:
                vintage_score = 20
            elif set_age_months >= 24:
                vintage_score = 16
            elif set_age_months >= 12:
                vintage_score = 12
            elif set_age_months >= 6:
                vintage_score = 8
            else:
                vintage_score = 4
        else:
            vintage_score = 10

        # 3. Demand & Liquidity (0-25 pts)
        if buylist_price and market_price > 0:
            b_ratio = buylist_price / market_price
            if b_ratio >= 0.80:
                demand_score = 25
            elif b_ratio >= 0.65:
                demand_score = 18
            elif b_ratio >= 0.50:
                demand_score = 12
            else:
                demand_score = 6
        else:
            spread = (
                ((median_price - low_price) / median_price)
                if (median_price and low_price and median_price > 0)
                else 0.20
            )
            if spread < 0.10:
                demand_score = 18
            elif spread < 0.25:
                demand_score = 12
            else:
                demand_score = 8

        # 4. Price Momentum (0-25 pts)
        p30 = extract_float(p, "price_change_30d") or 0.0
        p7 = extract_float(p, "price_change_7d") or 0.0
        p24 = extract_float(p, "price_change_24h") or 0.0

        momentum_pct = p30 if p30 != 0 else (p7 * 4.0 if p7 != 0 else p24 * 30.0)
        if momentum_pct >= 15.0:
            momentum_score = 25
        elif momentum_pct >= 5.0:
            momentum_score = 18
        elif momentum_pct >= 0.0:
            momentum_score = 14
        elif momentum_pct >= -10.0:
            momentum_score = 8
        else:
            momentum_score = 4

        total_score = min(100, supply_score + vintage_score + demand_score + momentum_score)
        if total_score >= 75:
            signal_label = "STRONG BUY"
            strong_buy_count += 1
        elif total_score >= 60:
            signal_label = "BUY"
            buy_count += 1
        elif total_score >= 45:
            signal_label = "HOLD"
            hold_count += 1
        else:
            signal_label = "UNDERPERFORM"
            underperform_count += 1

        item = SealedSignalItem(
            card_id=card.id,
            name=card.name,
            clean_name=clean_name,
            set_id=card.set_id,
            set_name=cset.name,
            series=cset.series,
            release_date=cset.release_date,
            image_url=card_image_url(card.id),
            product_type=disp_type,
            market_price=round(market_price, 2),
            **freshness(p),
            checked_at=obs.provider_updated_at if obs else None,
            return_days=period,
            return_percent=returns.get((card.id, "Normal" if obs.printing in (None, "Standard") else obs.printing)) if obs else None,

            low_price=round(low_price, 2) if low_price is not None else None,
            median_price=round(median_price, 2) if median_price is not None else None,
            lowest_with_shipping=round(lowest_with_shipping, 2) if lowest_with_shipping is not None else None,
            buylist_price=round(buylist_price, 2) if buylist_price is not None else None,
            total_listings=total_listings,
            supply_rating=supply_rating,
            set_age_months=set_age_months,
            price_change_24h=extract_float(p, "price_change_24h"),
            price_change_7d=extract_float(p, "price_change_7d"),
            price_change_30d=extract_float(p, "price_change_30d"),
            supply_score=supply_score,
            demand_score=demand_score,
            momentum_score=momentum_score,
            vintage_score=vintage_score,
            signal_score=total_score,
            signal_label=signal_label,
            last_updated_at=obs.observed_at if obs else card.updated_at,
        )
        if item.return_percent is None and period == 30:
            item.return_percent = item.price_change_30d
        all_scored_items.append((item, cat_slug))

    # Filter items
    filtered_items: list[SealedSignalItem] = []
    for item, cat_slug in all_scored_items:
        # Signal filter
        if signal == "strong_buy" and item.signal_label != "STRONG BUY":
            continue
        if signal == "buy" and item.signal_label != "BUY":
            continue
        if signal == "hold" and item.signal_label != "HOLD":
            continue
        if signal == "underperform" and item.signal_label != "UNDERPERFORM":
            continue

        # Product type filter
        if product_type != "all" and cat_slug != product_type:
            continue

        filtered_items.append(item)

    # Sorting
    if sort_by == "supply_asc":
        filtered_items.sort(key=lambda x: (x.total_listings == 0, x.total_listings, -x.signal_score))
    elif sort_by == "momentum_desc":
        # Unknown returns follow negative returns; zero is a valid observation.
        filtered_items.sort(key=lambda x: (
            x.return_percent is None,
            -(x.return_percent if x.return_percent is not None else 0),
            x.card_id,
        ))
    elif sort_by == "price_desc":
        filtered_items.sort(key=lambda x: x.market_price, reverse=True)
    elif sort_by == "price_asc":
        filtered_items.sort(key=lambda x: x.market_price)
    elif sort_by == "age_desc":
        filtered_items.sort(key=lambda x: x.set_age_months, reverse=True)
    else:  # default "score_desc"
        filtered_items.sort(key=lambda x: (x.signal_score, -x.total_listings), reverse=True)

    total_items = len(filtered_items)
    total_pages = max(1, math.ceil(total_items / per_page))
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_items = filtered_items[start_idx:end_idx]

    selected_printings = {item.card_id: (obs_map[item.card_id].printing or "Normal") for item in paged_items if item.card_id in obs_map}
    selected_printings = {cid: "Normal" if printing == "Standard" else printing for cid, printing in selected_printings.items()}
    history_by_card = {}
    if selected_printings:
        history_rows = db.scalars(select(MarketHistory).where(
            tuple_(MarketHistory.card_id, MarketHistory.printing).in_(list(selected_printings.items())),
            MarketHistory.day >= today - timedelta(days=period + 7), MarketHistory.day <= today,
        ).order_by(MarketHistory.day))
        for row in history_rows:
            history_by_card.setdefault(row.card_id, []).append(row)
    for item in paged_items:
        item.history = summarize_history(history_by_card.get(item.card_id, []), item.card_id, period,
                                         selected_printings.get(item.card_id, "Normal"), today=today)

    response = SealedSignalsResponse(
        page=page,
        per_page=per_page,
        total_items=total_items,
        total_pages=total_pages,
        signal_filter=signal,
        product_type_filter=product_type,
        sort_by=sort_by,
        strong_buy_count=strong_buy_count,
        buy_count=buy_count,
        hold_count=hold_count,
        underperform_count=underperform_count,
        items=paged_items,
        updated_at=datetime.now(UTC),
    )

    if r is not None:
        try:
            r.setex(redis_key, _SEALED_CACHE_TTL, response.model_dump_json())
        except (RedisError, Exception) as exc:
            logger.warning("Redis sealed signals cache write failed error=%s: %s", type(exc).__name__, exc)

    _SEALED_SIGNALS_LOCAL_FALLBACK[redis_key] = (now, response)
    return response
