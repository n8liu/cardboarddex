"""Small indexed telemetry writes and SQL aggregates; never query catalog tables."""
import hashlib
import hmac
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.common.admin_auth import utc
from app.config import get_settings
from app.models.analytics import AdminSession, AnalyticsDay, AnalyticsEvent, AnalyticsVisitor
from app.schemas.analytics import PageView

RETENTION_DAYS = 90


def insert_for(db: Session, model):
    return (pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert)(model)


def record_page_view(db: Session, event: PageView, country: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    secret = get_settings().analytics_identity_secret
    if not secret or len(secret) < 32:
        raise ValueError("ANALYTICS_IDENTITY_SECRET must contain at least 32 characters")
    visitor_id = hmac.new(secret.encode(), str(event.visitor_id).encode(), hashlib.sha256).hexdigest()
    # Upsert + row lock serialize concurrent tabs for this visitor, including first visit.
    db.execute(insert_for(db, AnalyticsVisitor).values(
        id=visitor_id, first_seen=now, last_seen=now, session_id=str(uuid4())
    ).on_conflict_do_nothing(index_elements=["id"]))
    visitor = db.execute(select(AnalyticsVisitor).where(AnalyticsVisitor.id == visitor_id).with_for_update()).scalar_one()
    if db.get(AnalyticsEvent, str(event.event_id)) is not None:
        db.rollback()
        return False
    if now - utc(visitor.last_seen) >= timedelta(minutes=30):
        visitor.session_id = str(uuid4())
    result = db.execute(insert_for(db, AnalyticsEvent).values(
        id=str(event.event_id), visitor_id=visitor_id, session_id=visitor.session_id,
        occurred_at=now, path=event.path, country=country,
    ).on_conflict_do_nothing(index_elements=["id"]))
    if result.rowcount == 0:
        db.rollback()
        return False
    visitor.last_seen = max(now, utc(visitor.last_seen))
    db.execute(insert_for(db, AnalyticsDay).values(day=now.date(), views=1).on_conflict_do_update(
        index_elements=["day"], set_={"views": AnalyticsDay.views + 1}))
    db.commit()
    return True


def report(db: Session, start: date, end: date, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    earliest = now.date() - timedelta(days=RETENTION_DAYS - 1)
    if start < earliest or end > now.date() or start > end:
        raise ValueError("Select dates within the last 90 days, including today (UTC)")
    columns = (func.count().label("views"), func.count(func.distinct(AnalyticsEvent.visitor_id)).label("visitors"),
               func.count(func.distinct(AnalyticsEvent.session_id)).label("sessions"))

    def bounds(first: date, last: date):
        return (AnalyticsEvent.occurred_at >= datetime.combine(first, time.min, UTC),
                AnalyticsEvent.occurred_at < datetime.combine(last + timedelta(days=1), time.min, UTC))

    def counts(first: date, last: date):
        return dict(db.execute(select(*columns).where(*bounds(first, last))).mappings().one())

    days = (end - start).days + 1
    previous_start = start - timedelta(days=days)
    timestamp = func.timezone("UTC", AnalyticsEvent.occurred_at) if db.get_bind().dialect.name == "postgresql" else AnalyticsEvent.occurred_at
    day_expr = func.date(timestamp)
    daily_rows = db.execute(select(day_expr.label("day"), *columns).where(*bounds(start, end)).group_by(day_expr)).mappings()
    by_day = {str(row["day"]): dict(row) for row in daily_rows}
    daily = [by_day.get(str(start + timedelta(days=i)), {
        "day": start + timedelta(days=i), "views": 0, "visitors": 0, "sessions": 0,
    }) for i in range(days)]

    def breakdown(column, label: str, limit: int):
        return [dict(row) for row in db.execute(select(column.label(label), *columns)
            .where(*bounds(start, end)).group_by(column).order_by(func.count().desc(), column).limit(limit)).mappings()]

    return {
        "start": start, "end": end, "updated_at": now,
        "tracking_started_at": db.scalar(select(func.min(AnalyticsVisitor.first_seen))),
        "tracking_enabled": get_settings().analytics_enabled,
        "earliest_report_date": earliest,
        "total_views": db.scalar(select(func.coalesce(func.sum(AnalyticsDay.views), 0))),
        "total_visitors": db.scalar(select(func.count()).select_from(AnalyticsVisitor)),
        "current": counts(start, end),
        "previous": counts(previous_start, start - timedelta(days=1)) if previous_start >= earliest else None,
        "daily": daily, "countries": breakdown(AnalyticsEvent.country, "country", 250),
        "pages": breakdown(AnalyticsEvent.path, "path", 20),
    }


def cleanup(db: Session, now: datetime | None = None) -> int:
    """Delete in bounded transactions, retaining lifetime visitors and daily view totals."""
    now = now or datetime.now(UTC)
    cutoff = datetime.combine(now.date() - timedelta(days=RETENTION_DAYS - 1), time.min, UTC)
    total = 0
    for model, condition, key in (
        (AnalyticsEvent, AnalyticsEvent.occurred_at < cutoff, AnalyticsEvent.id),
        (AdminSession, AdminSession.expires_at <= now, AdminSession.token_hash),
    ):
        while True:
            ids = list(db.scalars(select(key).where(condition).limit(1000)))
            if not ids:
                break
            db.execute(delete(model).where(key.in_(ids)))
            db.commit()
            total += len(ids)
    return total
