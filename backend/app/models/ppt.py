"""Additive provider identity, current quotes and compact, dimensioned history."""
from datetime import date, datetime
from typing import Any
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PPTProduct(Base):
    __tablename__ = "ppt_products"
    __table_args__ = (Index("ix_ppt_products_due", "status", "segment", "last_success_at"),)
    # Language and product kind are part of identity, even if provider IDs overlap.
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("cards.id"), index=True)
    segment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    match_method: Mapped[str | None] = mapped_column(String(64))
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quotes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    primary_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failures: Mapped[int] = mapped_column(default=0)


class PPTHistory(Base):
    __tablename__ = "ppt_history"
    __table_args__ = (Index("ix_ppt_history_card_month", "card_id", "month"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("ppt_products.id"), nullable=False)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    points: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PPTCheckpoint(Base):
    __tablename__ = "ppt_checkpoints"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class PPTCurrentQuote(Base):
    __tablename__ = "ppt_current_quotes"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("ppt_products.id"), nullable=False, index=True)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)


class MarketHistoryTransition(Base):
    """Immutable display boundary; original provider rows remain untouched."""
    __tablename__ = "market_history_transitions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("ppt_products.id"))
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    cutover_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
