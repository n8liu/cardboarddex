import type { MarketHistory, PriceFreshness } from "@/types/market-data";
export type CardSummary = {
  market_source?: string | null;
  id: string;
  name: string;
  set_id: string;
  set_name: string;
  number: string;
  printed_total: number | null;
  rarity: string | null;
  image_url: string;
  market_price: number | null;
  market_currency: string | null;
  last_updated_at?: string | null;
};

export type CardDetail = CardSummary & {
  series: string | null;
  release_date: string | null;
};

export type MarketMoverItem = {
  market_source?: string | null;
  card_id: string;
  name: string;
  set_id?: string | null;
  set_name: string;
  number?: string | null;
  rarity?: string | null;
  image_url: string;
  printing?: string | null;
  market_price: number;
  price_change_percentage: number;
  price_change_amount?: number | null;
  previous_price?: number | null;
  comparison_price?: number | null;
  comparison_source?: "history" | "estimated" | "pokemonpricetracker_history" | null;

  period: string;
  direction: "up" | "down";
  last_updated_at?: string | null;
};

export type MarketMoversResponse = {
  period: "24h" | "7d" | "30d";
  direction: "up" | "down" | "all";
  page: number;
  per_page: number;
  total_gainers: number;
  total_losers: number;
  total_pages: number;
  gainers: MarketMoverItem[];
  losers: MarketMoverItem[];
  updated_at: string;
};

export type MoverPeriod = "24h" | "7d" | "30d";
export type MoverDirection = "up" | "down" | "all";

export type CardSetOption = {
  id: string;
  name: string;
  series: string | null;
  release_date?: string | null;
  image_url?: string | null;
};

export type SetStats = {
  set_id: string;
  set_name: string | null;
  total_cards: number;
  priced_cards: number;
  total_price: number;
  avg_price: number | null;
  currency: string;
};

export type CardSort = "price_desc" | "price_asc" | "number_asc" | "number_desc" | "name" | "set";

export type ProviderPricingState = {
  provider: string;
  match_status: string;
  last_synced_at: string;
};

export type PriceObservation = {
  provider: string;
  provider_card_id: string;
  variant_id: string;
  condition: string | null;
  printing: string | null;
  grading_company: string | null;
  grade: number | null;
  price: number;
  currency: string;
  provider_updated_at: string | null;
  observed_at: string;
  listing_url?: string | null;
  low_price?: number | null;
  median_price?: number | null;
  lowest_with_shipping?: number | null;
  buylist_price?: number | null;
  price_change_24h?: number | null;
  price_change_7d?: number | null;
  price_change_30d?: number | null;
};

export type ListingGroup = {
  printing: string;
  condition: string;
  lowest_matched_price: number | null;
  avg_listing_price: number | null;
  median_listing_price: number | null;
  listing_sample_count: number;
  listing_seller_count: number;
};

export type ProviderQuote = {
  provider: string; language: string; currency: string; printing: string | null;
  condition: string | null; grade: string | null; metric: string; price: number;
  price_date: string; fetched_at: string | null; stale: boolean; primary: boolean;
  price_change_24h?: number | null; price_change_7d?: number | null; price_change_30d?: number | null;
  smart_price_outlier?: boolean;
};
export type ProviderHistorySeries = {
  cutover_date?: string | null;
  id: string; provider: string; language: string; currency: string;
  printing: string | null; condition: string | null; grade: string | null; metric: string;
  fetched_at: string; points: { date: string; price: number | null; sales_count: number | null; condition?: string | null; source?: string | null }[];
};

export type CardPricing = {
  market_quotes?: ProviderQuote[];
  market_history_series?: ProviderHistorySeries[];
  provider_quotes?: ProviderQuote[];
  provider_history?: ProviderHistorySeries[];
  ppt_mapped?: boolean;
  lowest_matched_price?: number | null;
  listing_seller_count?: number;
  selected_printing?: string;
  selected_condition?: string;
  listing_groups?: ListingGroup[];
  eligibility_version?: string;
  excluded_listing_count?: number;
  unconfirmed_listings?: { item_id: string; title: string; price?: number | null; listing_url?: string | null; status: string; reasons: string[] }[];
  card_id: string;
  provider_states: ProviderPricingState[];
  observations: PriceObservation[];
  avg_listing_price?: number | null;
  median_listing_price?: number | null;
  listing_sample_count?: number;
  tcg_market_prices?: PriceObservation[];
};

export type GradingProfitItem = {
  graded_source?: string | null;
  graded_metric?: string | null;
  card_id: string;
  name: string;
  set_id?: string | null;
  set_name: string;
  number?: string | null;
  rarity?: string | null;
  image_url: string;
  raw_price: number;
  psa10_price?: number | null;
  psa10_profit?: number | null;
  psa10_roi?: number | null;
  psa9_price?: number | null;
  psa9_profit?: number | null;
  psa9_roi?: number | null;
  spread_multiplier?: number | null;
  expected_value?: number | null;
  psa9_safe: boolean;
  grading_fee: number;
  last_updated_at?: string | null;
};

export type GradingSortOption =
  | "psa10_profit_desc"
  | "psa10_roi_desc"
  | "psa9_profit_desc"
  | "psa9_roi_desc"
  | "ev_desc"
  | "spread_desc"
  | "raw_price_asc"
  | "raw_price_desc";

export type GradingProfitResponse = {
  page: number;
  per_page: number;
  total_cards: number;
  total_pages: number;
  grading_fee: number;
  sort_by: string;
  items: GradingProfitItem[];
  updated_at: string;
};

