from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProviderCardState(Base):
    __tablename__ = "provider_card_states"
    __table_args__ = (
        UniqueConstraint("card_id", "provider", name="uq_provider_card_states_card_provider"),
        Index("ix_provider_card_states_provider_status", "provider", "match_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_card_id: Mapped[str | None] = mapped_column(String(128))
    match_status: Mapped[str] = mapped_column(String(24), nullable=False)
    match_method: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_price_observations_fingerprint"),
        Index("ix_price_observations_card_provider_time", "card_id", "provider", "observed_at"),
        Index(
            "ix_price_observations_analytics_cover", "card_id",
            postgresql_include=[
                "id", "price", "provider", "grading_company", "observed_at", "provider_updated_at",
            ],
        ),
        Index(
            "ix_price_observations_search_lookup",
            "card_id",
            "provider",
            "grading_company",
            "provider_updated_at",
            "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_card_id: Mapped[str] = mapped_column(String(128), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(64))
    printing: Mapped[str | None] = mapped_column(String(64))
    grading_company: Mapped[str | None] = mapped_column(String(32))
    grade: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class RawEbayListing(Base):
    __tablename__ = "raw_ebay_listings"
    __table_args__ = (
        UniqueConstraint("ebay_item_id", name="uq_raw_ebay_listings_item_id"),
        Index("ix_raw_ebay_listings_card_id", "card_id"),
        Index("ix_raw_ebay_listings_match_status", "match_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ebay_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("cards.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    item_url: Mapped[str | None] = mapped_column(String(1024))
    seller_feedback_score: Mapped[int | None] = mapped_column()
    listing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    match_status: Mapped[str] = mapped_column(String(24), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(128))
    grading_company: Mapped[str | None] = mapped_column(String(32))
    grade: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
