export interface PriceFreshness {
  market_price_as_of?: string | null;
  price_age_days?: number | null;
  price_freshness?: "unknown" | "recent" | "stale";
  checked_at?: string | null;
}
export interface HistoryPoint { date: string; market_price: number | null; sales_volume: number | null; avg_sales_price: number | null }
export interface MarketHistory extends PriceFreshness {
  card_id: string; printing: string; days: number; currency: string;
  status: string; synced_at: string | null;
  coverage_start: string | null; coverage_end: string | null; return_end: string | null;
  return_percent: number | null; complete_return_window: boolean;
  market_price?: number | null; points: HistoryPoint[];
}
export interface SalesActivity {
  status?: "ready" | "not_synced" | "no_matches" | "no_sales";
  days: number; start: string; end: string; synced_at: string | null;
  total_sales: number | null; products_with_sales_data: number; coverage: string;
  items: { card_id: string; name: string; set_name: string; sales: number; reported_rows: number; last_reported_day: string }[];
}
export interface CatalogSet {
  id: string; name: string; release_date: string | null; provider_card_count: number | null;
  local_card_count: number; present_locally: boolean; provider_synced_at: string | null;
}
export interface CatalogHealth {
  status: string;
  games: { game: string; fetched_at: string; provider_synced_at: string | null;
    provider_set_count: number | null; discovered_set_count: number; local_set_count: number;
    provider_card_count: number | null; local_card_count: number; missing_sets: CatalogSet[]; latest_sets: CatalogSet[] }[];
}
