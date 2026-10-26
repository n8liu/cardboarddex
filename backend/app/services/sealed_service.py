from app.config import get_settings
from app.services.price_sources import market_observation
from app.services.image_delivery import card_image_url, image_generation
from app.common.cache import TTLCache
import hashlib
import json
import logging
import math
import time
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi.encoders import jsonable_encoder
from redis.exceptions import RedisError
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import Session

from app.common.formatters import extract_float
from app.common.redis import get_redis
from app.models import Card, PriceObservation, ProviderCardState, MarketHistory, Set
from app.services import market_snapshots
from app.services.market_data_service import freshness, historical_returns, summarize_history, estimated_price_change
from app.schemas.cards import SealedSignalItem, SealedSignalsResponse

logger = logging.getLogger(__name__)

_SEALED_SIGNALS_LOCAL_FALLBACK = TTLCache(max_entries=64, ttl=300)
_SEALED_CACHE_TTL = 300  # 5 minutes
SNAPSHOT_NAME = "sealed-evidence-v2"
PERIODS = (30, 90)


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


def build_snapshot(db: Session, now: datetime) -> dict:
    """Score every sealed product once. Filters, sorting, pages and history happen per request."""
    from app.services.product_metadata import sealed_product
    query = (
        select(Card, Set)
        .join(Set, Card.set_id == Set.id)
        .outerjoin(ProviderCardState, and_(ProviderCardState.card_id == Card.id, ProviderCardState.provider == "tcgapi"))
        .where(
            sealed_product(),
            Card.name.not_ilike("%code card%"),
        )
    )
    sealed_rows = db.execute(query).all()
    snapshot = {"updated_at": now.isoformat(), "items": [], "returns": {str(p): {} for p in PERIODS},
                "printings": {}, "ppt_card_ids": []}
    if not sealed_rows:
        return snapshot

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
        .where(PriceObservation.card_id.in_(card_ids), market_observation())
        .subquery()
    )
    obs_list = db.scalars(
        select(PriceObservation)
        .join(ranked, ranked.c.id == PriceObservation.id)
        .where(ranked.c.position == 1)
    ).all()
    obs_map: dict[str, PriceObservation] = {o.card_id: o for o in obs_list}

    returns_by_period = {period: historical_returns(db, card_ids, period) for period in PERIODS}
    from app.services.ppt_prices import primary_quotes
    ppt_quotes = primary_quotes(db, card_ids)
    today = now.date()

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
        disp_type, _ = classify_sealed_product(card.name)

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
            supply_score = None
            supply_rating = "Unavailable"

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
            vintage_score = None

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
        elif median_price is not None and low_price is not None and median_price > 0:
            spread = (median_price - low_price) / median_price
            if spread < 0.10:
                demand_score = 18
            elif spread < 0.25:
                demand_score = 12
            else:
                demand_score = 8
        else:
            demand_score = None

        # 4. Price Momentum (0-25 pts)
        # Use the reported monthly return, including zero. Shorter periods
        # cannot establish a missing monthly return through extrapolation.
        momentum_pct = extract_float(p, "price_change_30d")
        if momentum_pct is None:
            momentum_score = None
        elif momentum_pct >= 15.0:
            momentum_score = 25
        elif momentum_pct >= 5.0:
            momentum_score = 18
        elif momentum_pct >= 0.0:
            momentum_score = 14
        elif momentum_pct >= -10.0:
            momentum_score = 8
        else:
            momentum_score = 4

        components = (supply_score, vintage_score, demand_score, momentum_score)
        total_score = min(100, sum(components)) if all(score is not None for score in components) else None
        if total_score is None:
            signal_label = "INSUFFICIENT DATA"
        elif total_score >= 75:
            signal_label = "STRONG BUY"
        elif total_score >= 60:
            signal_label = "BUY"
        elif total_score >= 45:
            signal_label = "HOLD"
        else:
            signal_label = "UNDERPERFORM"

        item = SealedSignalItem(
            card_id=card.id,
            name=card.name,
            clean_name=clean_name,
            set_id=card.set_id,
            set_name=cset.name,
            series=cset.series,
            release_date=cset.release_date,
            image_url="",
            product_type=disp_type,
            market_source=obs.provider if obs else None,
            market_price=round(market_price, 2),
            **freshness(p),
            checked_at=obs.provider_updated_at if obs else None,
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
        snapshot["items"].append(item.model_dump(mode="json", exclude={"history", "return_percent", "return_days"}))
        printing = "Normal" if not obs or obs.printing in (None, "Standard") else obs.printing
        for period in PERIODS:
            value = (ppt_quotes[card.id].get(f"price_change_{period}d") if card.id in ppt_quotes
                     else returns_by_period[period].get((card.id, printing)) if obs else None)
            if value is None and period == 30:
                value = item.price_change_30d
            snapshot["returns"][str(period)][card.id] = value
        if obs:
            snapshot["printings"][card.id] = printing
        if card.id in ppt_quotes:
            snapshot["ppt_card_ids"].append(card.id)
    return snapshot


def _history_key(card_id: str, period: int, printing: str) -> str:
    return market_snapshots.part_key(SNAPSHOT_NAME, f"history:{card_id}:{period}:{printing}")


def _page_history(db: Session, items: list[SealedSignalItem], period: int, snapshot: dict, today: date) -> None:
    """Sparkline history for one page only, cached per product for the snapshot interval."""
    printings = {item.card_id: snapshot["printings"][item.card_id] for item in items if item.card_id in snapshot["printings"]}
    ppt_ids = set(snapshot["ppt_card_ids"])
    redis = market_snapshots.get_redis()
    keys = {cid: _history_key(cid, period, printing) for cid, printing in printings.items()}
    cached = {}
    if redis is not None and keys:
        try:
            cached = {cid: json.loads(raw) for cid, raw in zip(keys, redis.mget(list(keys.values()))) if raw}
        except Exception as exc:
            logger.warning("Sealed history cache read failed error=%s: %s", type(exc).__name__, exc)
    missing = {cid: printing for cid, printing in printings.items() if cid not in cached}
    history_by_card = {}
    if missing:
        history_rows = db.scalars(select(MarketHistory).where(
            tuple_(MarketHistory.card_id, MarketHistory.printing).in_(list(missing.items())),
            MarketHistory.day >= today - timedelta(days=period + 7), MarketHistory.day <= today,
        ).order_by(MarketHistory.day))
        for row in history_rows:
            history_by_card.setdefault(row.card_id, []).append(row)
    from app.services.ppt_prices import market_history as ppt_market_history
    for item in items:
        if item.card_id in cached:
            item.history = cached[item.card_id]
        else:
            item.history = summarize_history(history_by_card.get(item.card_id, []), item.card_id, period,
                                             printings.get(item.card_id, "Normal"), today=today)
            if item.card_id in ppt_ids:
                item.history = ppt_market_history(db, item.card_id, period) or item.history
            item.history = jsonable_encoder(item.history)
            if redis is not None and item.card_id in keys:
                try:
                    redis.setex(keys[item.card_id], market_snapshots.REFRESH_SECONDS, json.dumps(item.history))
                except Exception as exc:
                    logger.warning("Sealed history cache write failed error=%s: %s", type(exc).__name__, exc)
        comparison = item.history if item.history["complete_return_window"] else estimated_price_change(item.market_price, item.return_percent)
        for field in ("previous_price", "comparison_price", "price_change_amount", "comparison_source"):
            setattr(item, field, comparison.get(field))


def select_sealed_signals(
    db: Session,
    snapshot: dict,
    *,
    signal: str = "all",
    product_type: str = "all",
    sort_by: str = "score_desc",
    set_id: str | None = None,
    q: str = "",
    era: str = "all",
    game: str = "all",
    period: int = 30,
    page: int = 1,
    per_page: int = 24,
) -> SealedSignalsResponse:
    """Filter, count, sort and page the scored products, then add history for that page."""
    today = datetime.now(UTC).date()
    # Calendar years, with Feb 29 clamped to Feb 28 in the cutoff year.
    cutoff = today.replace(year=today.year - 3, day=28 if today.month == 2 and today.day == 29 else today.day)
    query_str = q.strip().lower()
    returns = snapshot["returns"][str(period)]
    rows = []
    for row in snapshot["items"]:
        # Match the catalog's language marker, including legacy English sets without a series.
        japanese = row["series"] == "Pokemon Japan"
        if (game == "pokemon-japan" and not japanese) or (game == "pokemon" and japanese):
            continue
        released = date.fromisoformat(row["release_date"]) if row["release_date"] else None
        if era == "newer" and not (released and cutoff < released <= today):
            continue
        if era == "older" and not (released and released <= cutoff):
            continue
        if set_id and row["set_id"] != set_id:
            continue
        if query_str and query_str not in row["name"].lower() and query_str not in row["set_name"].lower():
            continue
        rows.append(row)

    counts = {label: sum(row["signal_label"] == label for row in rows)
              for label in ("STRONG BUY", "BUY", "HOLD", "UNDERPERFORM")}
    labels = {"strong_buy": "STRONG BUY", "buy": "BUY", "hold": "HOLD", "underperform": "UNDERPERFORM"}
    filtered = [row for row in rows
                if (signal == "all" or row["signal_label"] == labels[signal])
                and (product_type == "all" or classify_sealed_product(row["name"])[1] == product_type)]

    # Sorting
    if sort_by == "supply_asc":
        filtered.sort(key=lambda x: (x["total_listings"] == 0, x["total_listings"], -(x["signal_score"] if x["signal_score"] is not None else -1)))
    elif sort_by == "momentum_desc":
        # Unknown returns follow negative returns; zero is a valid observation.
        filtered.sort(key=lambda x: (
            returns.get(x["card_id"]) is None,
            -(returns.get(x["card_id"]) or 0),
            x["card_id"],
        ))
    elif sort_by == "price_desc":
        filtered.sort(key=lambda x: x["market_price"], reverse=True)
    elif sort_by == "price_asc":
        filtered.sort(key=lambda x: x["market_price"])
    elif sort_by == "age_desc":
        filtered.sort(key=lambda x: x["set_age_months"], reverse=True)
    else:  # default "score_desc"
        filtered.sort(key=lambda x: (x["signal_score"] is not None, x["signal_score"] if x["signal_score"] is not None else 0, -x["total_listings"]), reverse=True)

    total_items = len(filtered)
    total_pages = max(1, math.ceil(total_items / per_page))
    start_idx = (page - 1) * per_page
    paged_items = [SealedSignalItem.model_validate({
        **row, "image_url": card_image_url(row["card_id"]), "return_days": period,
        "return_percent": returns.get(row["card_id"]),
    }) for row in filtered[start_idx:start_idx + per_page]]
    _page_history(db, paged_items, period, snapshot, today)

    return SealedSignalsResponse(
        page=page,
        per_page=per_page,
        total_items=total_items,
        total_pages=total_pages,
        signal_filter=signal,
        product_type_filter=product_type,
        sort_by=sort_by,
        strong_buy_count=counts["STRONG BUY"],
        buy_count=counts["BUY"],
        hold_count=counts["HOLD"],
        underperform_count=counts["UNDERPERFORM"],
        items=paged_items,
        updated_at=datetime.fromisoformat(snapshot["updated_at"]),
    )


def _snapshot_now(db: Session) -> dict:
    # A JSON round trip gives exactly the shape the worker publishes.
    return json.loads(json.dumps(build_snapshot(db, datetime.now(UTC))))


def refresh_snapshot(*, force=False) -> bool:
    return market_snapshots.refresh(SNAPSHOT_NAME, ["all"], lambda db, now: {"all": json.dumps(build_snapshot(db, now))},
                                    force=force)


def stored_sealed_signals(db: Session, **filters) -> SealedSignalsResponse:
    """Serve the worker snapshot; compute on request only when Redis is unreachable."""
    snapshot = market_snapshots.read(SNAPSHOT_NAME)
    if snapshot is None:
        db = market_snapshots.on_demand_session(db)
        snapshot = _snapshot_now(db)
    return select_sealed_signals(db, snapshot, **filters)


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
    use_cache: bool = True,
) -> SealedSignalsResponse:
    """Calculate multi-factor sealed market investment signals and scores on demand."""
    now = time.time()
    cache_key_raw = f"v7:{game}:{period}:{era}:{signal}:{product_type}:{sort_by}:{set_id}:{q.strip().lower()}:{page}:{per_page}"
    cache_hash = hashlib.md5(cache_key_raw.encode()).hexdigest()
    source_key = "ppt" if get_settings().ppt_primary_enabled else "legacy"
    redis_key = f"cardboarddex:{source_key}:sealed_signals:{cache_hash}"
    redis_key = f"{image_generation()}:{redis_key}"

    # 1. Try Redis cache first
    r = get_redis() if use_cache else None
    if r is not None:
        try:
            cached_data = r.get(redis_key)
            if cached_data:
                return SealedSignalsResponse.model_validate_json(cached_data)
        except (RedisError, Exception) as exc:
            logger.warning("Redis sealed signals cache read failed error=%s: %s", type(exc).__name__, exc)

    # 2. Try in-process fallback
    local_cached = _SEALED_SIGNALS_LOCAL_FALLBACK.get(redis_key)
    if use_cache and local_cached and (now - local_cached[0]) < _SEALED_CACHE_TTL:
        return local_cached[1]

    response = select_sealed_signals(db, _snapshot_now(db), signal=signal, product_type=product_type,
                                     sort_by=sort_by, set_id=set_id, q=q, era=era, game=game, period=period,
                                     page=page, per_page=per_page)

    if r is not None:
        try:
            r.setex(redis_key, _SEALED_CACHE_TTL, response.model_dump_json())
        except (RedisError, Exception) as exc:
            logger.warning("Redis sealed signals cache write failed error=%s: %s", type(exc).__name__, exc)

    if use_cache:
        _SEALED_SIGNALS_LOCAL_FALLBACK[redis_key] = (now, response)
    return response
