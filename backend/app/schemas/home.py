from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class HomeHighlight(BaseModel):
    card_id: str
    name: str
    set_name: str
    image_url: str
    printing: str | None
    market_price: float
    change_percent: float
    market_price_as_of: date | None
    observed_at: datetime
    price_freshness: Literal['recent', 'stale', 'unknown']
    history: list[dict]


class HomeRelease(BaseModel):
    id: str
    name: str
    game: Literal['pokemon', 'pokemon-japan']
    release_date: date
    upcoming: bool
    card_count: int
    image_url: str | None


class HomeOverview(BaseModel):
    calculated_at: datetime
    catalog_updated_at: datetime | None
    latest_observation_at: datetime | None
    products: int
    sets: int
    price_observations: int
    gainer: HomeHighlight | None
    loser: HomeHighlight | None
    sealed: HomeHighlight | None
    releases: list[HomeRelease]
