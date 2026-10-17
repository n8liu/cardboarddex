"""Read cached provider data; public requests never consume provider quota."""
import logging
import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.models import Card, Set, PriceObservation, ProviderCardState, MarketHistory, CatalogSnapshot
from app.tcgapi.client import parse_release_date

logger = logging.getLogger(__name__)


def estimated_price_change(price, percent):
    """Reverse a provider percentage; this is an estimate, not a historical quote."""
    if price is None or percent is None:
        return {}
    if not math.isfinite(price) or not math.isfinite(percent) or price <= 0 or percent <= -100:
        return {}
    previous = price / (1 + percent / 100)
    if not math.isfinite(previous):
        return {}
    return {"previous_price": round(previous, 2), "comparison_price": round(price, 2),
            "price_change_amount": round(price - previous, 2), "comparison_source": "estimated"}


def product_metadata(payload):
    card = (payload or {}).get("card", {})
    if not isinstance(card, dict):
        return {}
    return card.get("data", card) if isinstance(card.get("data", card), dict) else {}


def freshness(payload, today=None):
    today = today or datetime.now(UTC).date()
    as_of = parse_release_date((payload or {}).get("market_price_as_of"))
    if as_of and as_of > today:
        logger.warning("TCG API market price date is in the future date=%s", as_of)
        as_of = None
    return {"market_price_as_of": as_of, "price_age_days": (today - as_of).days if as_of else None,
            "price_freshness": "unknown" if not as_of else "stale" if (today - as_of).days > 7 else "recent"}


def normalize_history(payload, today=None):
    today = today or datetime.now(UTC).date()
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) > 20000:
        logger.error("Invalid history data shape or row count")
        raise ValueError("History data must be a bounded list")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            logger.error("Invalid history row type=%s", type(row).__name__)
            raise ValueError("Invalid history row")
        day = parse_release_date(row.get("date"))
        printing = str(row.get("printing") or "Normal")
        if day is None or day > today or len(printing) > 128:
            logger.error("Invalid history date or printing date=%s printing=%s", day, printing)
            raise ValueError("Invalid history identity")
        if day < today - timedelta(days=372):
            continue
        values = {"day": day, "printing": printing}
        for field in ("market_price", "avg_sales_price", "sales_volume"):
            raw = row.get(field)
            value = None
            if raw is not None:
                try:
                    number = Decimal(str(raw))
                    if not number.is_finite() or number < 0 or number > 999999999 or (field == "sales_volume" and number != number.to_integral_value()):
                        raise ValueError(f"Invalid {field}")
                    value = int(number) if field == "sales_volume" else number
                except (InvalidOperation, ValueError) as exc:
                    logger.error("Invalid history number field=%s date=%s error=%s: %s", field, day, type(exc).__name__, exc)
                    raise ValueError(f"Invalid history {field}") from exc
            values[field] = value
        key = (day, printing)
        if key in result and result[key] != values:
            logger.error("Conflicting history rows date=%s printing=%s", day, printing)
            raise ValueError("Conflicting duplicate history rows")
        result[key] = values
    return list(result.values())


def history_series(db: Session, card_id: str, days=30, printing=None):
    today = datetime.now(UTC).date()
    if not printing:
        available = list(db.scalars(select(MarketHistory.printing).where(MarketHistory.card_id == card_id).distinct().order_by(MarketHistory.printing)))
        printing = "Normal" if "Normal" in available else available[0] if available else "Normal"
    rows = list(db.scalars(select(MarketHistory).where(
        MarketHistory.card_id == card_id, MarketHistory.printing == printing,
        MarketHistory.day >= today - timedelta(days=days + 7), MarketHistory.day <= today,
    ).order_by(MarketHistory.day)))
    sync = db.scalar(select(ProviderCardState).where(ProviderCardState.card_id == card_id, ProviderCardState.provider == "tcgapi_history"))
    return summarize_history(rows, card_id, days, printing, sync, today)


def summarize_history(rows, card_id, days, printing, sync=None, today=None):
    today = today or datetime.now(UTC).date()
    priced = [r for r in rows if r.market_price is not None and r.market_price > 0]
    latest = priced[-1] if priced else None
    baseline = next((r for r in priced if latest and r.day == latest.day - timedelta(days=days)), None)
    recent = latest is not None and (today - latest.day).days <= 7
    growth = round((float(latest.market_price / baseline.market_price) - 1) * 100, 2) if baseline and recent else None
    start = latest.day - timedelta(days=days) if latest else today - timedelta(days=days)
    visible = [r for r in rows if r.day >= start]

    return {
        "card_id": card_id, "printing": printing, "days": days, "currency": "USD",
        "status": sync.match_status if sync else "not_synced",
        "synced_at": (sync.payload or {}).get("success_at") if sync else None,
        "coverage_start": visible[0].day if visible else None,
        "coverage_end": visible[-1].day if visible else None,
        "return_end": latest.day if latest else None,
        "return_percent": growth, "complete_return_window": growth is not None,
        "previous_price": float(baseline.market_price) if growth is not None else None,
        "comparison_price": float(latest.market_price) if growth is not None else None,
        "price_change_amount": round(float(latest.market_price - baseline.market_price), 2) if growth is not None else None,
        "comparison_source": "history" if growth is not None else None,
        "points": [{"date": r.day, "market_price": float(r.market_price) if r.market_price is not None else None,
                    "sales_volume": r.sales_volume, "avg_sales_price": float(r.avg_sales_price) if r.avg_sales_price is not None else None} for r in visible],
    }