export type SealedSignalItem = PriceFreshness & {
  market_source?: string | null;
  return_days?: number;
  price_change_amount?: number | null;
  previous_price?: number | null;
  comparison_price?: number | null;
  comparison_source?: "history" | "estimated" | "pokemonpricetracker_history" | null;

  return_percent?: number | null;
  history?: MarketHistory;
  card_id: string;
  name: string;
  clean_name?: string | null;
  set_id: string;
  set_name: string;
  series?: string | null;
  release_date?: string | null;
  image_url: string;
  product_type: string;
  market_price: number;
  low_price?: number | null;
  median_price?: number | null;
  lowest_with_shipping?: number | null;
  buylist_price?: number | null;
  total_listings: number;
  supply_rating: string;
  set_age_months: number;
  price_change_24h?: number | null;
  price_change_7d?: number | null;
  price_change_30d?: number | null;
  supply_score: number | null;
  demand_score: number | null;
  momentum_score: number | null;
  vintage_score: number | null;
  signal_score: number | null;
  signal_label: "STRONG BUY" | "BUY" | "HOLD" | "UNDERPERFORM" | string;
  last_updated_at?: string | null;
};

export type SealedSignalType = "all" | "strong_buy" | "buy" | "hold" | "underperform";
export type SealedProductType =
  | "all"
  | "booster_box"
  | "etb"
  | "bundle"
  | "case"
  | "pack"
  | "blister"
  | "collection";

export type SealedSortOption =
  | "score_desc"
  | "supply_asc"
  | "momentum_desc"
  | "price_desc"
  | "price_asc"
  | "age_desc";

export type SealedSignalsResponse = {
  page: number;
  per_page: number;
  total_items: number;
  total_pages: number;
  signal_filter: string;
  product_type_filter: string;
  sort_by: string;
  strong_buy_count: number;
  buy_count: number;
  hold_count: number;
  underperform_count: number;
  items: SealedSignalItem[];
  updated_at: string;
};

export type VolumeTimeframe = "24h" | "7d" | "30d" | "all_time" | "2026_ytd";
export type VolumeSortMetric = "volume_desc" | "sales_desc" | "growth_desc" | "avg_price_desc";

export type PokemonVolumeItem = {
  rank: number;
  pokemon_name: string;
  dex_number: number;
  sprite_url: string;
  volume_usd: number;
  volume_formatted: string;
  sales_count: number;
  momentum_percentage: number;
  momentum_trend: "up" | "down" | "flat";
  yoy_percentage: number;
  yoy_trend: "up" | "down" | "flat";
  cards_count: number;
  avg_card_price?: number | null;
  top_card_name?: string | null;
  top_card_price?: number | null;
  top_card_id?: string | null;
};

export type PokemonVolumeResponse = {
  timeframe: string;
  sort_by?: string;
  total_volume_usd: number;
  total_sales_count?: number;
  total_pokemon: number;
  items: PokemonVolumeItem[];
  updated_at: string;
};

export type TrendingCardItem = {
  rank: number;
  card_id: string;
  name: string;
  set_name: string;
  set_id?: string | null;
  number?: string | null;
  rarity?: string | null;
  image_url: string;
  market_price?: number | null;
  price_change_7d?: number | null;
  clicks_count: number;
  trend_score: number;
  trend_direction: "up" | "down" | "flat";
};

export type TrendingPokemonItem = {
  rank: number;
  pokemon_name: string;
  dex_number: number;
  sprite_url: string;
  clicks_count: number;
  searches_count: number;
  cards_count: number;
  trend_score: number;
  trend_direction: "up" | "down" | "flat";
  top_card_name?: string | null;
  top_card_price?: number | null;
  top_card_id?: string | null;
};

export type TrendingDashboardResponse = {
  timeframe: string;
  trending_cards: TrendingCardItem[];
  trending_pokemon: TrendingPokemonItem[];
  volume_pokemon: PokemonVolumeItem[];
  total_volume_usd: number;
  total_sales_count: number;
  updated_at: string;
  /** Worker snapshot older than 30 minutes, served while updates are paused. */
  is_stale?: boolean;
};

export type TrackActionPayload = {
  entityType: "card" | "pokemon" | "search";
  entityId: string;
  action?: "click" | "search" | "view";
};

export type LiveUpdateProviderFilter = "all" | "ebay" | "tcgapi" | "pokemonpricetracker";
export type LiveUpdateGradeFilter = "all" | "graded" | "psa10" | "psa9" | "raw";

export type LiveUpdateItem = {
  update_type?: string;
  price_date?: string | null;
  metric?: string | null;
  id: string;
  card_id: string;
  card_name: string;
  set_id: string;
  set_name: string;
  number?: string | null;
  rarity?: string | null;
  image_url: string;
  provider: string;
  price: number;
  currency: string;
  condition?: string | null;
  printing?: string | null;
  grading_company?: string | null;
  grade?: string | null;
  listing_title?: string | null;
  listing_url?: string | null;
  observed_at: string;
};

export type LiveUpdatesResponse = {
  page: number;
  per_page: number;
  total_items: number;
  total_pages: number;
  provider_filter: string;
  grade_filter: string;
  total_ebay_updates: number;
  total_tcg_updates: number;
  total_legacy_updates?: number;
  graded_updates_count: number;
  items: LiveUpdateItem[];
  updated_at: string;
};

export type GameLanguage = "all" | "pokemon" | "pokemon-japan";


export type LiveFeedResponse = {
  page: number;
  per_page: number;
  has_more: boolean;
  items: LiveUpdateItem[];
  updated_at: string;
};

export type LiveStatsResponse = {
  total_items: number;
  total_ebay_updates: number;
  total_tcg_updates: number;
  total_legacy_updates?: number;
  total_ppt_updates: number;
  graded_updates_count: number;
  generated_at: string;
  is_stale: boolean;
};
