from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class CardSummary(BaseModel):
    id: str
    name: str
    set_id: str
    set_name: str
    number: str
    printed_total: int | None
    rarity: str | None
    image_url: str
    market_price: float | None = None
    market_currency: str | None = None
    last_updated_at: datetime | None = None


class CardDetail(CardSummary):
    series: str | None
    release_date: date | None


class MarketMoverItem(BaseModel):
    card_id: str
    name: str
    set_id: str | None = None
    set_name: str
    number: str | None = None
    rarity: str | None = None
    image_url: str
    printing: str | None = None
    market_price: float
    price_change_percentage: float
    price_change_amount: float | None = None
    period: str
    direction: str
    last_updated_at: datetime | None = None


class MarketMoversResponse(BaseModel):
    period: str
    direction: str
    page: int
    per_page: int
    total_gainers: int
    total_losers: int
    total_pages: int
    gainers: list[MarketMoverItem]
    losers: list[MarketMoverItem]
    updated_at: datetime


class CardSetOption(BaseModel):
    id: str
    name: str
    series: str | None
    release_date: date | None = None
    image_url: str | None = None


class SetStatsResponse(BaseModel):
    set_id: str
    set_name: str | None = None
    total_cards: int
    priced_cards: int
    total_price: float
    avg_price: float | None = None
    currency: str = "USD"


class PokemonSetCount(BaseModel):
    id: str
    name: str
    count: int


class PokemonCardsResponse(BaseModel):
    pokemon_name: str
    total_cards: int
    highest_price: float | None = None
    lowest_price: float | None = None
    available_sets: list[PokemonSetCount] = []
    cards: list[CardSummary] = []


class ProviderPricingState(BaseModel):
    provider: str
    match_status: str
    last_synced_at: datetime


class PriceObservationItem(BaseModel):
    provider: str
    provider_card_id: str
    variant_id: str
    condition: str | None
    printing: str | None
    grading_company: str | None
    grade: float | None
    price: float
    currency: str
    provider_updated_at: datetime | None
    observed_at: datetime
    listing_url: str | None = None
    low_price: float | None = None
    median_price: float | None = None
    lowest_with_shipping: float | None = None
    buylist_price: float | None = None
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    price_change_30d: float | None = None


class CardPricingResponse(BaseModel):
    card_id: str
    provider_states: list[ProviderPricingState]
    observations: list[PriceObservationItem]
    avg_listing_price: float | None = None


class GradingProfitItem(BaseModel):
    card_id: str
    name: str
    set_id: str | None = None
    set_name: str
    number: str | None = None
    rarity: str | None = None
    image_url: str
    raw_price: float
    psa10_price: float | None = None
    psa10_profit: float | None = None
    psa10_roi: float | None = None
    psa9_price: float | None = None
    psa9_profit: float | None = None
    psa9_roi: float | None = None
    spread_multiplier: float | None = None
    expected_value: float | None = None
    psa9_safe: bool = False
    grading_fee: float
    last_updated_at: datetime | None = None


class GradingProfitResponse(BaseModel):
    page: int
    per_page: int
    total_cards: int
    total_pages: int
    grading_fee: float
    sort_by: str
    items: list[GradingProfitItem]
    updated_at: datetime


class SealedSignalItem(BaseModel):
    card_id: str
    name: str
    clean_name: str | None = None
    set_id: str
    set_name: str
    series: str | None = None
    release_date: date | None = None
    image_url: str
    product_type: str
    market_price: float
    low_price: float | None = None
    median_price: float | None = None
    lowest_with_shipping: float | None = None
    buylist_price: float | None = None
    total_listings: int = 0
    supply_rating: str
    set_age_months: int = 0
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    price_change_30d: float | None = None
    supply_score: int
    demand_score: int
    momentum_score: int
    vintage_score: int
    signal_score: int
    signal_label: str
    last_updated_at: datetime | None = None


class SealedSignalsResponse(BaseModel):
    page: int
    per_page: int
    total_items: int
    total_pages: int
    signal_filter: str
    product_type_filter: str
    sort_by: str
    strong_buy_count: int
    buy_count: int
    hold_count: int
    underperform_count: int
    items: list[SealedSignalItem]
    updated_at: datetime