def historical_returns(db: Session, card_ids, days):
    """Read a bounded latest/baseline window per printing, independent of history length."""
    if not card_ids:
        return {}
    today = datetime.now(UTC).date()
    ranked = select(MarketHistory.card_id, MarketHistory.printing, MarketHistory.day, MarketHistory.market_price,
        func.row_number().over(partition_by=(MarketHistory.card_id, MarketHistory.printing), order_by=MarketHistory.day.desc()).label("position")
    ).where(MarketHistory.card_id.in_(card_ids), MarketHistory.market_price > 0,
            MarketHistory.day <= today, MarketHistory.day >= today - timedelta(days=7)).subquery()
    latest = db.execute(select(ranked).where(ranked.c.position == 1)).mappings().all()
    # All possible exact baselines for the seven-day range of latest observations.
    baselines = db.execute(select(MarketHistory.card_id, MarketHistory.printing, MarketHistory.day, MarketHistory.market_price).where(
        MarketHistory.card_id.in_(card_ids), MarketHistory.market_price > 0,
        MarketHistory.day >= today - timedelta(days=days + 7), MarketHistory.day <= today - timedelta(days=days),
    )).all()
    by_key = {(r.card_id, r.printing, r.day): r.market_price for r in baselines}
    return {(r["card_id"], r["printing"]): round((float(r["market_price"] / base) - 1) * 100, 2)
            for r in latest if (base := by_key.get((r["card_id"], r["printing"], r["day"] - timedelta(days=days))))}


def sales_activity(db: Session, days=30, q=""):
    from app.config import get_settings
    if get_settings().ppt_primary_enabled:
        from app.services.ppt_prices import sales_activity as ppt_sales_activity
        return ppt_sales_activity(db, days, q)
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    base = select(MarketHistory.card_id, Card.name, Set.name.label("set_name"),
        func.sum(MarketHistory.sales_volume).label("sales"),
        func.count(MarketHistory.sales_volume).label("reported_rows"),
        func.max(MarketHistory.day).label("last_reported_day"),
        func.max(MarketHistory.fetched_at).label("synced_at"),
    ).join(Card, Card.id == MarketHistory.card_id).join(Set, Set.id == Card.set_id).where(
        MarketHistory.day >= start, MarketHistory.day <= today, MarketHistory.sales_volume.is_not(None))
    if q:
        from app.common.formatters import escape_like
        base = base.where(or_(Card.name.ilike(f"%{escape_like(q)}%", escape="\\"),
                              Set.name.ilike(f"%{escape_like(q)}%", escape="\\")))
    aggregate = base.group_by(MarketHistory.card_id, Card.name, Set.name).subquery()
    totals = db.execute(select(func.sum(aggregate.c.sales), func.count()).select_from(aggregate)).one()
    rows = db.execute(select(aggregate).order_by(aggregate.c.sales.desc(), aggregate.c.card_id).limit(50)).mappings().all()
    synced = db.scalar(select(func.max(aggregate.c.synced_at)))
    has_history = db.scalar(select(MarketHistory.card_id).limit(1)) is not None
    status = "ready" if totals[0] is not None else "no_matches" if q.strip() and has_history else "no_sales" if has_history else "not_synced"
    return {"days": days, "start": start, "end": today, "synced_at": synced, "status": status,
        "total_sales": int(totals[0]) if totals[0] is not None else None, "products_with_sales_data": totals[1],
        "items": [dict(row) for row in rows], "source": "TCG API reported sales",
        "coverage": "Synced products only. Missing sales are unknown; the newest 1–3 days may be incomplete."}


def catalog_coverage(db: Session):
    counts = dict(db.execute(select(Card.set_id, func.count()).group_by(Card.set_id)).all())
    local_sets = set(db.scalars(select(Set.id)))
    games = []
    for snapshot in db.scalars(select(CatalogSnapshot).order_by(CatalogSnapshot.game)):
        payload = snapshot.payload
        sets = payload.get("sets", [])
        entries = []
        for row in sets:
            set_id = str(row["id"])
            entries.append({"id": set_id, "name": row.get("name", set_id), "release_date": row.get("release_date"),
                "provider_card_count": row.get("card_count"), "local_card_count": counts.get(set_id, 0),
                "present_locally": set_id in local_sets, "provider_synced_at": row.get("last_synced_at")})
        entries.sort(key=lambda r: (r["release_date"] or "", r["id"]), reverse=True)
        games.append({"game": snapshot.game, "fetched_at": snapshot.fetched_at,
            "provider_synced_at": payload.get("game", {}).get("last_synced_at"),
            "provider_set_count": payload.get("game", {}).get("set_count"),
            "discovered_set_count": len(entries), "local_set_count": sum(r["present_locally"] for r in entries),
            "provider_card_count": payload.get("game", {}).get("card_count"),
            "local_card_count": sum(r["local_card_count"] for r in entries),
            "missing_sets": [r for r in entries if not r["present_locally"]][:30], "latest_sets": entries[:20]})
    return {"games": games, "status": "ready" if games else "not_synced"}
