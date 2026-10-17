"""Versioned evidence for listing identity; never a claim of authenticity."""
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import DateTime, ForeignKey, JSON, String, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ListingAssessment(Base):
    __tablename__ = "listing_assessments"
    __table_args__ = (Index("ix_listing_assessments_pending", "status", "checked_at"),)
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    text_status: Mapped[str] = mapped_column(String(24))
    image_status: Mapped[str] = mapped_column(String(24), default="pending")
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[dict[str, Any]] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