class PokemonVolumeItem(BaseModel):
    rank: int
    pokemon_name: str
    dex_number: int
    sprite_url: str
    volume_usd: float
    volume_formatted: str
    sales_count: int = 0
    momentum_percentage: float = 0.0
    momentum_trend: Literal["up", "down", "flat"] = "flat"
    yoy_percentage: float = 0.0
    yoy_trend: Literal["up", "down", "flat"] = "flat"
    cards_count: int
    avg_card_price: float | None = None
    top_card_name: str | None = None
    top_card_price: float | None = None
    top_card_id: str | None = None


class PokemonVolumeResponse(BaseModel):
    timeframe: str
    sort_by: str = "volume_desc"
    total_volume_usd: float
    total_sales_count: int = 0
    total_pokemon: int
    items: list[PokemonVolumeItem]
    updated_at: datetime


class TrendingCardItem(BaseModel):
    rank: int
    card_id: str
    name: str
    set_name: str
    set_id: str | None = None
    number: str | None = None
    rarity: str | None = None
    image_url: str
    market_price: float | None = None
    price_change_7d: float | None = None
    clicks_count: int = 0
    trend_score: float = 0.0
    trend_direction: Literal["up", "down", "flat"] = "flat"


class TrendingPokemonItem(BaseModel):
    rank: int
    pokemon_name: str
    dex_number: int
    sprite_url: str
    clicks_count: int = 0
    searches_count: int = 0
    cards_count: int = 0
    trend_score: float = 0.0
    trend_direction: Literal["up", "down", "flat"] = "flat"
    top_card_name: str | None = None
    top_card_price: float | None = None
    top_card_id: str | None = None


class TrendingDashboardResponse(BaseModel):
    timeframe: str
    trending_cards: list[TrendingCardItem]
    trending_pokemon: list[TrendingPokemonItem]
    volume_pokemon: list[PokemonVolumeItem]
    total_volume_usd: float = 0.0
    total_sales_count: int = 0
    updated_at: datetime


class TrackActionRequest(BaseModel):
    entity_type: Literal["card", "pokemon", "search"]
    entity_id: str = Field(..., max_length=100, pattern=r"^[a-zA-Z0-9_\-\.\:\'\s]+$")
    action: Literal["click", "search", "view"] = "click"


class LiveUpdateItem(BaseModel):
    id: str
    card_id: str
    card_name: str
    set_id: str
    set_name: str
    number: str | None = None
    rarity: str | None = None
    image_url: str
    provider: str
    price: float
    currency: str = "USD"
    condition: str | None = None
    printing: str | None = None
    grading_company: str | None = None
    grade: str | None = None
    listing_title: str | None = None
    listing_url: str | None = None
    observed_at: datetime


class LiveUpdatesResponse(BaseModel):
    page: int
    per_page: int
    total_items: int
    total_pages: int
    provider_filter: str
    grade_filter: str
    total_ebay_updates: int
    total_tcg_updates: int
    graded_updates_count: int
    items: list[LiveUpdateItem]
    updated_at: datetime


class PortfolioValuationRequest(BaseModel):
    card_ids: list[str] = Field(..., max_length=200)
    days: int = Field(default=365, ge=7, le=730)


class PortfolioCardItem(BaseModel):
    id: str
    name: str
    set_name: str
    number: str
    rarity: str | None = None
    image_url: str
    market_price: float | None = None
    market_currency: str | None = None
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    price_change_30d: float | None = None


class PortfolioHistoryPoint(BaseModel):
    date: str  # YYYY-MM-DD
    total_value: float
    card_count: int


class PortfolioValuationResponse(BaseModel):
    total_cards: int
    total_current_value: float
    currency: str = "USD"
    delta_24h_amount: float | None = None
    delta_24h_percent: float | None = None
    delta_7d_amount: float | None = None
    delta_7d_percent: float | None = None
    delta_30d_amount: float | None = None
    delta_30d_percent: float | None = None
    highest_value_card: PortfolioCardItem | None = None
    cards: list[PortfolioCardItem]
    history: list[PortfolioHistoryPoint]
    updated_at: datetime

