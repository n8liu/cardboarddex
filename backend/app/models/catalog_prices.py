"""Derived catalog prices, independently rebuildable from stored source data."""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CatalogPriceCandidate(Base):
    __tablename__ = "catalog_price_candidates"
    __table_args__ = (
        Index("uq_catalog_price_tcgapi", "card_id", unique=True,
              postgresql_where=text("provider = 'tcgapi'"), sqlite_where=text("provider = 'tcgapi'")),
        Index("ix_catalog_price_lookup", "card_id", "provider", "provider_updated_at", "observed_at", "observation_id"),
        # Broad catalog price sorts walk this index instead of sorting every card.
        Index("ix_catalog_price_selected", "price", postgresql_where=text("selected"), sqlite_where=text("selected")),
    )
    card_id: Mapped[str] = mapped_column(String(64), ForeignKey("cards.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    observation_id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    condition: Mapped[str | None] = mapped_column(String(64))
    printing: Mapped[str | None] = mapped_column(String(64))
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ppt_price_date: Mapped[date | None] = mapped_column(Date)
    # The card's PPT-primary price: newest primary PPT row, else its TCG row.
    selected: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class CatalogPriceProjectionState(Base):
    __tablename__ = "catalog_price_projection_state"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    after_card_id: Mapped[str | None] = mapped_column(String(64))
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
