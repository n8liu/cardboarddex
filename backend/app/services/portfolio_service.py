from app.services.image_delivery import card_image_url, image_generation
from app.common.cache import TTLCache
import hashlib
import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.redis import get_redis
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.schemas.cards import (
    PortfolioCardItem,
    PortfolioHistoryPoint,
    PortfolioValuationResponse,
)

logger = logging.getLogger(__name__)

_PORTFOLIO_CACHE_TTL = 300  # 5 minutes
_PORTFOLIO_LOCAL_FALLBACK = TTLCache(max_entries=64, ttl=300)


def _extract_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # check NaN
    except (ValueError, TypeError):
        return None


def calculate_portfolio_valuation(
    db: Session,
    card_ids: list[str],
    days: int = 365,
) -> PortfolioValuationResponse:
    """Calculate combined portfolio value, deltas, and historical valuation curve for card IDs."""
    now = datetime.now(UTC)
    now_date = now.date()

    # Deduplicate and normalize card IDs
    clean_ids = sorted({str(cid).strip() for cid in card_ids if str(cid).strip()})
    if not clean_ids:
        return PortfolioValuationResponse(
            total_cards=0,
            total_current_value=0.0,
            currency="USD",
            delta_24h_amount=0.0,
            delta_24h_percent=0.0,
            delta_7d_amount=0.0,
            delta_7d_percent=0.0,
            delta_30d_amount=0.0,
            delta_30d_percent=0.0,
            highest_value_card=None,
            cards=[],
            history=[],
            updated_at=now,
        )

    # Cache lookup
    from app.config import get_settings
    cache_str = f"ppt-migration-v2:{get_settings().ppt_primary_enabled}:{','.join(clean_ids)}:{days}"
    cache_hash = hashlib.md5(cache_str.encode("utf-8")).hexdigest()
    cache_key = f"cardboarddex:portfolio:{cache_hash}"
    cache_key = f"{image_generation()}:{cache_key}"

    try:
        redis_client = get_redis()
        if redis_client:
            cached_bytes = redis_client.get(cache_key)
            if cached_bytes:
                cached_data = json.loads(cached_bytes)
                return PortfolioValuationResponse.model_validate(cached_data)
    except RedisError as err:
        logger.warning(
            "Redis cache error reading portfolio valuation key=%s error_type=%s: %s",
            cache_key,
            type(err).__name__,
            err,
        )
    except Exception as err:
        logger.error(
            "Unexpected error reading portfolio valuation cache key=%s error_type=%s: %s",
            cache_key,
            type(err).__name__,
            err,
        )

    # In-process cache check
    if cache_key in _PORTFOLIO_LOCAL_FALLBACK:
        ts, cached_payload = _PORTFOLIO_LOCAL_FALLBACK[cache_key]
        if now.timestamp() - ts < _PORTFOLIO_CACHE_TTL:
            return PortfolioValuationResponse.model_validate(cached_payload)

    # 1. Fetch matching Cards and Sets
    try:
        cards_with_sets = list(
            db.execute(
                select(Card, Set)
                .join(Set, Card.set_id == Set.id)
                .where(Card.id.in_(clean_ids))
            ).all()
        )
    except Exception as err:
        logger.error(
            "Failed querying cards and sets for portfolio IDs=%s error_type=%s: %s",
            clean_ids,
            type(err).__name__,
            err,
        )
        raise

    card_map = {card.id: (card, card_set) for card, card_set in cards_with_sets}

    # 2. Fetch ProviderCardState for TCG API prices and deltas
    provider_states = list(
        db.scalars(
            select(ProviderCardState).where(
                ProviderCardState.card_id.in_(clean_ids),
                ProviderCardState.provider == "tcgapi",
            )
        ).all()
    )
    state_map: dict[str, dict[str, Any]] = {}
    for state in provider_states:
        if isinstance(state.payload, dict):
            state_map[state.card_id] = state.payload

    # 3. Fetch latest PriceObservation for each card (for fallback price if state payload lacks it)
    latest_obs_query = (
        select(PriceObservation)
        .where(
            PriceObservation.card_id.in_(clean_ids),
            PriceObservation.provider == "tcgapi",
            PriceObservation.grading_company.is_(None),
        )
        .order_by(
            PriceObservation.card_id,
            func.coalesce(PriceObservation.provider_updated_at, PriceObservation.observed_at).desc(),
            PriceObservation.id.desc(),
        )
    )
    latest_observations = list(db.scalars(latest_obs_query).all())
    latest_price_map: dict[str, float] = {}
    for obs in latest_observations:
        if obs.card_id not in latest_price_map and obs.price is not None:
            latest_price_map[obs.card_id] = float(obs.price)

    from app.services.ppt_prices import primary_quotes
    ppt_quotes = primary_quotes(db, clean_ids)

    # 4. Build PortfolioCardItem list
    portfolio_cards: list[PortfolioCardItem] = []
    card_current_prices: dict[str, float] = {}

    for cid in clean_ids:
        if cid not in card_map:
            continue
        card, card_set = card_map[cid]
        state_payload = state_map.get(cid, {})

        # Extract market price and deltas
        market_price: float | None = None
        p_24h: float | None = None
        p_7d: float | None = None
        p_30d: float | None = None

        # Inspect nested prices in payload
        prices_data = state_payload.get("prices")
        if isinstance(prices_data, dict):
            pdata = prices_data.get("data")
            pitem = pdata[0] if isinstance(pdata, list) and pdata else prices_data
            if isinstance(pitem, dict):
                market_price = _extract_float(pitem.get("market_price"))
                p_24h = _extract_float(pitem.get("price_change_24h"))
                p_7d = _extract_float(pitem.get("price_change_7d"))
                p_30d = _extract_float(pitem.get("price_change_30d"))

        # Fallback to latest PriceObservation
        if market_price is None or market_price <= 0:
            market_price = latest_price_map.get(cid)

        if cid in ppt_quotes:
            quote = ppt_quotes[cid]
            market_price = quote["price"]
            p_24h, p_7d, p_30d = (quote.get("price_change_" + period) for period in ("24h", "7d", "30d"))

        if market_price is not None:
            card_current_prices[cid] = market_price

        portfolio_cards.append(
            PortfolioCardItem(
                id=card.id,
                name=card.name,
                set_name=card_set.name,
                number=f"{card.number}/{card.printed_total}" if card.printed_total else card.number,
                rarity=card.rarity,
                image_url=card_image_url(card.id),
                price_status=("stale" if ppt_quotes[cid].get("stale") else "recent") if cid in ppt_quotes else "legacy" if market_price is not None else "unavailable",
                price_date=ppt_quotes[cid]["price_date"] if cid in ppt_quotes else next(((o.provider_updated_at or o.observed_at).date().isoformat() for o in latest_observations if o.card_id == cid), None),
                market_source="pokemonpricetracker" if cid in ppt_quotes else "tcgapi" if market_price is not None else None,
                market_price=round(market_price, 2) if market_price is not None else None,
                market_currency="USD",
                price_change_24h=round(p_24h, 2) if p_24h is not None else None,
                price_change_7d=round(p_7d, 2) if p_7d is not None else None,
                price_change_30d=round(p_30d, 2) if p_30d is not None else None,
            )
        )

    # Sort cards by market price descending
    portfolio_cards.sort(key=lambda c: (c.market_price or 0.0), reverse=True)

    total_current_val = round(sum(card_current_prices.values()), 2)
    highest_card = portfolio_cards[0] if portfolio_cards and portfolio_cards[0].market_price else None

    # Unified source-aware history, with no synthesized observations or today's seed.
    from app.services.ppt_prices import pricing_data
    from app.services.market_history import load_history_inputs
    inputs = load_history_inputs(db, clean_ids, days)
    card_date_prices = {}
    card_date_sources = {}
    for cid in clean_ids:
        data = pricing_data(db, cid, days, stored=inputs[cid])
        quote = ppt_quotes.get(cid)
        series = [s for s in data["market_history_series"] if not s.get("grade") and s["metric"] == "market"]
        if quote:
            printing = 'Normal' if quote["printing"] == 'Standard' else quote["printing"]
            series = [s for s in series if s["printing"] == printing and s["condition"] in (quote["condition"], None, 'Unknown')]
        elif series:
            # Choose one printing by most recent recorded point; never sum printings as separate cards.
            selected = max(series, key=lambda s: max((p['date'] for p in s['points']), default=''))
            series = [selected]
        points = {}
        sources = {}
        for s in sorted(series, key=lambda s: s['provider'] != 'tcgapi'):
            for point in s['points']:
                if point['price'] is not None:
                    points[point['date']] = point['price']
                    sources[point['date']] = point.get('source')
        card_date_prices[cid] = points
        card_date_sources[cid] = sources
    dates = sorted({d for points in card_date_prices.values() for d in points})
    history_points = [PortfolioHistoryPoint(date=d,
        total_value=round(sum(points[d] for points in card_date_prices.values() if d in points), 2),
        card_count=sum(d in points for points in card_date_prices.values())) for d in dates]

    # 6. Calculate Combined Deltas (24h, 7d, 30d)
    # Prefer delta computed from historical points if available
    def _calc_delta(days_back: int) -> tuple[float | None, float | None]:
        previous = 0.0
        for card in portfolio_cards:
            if card.market_price is None:
                continue
            # A stale value is not a current return, and provider backfill cannot
            # supply a hidden baseline across the recorded source cutover.
            if card.price_date != now_date.isoformat() or card.price_status == "stale":
                return None, None
            baseline = (now_date - timedelta(days=days_back)).isoformat()
            price = card_date_prices.get(card.id, {}).get(baseline)
            source = card_date_sources.get(card.id, {}).get(baseline)
            if not price or source != card.market_source:
                return None, None
            previous += price
        if previous > 0:
            return round(total_current_val - previous, 2), round((total_current_val / previous - 1) * 100, 2)
        return None, None

    d24_amt, d24_pct = _calc_delta(1)
    d7_amt, d7_pct = _calc_delta(7)
    d30_amt, d30_pct = _calc_delta(30)

    response = PortfolioValuationResponse(
        total_cards=len(portfolio_cards),
        total_current_value=total_current_val,
        currency="USD",
        delta_24h_amount=d24_amt,
        delta_24h_percent=d24_pct,
        delta_7d_amount=d7_amt,
        delta_7d_percent=d7_pct,
        delta_30d_amount=d30_amt,
        delta_30d_percent=d30_pct,
        highest_value_card=highest_card,
        cards=portfolio_cards,
        history=history_points,
        updated_at=now,
    )

    # 7. Cache Response
    try:
        redis_client = get_redis()
        if redis_client:
            redis_client.setex(cache_key, _PORTFOLIO_CACHE_TTL, response.model_dump_json())
    except RedisError as err:
        logger.warning("Failed writing portfolio cache key=%s error_type=%s: %s", cache_key, type(err).__name__, err)
    except Exception as err:
        logger.error("Unexpected error saving portfolio cache key=%s error_type=%s: %s", cache_key, type(err).__name__, err)

    _PORTFOLIO_LOCAL_FALLBACK[cache_key] = (now.timestamp(), response.model_dump())

    return response
