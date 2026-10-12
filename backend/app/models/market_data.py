"""Provider-reported daily history and catalog snapshots, separate from catalog tables."""
from datetime import date, datetime
from typing import Any
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MarketHistory(Base):
    __tablename__ = "market_history"
    __table_args__ = (Index("ix_market_history_day", "day"),)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), primary_key=True)
    printing: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    market_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    avg_sales_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    sales_volume: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CatalogSnapshot(Base):
    __tablename__ = "catalog_snapshots"
    game: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
