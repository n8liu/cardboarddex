import type {
  CardDetail,
  CardPricing,
  CardSetOption,
  CardSort,
  CardSummary,
  GradingProfitResponse,
  GradingSortOption,
  MarketMoversResponse,
  MoverDirection,
  MoverPeriod,
  SealedProductType,
  SealedSignalsResponse,
  SealedSignalType,
  SealedSortOption,
  PokemonVolumeResponse,
  VolumeTimeframe,
  VolumeSortMetric,
  TrendingDashboardResponse,
  TrackActionPayload,
  LiveUpdatesResponse,
  LiveUpdateProviderFilter,
  LiveUpdateGradeFilter,
  GameLanguage,
} from "@/types/card";
import type { PokemonCardsResponse } from "@/types/pokemon";

const DEFAULT_API_URL =
  process.env.NEXT_PUBLIC_API_URL?.trim() ||
  process.env.DEFAULT_API_URL?.trim() ||
  "http://localhost:8000";

function resolveApiUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    process.env.DEFAULT_API_URL?.trim() ||
    DEFAULT_API_URL
  );
}

const API_URL = resolveApiUrl();
export const CARD_PAGE_SIZE = 24;

export function buildQueryString(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const str = searchParams.toString();
  return str ? `?${str}` : "";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
  });
  if (!response.ok) {
    throw new Error(`CardboardDex API ${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

type SearchCardOptions = {
  limit?: number;
  offset?: number;
  setId?: string;
  sortBy?: CardSort;
  hideSealed?: boolean;
  sealedOnly?: boolean;
  game?: GameLanguage;
};

export function searchCards(query: string, options: SearchCardOptions = {}): Promise<CardSummary[]> {
  const qs = buildQueryString({
    q: query,
    limit: options.limit ?? CARD_PAGE_SIZE,
    offset: options.offset ?? 0,
    sort_by: options.sortBy ?? "price_desc",
    hide_sealed: options.hideSealed === false ? "false" : "true",
    set_id: options.setId,
    sealed_only: options.sealedOnly ? "true" : undefined,
    game: options.game && options.game !== "all" ? options.game : undefined,
  });
  return request<CardSummary[]>(`/cards/search${qs}`, { cache: "no-store" });
}

export function getPokemonCards(
  pokemonName: string,
  options: {
    setId?: string;
    sortBy?: CardSort;
    game?: GameLanguage;
    limit?: number;
    offset?: number;
    ref?: string;
  } = {}
): Promise<PokemonCardsResponse> {
  const qs = buildQueryString({
    limit: options.limit ?? CARD_PAGE_SIZE,
    offset: options.offset ?? 0,
    sort_by: options.sortBy ?? "price_desc",
    set_id: options.setId,
    game: options.game && options.game !== "all" ? options.game : undefined,
    ref: options.ref,
  });
  return request<PokemonCardsResponse>(
    `/cards/pokemon/${encodeURIComponent(pokemonName)}${qs}`,
    { cache: "no-store" }
  );
}

export function getCardSets(game?: GameLanguage): Promise<CardSetOption[]> {
  const qs = buildQueryString({
    game: game && game !== "all" ? game : undefined,
  });
  return request<CardSetOption[]>(`/cards/sets${qs}`, {
    next: { revalidate: 86400 },
  });

}

export function getMarketMovers(options: {
  direction?: MoverDirection;
  period?: MoverPeriod;
  game?: "pokemon" | "pokemon-japan";
  page?: number;
  perPage?: number;
} = {}): Promise<MarketMoversResponse> {
  const qs = buildQueryString({
    direction: options.direction ?? "all",
    period: options.period ?? "24h",
    game: options.game ?? "pokemon",
    page: options.page ?? 1,
    per_page: options.perPage ?? 24,
  });
  return request<MarketMoversResponse>(`/cards/market-movers${qs}`, {
    next: { revalidate: 300 },
  });
}

export async function getCard(
  cardId: string,
  options?: { ref?: string }
): Promise<CardDetail | null> {
  const qs = options?.ref ? `?ref=${encodeURIComponent(options.ref)}` : "";
  const response = await fetch(`${API_URL}/cards/${encodeURIComponent(cardId)}${qs}`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`CardboardDex card request returned ${response.status}`);
  }
  return response.json() as Promise<CardDetail>;
}

export async function getCardPricing(cardId: string): Promise<CardPricing | null> {
  const response = await fetch(
    `${API_URL}/cards/${encodeURIComponent(cardId)}/prices?days=365`,
    { cache: "no-store" },
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`CardboardDex pricing request returned ${response.status}`);
  }
  return response.json() as Promise<CardPricing>;
}

export function getGradingProfit(options: {
  gradingFee?: number;
  sortBy?: GradingSortOption;
  targetGrade?: "all" | "psa10" | "psa9";
  minProfit?: number;
  maxRawPrice?: number;
  minSpread?: number;
  psa9SafeOnly?: boolean;
  setId?: string;
  query?: string;
  page?: number;
  perPage?: number;
} = {}): Promise<GradingProfitResponse> {
  const qs = buildQueryString({
    page: options.page ?? 1,
    per_page: options.perPage ?? 24,
    sort_by: options.sortBy ?? "psa10_profit_desc",
    target_grade: options.targetGrade ?? "all",
    grading_fee: options.gradingFee,
    min_profit: options.minProfit,
    max_raw_price: options.maxRawPrice,
    min_spread: options.minSpread,
    psa9_safe_only: options.psa9SafeOnly ? "true" : undefined,
    set_id: options.setId,
    q: options.query,
  });
  return request<GradingProfitResponse>(`/cards/grading-profit${qs}`, {
    next: { revalidate: 300 },
  });
}

export function getSealedSignals(options: {
  signal?: SealedSignalType;
  productType?: SealedProductType;
  sortBy?: SealedSortOption;
  setId?: string;
  query?: string;
  page?: number;
  perPage?: number;
} = {}): Promise<SealedSignalsResponse> {
  const qs = buildQueryString({
    signal: options.signal ?? "all",
    product_type: options.productType ?? "all",
    sort_by: options.sortBy ?? "score_desc",
    page: options.page ?? 1,
    per_page: options.perPage ?? 24,
    set_id: options.setId,
    q: options.query,
  });
  return request<SealedSignalsResponse>(`/cards/sealed-signals${qs}`, {
    next: { revalidate: 300 },
  });
}

export function getTopPokemonVolume(options: {
  timeframe?: VolumeTimeframe;
  sortBy?: VolumeSortMetric;
  query?: string;
} = {}): Promise<PokemonVolumeResponse> {
  const qs = buildQueryString({
    timeframe: options.timeframe,
    sort_by: options.sortBy,
    q: options.query,
  });
  return request<PokemonVolumeResponse>(`/cards/top-pokemon-volume${qs}`, {
    next: { revalidate: 600 },
  });
}

export function getTrendingDashboard(options: {
  timeframe?: VolumeTimeframe;
  query?: string;
} = {}): Promise<TrendingDashboardResponse> {
  const qs = buildQueryString({
    timeframe: options.timeframe,
    q: options.query,
  });
  return request<TrendingDashboardResponse>(`/cards/trending${qs}`, {
    cache: "no-store",
  });
}

export function trackUserAction(data: TrackActionPayload): void {
  const body = {
    entity_type: data.entityType,
    entity_id: data.entityId,
    action: data.action ?? "click",
  };
  try {
    fetch(`${API_URL}/cards/track-action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  } catch {}
}

export function getLiveUpdates(options: {
  provider?: LiveUpdateProviderFilter;
  gradeFilter?: LiveUpdateGradeFilter;
  setId?: string;
  query?: string;
  page?: number;
  perPage?: number;
} = {}): Promise<LiveUpdatesResponse> {
  const qs = buildQueryString({
    provider: options.provider ?? "all",
    grade_filter: options.gradeFilter ?? "all",
    page: options.page ?? 1,
    per_page: options.perPage ?? 24,
    set_id: options.setId,
    q: options.query,
  });
  return request<LiveUpdatesResponse>(`/cards/live-updates${qs}`, {
    cache: "no-store",
  });
}

export function cardImageUrl(path: string): string {
  return `${API_URL}${path}`;
}
