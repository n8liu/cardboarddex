export interface StoredBinderPage {
  id: string;
  name?: string;
  slots: Record<number, string>; // slotIndex (0..8) -> cardId (e.g. "28402")
}

export interface StoredBinder {
  version: 1;
  name: string;
  pages: StoredBinderPage[];
}

export interface PortfolioCardItem {
  id: string;
  name: string;
  set_name: string;
  number: string;
  rarity: string | null;
  image_url: string;
  market_price: number | null;
  market_currency: string | null;
  price_change_24h: number | null;
  price_change_7d: number | null;
  price_change_30d: number | null;
}

export interface PortfolioHistoryPoint {
  date: string; // YYYY-MM-DD
  total_value: number;
  card_count: number;
}

export interface PortfolioValuationResponse {
  total_cards: number;
  total_current_value: number;
  currency: string;
  delta_24h_amount: number | null;
  delta_24h_percent: number | null;
  delta_7d_amount: number | null;
  delta_7d_percent: number | null;
  delta_30d_amount: number | null;
  delta_30d_percent: number | null;
  highest_value_card: PortfolioCardItem | null;
  cards: PortfolioCardItem[];
  history: PortfolioHistoryPoint[];
  updated_at?: string;
}
