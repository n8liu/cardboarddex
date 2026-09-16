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
  SetStats,
} from "@/types/card";
import type { PokemonCardsResponse } from "@/types/pokemon";
import type { PortfolioValuationResponse } from "@/types/binder";

const LEGACY_AWS_API_URL =
  "https://ca-72b07140e03c4335a2d28f0e1c81f161.ecs.us-west-2.on.aws";
export const PRODUCTION_API_URL = "https://api.cardboarddex.app";

function isLegacyAwsApiUrl(url: string): boolean {
  return url.replace(/\/+$/, "").toLowerCase() === LEGACY_AWS_API_URL;
}

function isProductionApiSubdomain(url: string): boolean {
  return /^https:\/\/api\.cardboarddex\.app\/?$/i.test(url);
}

function isInvalidOrLocalhost(url: string | undefined): boolean {
  if (!url) return true;
  const lower = url.toLowerCase();
  return (
    lower.includes("localhost") ||
    lower.includes("127.0.0.1") ||
    (lower.includes("cardboarddex.app") && !isProductionApiSubdomain(url)) ||
    isLegacyAwsApiUrl(url)
  );
}

export function resolveApiUrl(): string {
  let url =
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    process.env.DEFAULT_API_URL?.trim() ||
    "";

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    const isProdHost =
      host.endsWith(".pages.dev") ||
      host === "cardboarddex.pages.dev" ||
      host === "cardboarddex.app" ||
      host.endsWith(".cardboarddex.app");
    if (isProdHost) {
      if (isInvalidOrLocalhost(url)) {
        return PRODUCTION_API_URL;
      }
    }
  }

  const isProdEnv =
    process.env.NODE_ENV === "production" ||
    Boolean(process.env.CF_PAGES);

  if (isProdEnv) {
    if (isInvalidOrLocalhost(url)) {
      return PRODUCTION_API_URL;
    }
  }

  if (
    (url.includes("cardboarddex.app") && !isProductionApiSubdomain(url)) ||
    isLegacyAwsApiUrl(url)
  ) {
    return PRODUCTION_API_URL;
  }

  return (url || "http://localhost:8000").replace(/\/+$/, "");
}

export const API_URL = resolveApiUrl();
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

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const clientCache = new Map<string, CacheEntry<unknown>>();
const clientInflight = new Map<string, Promise<unknown>>();
const CLIENT_CACHE_TTL_MS = 60_000; // 60s memory cache for browser GET requests

export function clearClientCache(): void {
  clientCache.clear();
  clientInflight.clear();
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const baseUrl = resolveApiUrl();
  const fullUrl = `${baseUrl}${path.startsWith("/") ? "" : "/"}${path}`;

  const isClient = typeof window !== "undefined";
  const isGet = !options.method || options.method.toUpperCase() === "GET";

  if (isClient && isGet) {
    const cached = clientCache.get(fullUrl);
    if (cached && Date.now() - cached.timestamp < CLIENT_CACHE_TTL_MS) {
      return cached.data as T;
    }
    const inflight = clientInflight.get(fullUrl);
    if (inflight) {
      return inflight as Promise<T>;
    }
  }

  const fetchPromise = (async () => {
    try {
      const response = await fetch(fullUrl, options);
      if (!response.ok) {
        throw new Error(`CardboardDex API ${path} returned ${response.status}`);
      }
      const data = (await response.json()) as T;
      if (isClient && isGet) {
        clientCache.set(fullUrl, { data, timestamp: Date.now() });
      }
      return data;
    } finally {
      if (isClient && isGet) {
        clientInflight.delete(fullUrl);
      }
    }
  })();

  if (isClient && isGet) {
    clientInflight.set(fullUrl, fetchPromise);
  }

  return fetchPromise;
}


type SearchCardOptions = {
  limit?: number;
  offset?: number;
  setId?: string;
  sortBy?: CardSort;
  hideSealed?: boolean;
  sealedOnly?: boolean;
  game?: GameLanguage;
  minPrice?: number | null;
  maxPrice?: number | null;
  revalidate?: number;
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
    min_price: options.minPrice != null && options.minPrice > 0 ? options.minPrice : undefined,
    max_price: options.maxPrice != null ? options.maxPrice : undefined,
  });
  const isServer = typeof window === "undefined";
  const reqOptions: RequestInit = isServer
    ? { next: { revalidate: options.revalidate ?? 60 } }
    : { cache: "no-store" };
  return request<CardSummary[]>(`/cards/search${qs}`, reqOptions);
}

export function getSetStats(
  setId: string,
  options: {
    q?: string;
    hideSealed?: boolean;
    sealedOnly?: boolean;
    game?: GameLanguage;
    minPrice?: number | null;
    maxPrice?: number | null;
    revalidate?: number;
  } = {}
): Promise<SetStats> {
  const qs = buildQueryString({
    q: options.q,
    hide_sealed: options.hideSealed === false ? "false" : "true",
    sealed_only: options.sealedOnly ? "true" : undefined,
    game: options.game && options.game !== "all" ? options.game : undefined,
    min_price: options.minPrice != null && options.minPrice > 0 ? options.minPrice : undefined,
    max_price: options.maxPrice != null ? options.maxPrice : undefined,
  });
  const isServer = typeof window === "undefined";
  const reqOptions: RequestInit = isServer
    ? { next: { revalidate: options.revalidate ?? 120 } }
    : { cache: "no-store" };
  return request<SetStats>(`/cards/sets/${encodeURIComponent(setId)}/stats${qs}`, reqOptions);
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
  try {
    return await request<CardDetail>(`/cards/${encodeURIComponent(cardId)}${qs}`, {
      cache: "no-store",
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes("404")) {
      return null;
    }
    throw err;
  }
}

export async function getCardPricing(cardId: string): Promise<CardPricing | null> {
  try {
    return await request<CardPricing>(`/cards/${encodeURIComponent(cardId)}/prices?days=365`, {
      cache: "no-store",
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes("404")) {
      return null;
    }
    throw err;
  }
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
    const baseUrl = resolveApiUrl();
    fetch(`${baseUrl}/cards/track-action`, {
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

export async function getPortfolioValuation(
  cardIds: string[],
  days: number = 365
): Promise<PortfolioValuationResponse> {
  if (!cardIds || cardIds.length === 0) {
    return {
      total_cards: 0,
      total_current_value: 0,
      currency: "USD",
      delta_24h_amount: 0,
      delta_24h_percent: 0,
      delta_7d_amount: 0,
      delta_7d_percent: 0,
      delta_30d_amount: 0,
      delta_30d_percent: 0,
      highest_value_card: null,
      cards: [],
      history: [],
    };
  }

  return request<PortfolioValuationResponse>("/cards/portfolio-valuation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ card_ids: cardIds, days }),
    cache: "no-store",
  });
}

export function cardImageUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const baseUrl = resolveApiUrl();
  return `${baseUrl}${path.startsWith("/") ? "" : "/"}${path}`;
}
