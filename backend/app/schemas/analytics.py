from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class PageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    visitor_id: UUID
    path: str = Field(max_length=128, pattern=r"^/(?:catalog|pokedex|market-movers|grading-profit|sealed-signals|top-volume|live-updates|binder|cards/[A-Za-z0-9_-]{1,64}|pokemon/[A-Za-z0-9_-]{1,64})?$")


class AdminLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret: SecretStr = Field(min_length=1, max_length=512)


class TrafficCounts(BaseModel):
    views: int
    visitors: int
    sessions: int


class DailyTraffic(TrafficCounts):
    day: date


class CountryTraffic(TrafficCounts):
    country: str


class PageTraffic(TrafficCounts):
    path: str


class StatsReport(BaseModel):
    start: date
    end: date
    timezone: str = "UTC"
    updated_at: datetime
    tracking_started_at: datetime | None
    tracking_enabled: bool
    earliest_report_date: date
    total_views: int
    total_visitors: int
    current: TrafficCounts
    previous: TrafficCounts | None
    daily: list[DailyTraffic]
    countries: list[CountryTraffic]
    pages: list[PageTraffic]
