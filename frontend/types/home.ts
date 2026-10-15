import type { HistoryPoint } from "@/types/market-data";

export type HomeHighlight = {
  card_id: string;
  name: string;
  set_name: string;
  image_url: string;
  printing: string | null;
  market_price: number;
  change_percent: number;
  market_price_as_of: string | null;
  observed_at: string;
  price_freshness: "recent" | "stale" | "unknown";
  history: HistoryPoint[];
};
export type HomeRelease = {
  id: string;
  name: string;
  game: "pokemon" | "pokemon-japan";
  release_date: string;
  upcoming: boolean;
  card_count: number;
  image_url: string | null;
};
export type HomeOverview = {
  calculated_at: string;
  catalog_updated_at: string | null;
  latest_observation_at: string | null;
  products: number;
  sets: number;
  price_observations: number;
  gainer: HomeHighlight | null;
  loser: HomeHighlight | null;
  sealed: HomeHighlight | null;
  releases: HomeRelease[];
};

export type HomeStats = Pick<HomeOverview, "products" | "sets" | "price_observations" | "calculated_at">;
