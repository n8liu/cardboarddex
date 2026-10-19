import type { HomeOverview, HomeStats } from "@/types/home";
import type { MarketHistory, SalesActivity, GradedSalesActivity } from "@/types/market-data";
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
  LiveFeedResponse,
  LiveStatsResponse,
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

export type CacheMetadata = {
  status: string;
  generatedAt: number | null;
  expiresAt: number | null;
};
export type CacheOptions = {
  abortSignal?: AbortSignal;
  bypassCache?: boolean;
  onCache?: (metadata: CacheMetadata) => void;
};
interface CacheEntry<T> {
  data: T;
  expiresAt: number;
  metadata: CacheMetadata;
}
const clientCache = new Map<string, CacheEntry<unknown>>();
type SharedRequest = {
  promise: Promise<CacheEntry<unknown>>;
  controller: AbortController;
  subscribers: number;
  settled: boolean;
};
const clientInflight = new Map<string, SharedRequest>();
const CLIENT_CACHE_MAX_ENTRIES = 64;
let cacheGeneration = 0;

function browserTtl(path: string): number {
  const route = path.split("?")[0];
  if (route === "/cards/sets") return 300_000;
  if (["/cards/search", "/cards/market-movers", "/cards/grading-profit",
    "/cards/sealed-signals", "/home/overview"].includes(route) ||
    route.startsWith("/cards/pokemon/") || /^\/cards\/sets\/[^/]+\/stats$/.test(route)) return 60_000;
  return 0;
}

export function clearClientCache(): void {
  cacheGeneration++;
  clientCache.clear();
  // Existing subscribers still own their requests; old completions cannot refill the cache.
  clientInflight.clear();
}

function subscribe<T>(shared: SharedRequest, options: CacheOptions): Promise<T> {
  shared.subscribers++;
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = () => {
      if (done) return false;
      done = true;
      options.abortSignal?.removeEventListener("abort", abort);
      shared.subscribers--;
      if (!shared.settled && shared.subscribers === 0) shared.controller.abort();
      return true;
    };
    const abort = () => {
      if (finish()) reject(options.abortSignal?.reason ?? new DOMException("Aborted", "AbortError"));
    };
    shared.promise.then((entry) => {
      if (!done) options.onCache?.(entry.metadata);
      if (finish()) resolve(entry.data as T);
    }, (error) => { if (finish()) reject(error); });
    if (options.abortSignal?.aborted) abort();
    else options.abortSignal?.addEventListener("abort", abort, { once: true });
  });
}

async function request<T>(path: string, options: RequestInit = {}, policy: CacheOptions = {}): Promise<T> {
  const fullUrl = `${resolveApiUrl()}${path.startsWith("/") ? "" : "/"}${path}`;
  const isClient = typeof window !== "undefined";
  const isGet = !options.method || options.method.toUpperCase() === "GET";
  const ttl = isClient && isGet && options.cache !== "no-store" ? browserTtl(path) : 0;
  const subscriber = { ...policy, abortSignal: policy.abortSignal ?? options.signal ?? undefined };
  if (subscriber.abortSignal?.aborted) throw subscriber.abortSignal.reason ?? new DOMException("Aborted", "AbortError");
  if (ttl && !policy.bypassCache) {
    const cached = clientCache.get(fullUrl);
    if (cached && Date.now() < cached.expiresAt) {
      subscriber.onCache?.(cached.metadata);
      return cached.data as T;
    }
    clientCache.delete(fullUrl);
    const pending = clientInflight.get(fullUrl);
    if (pending && !pending.controller.signal.aborted) return subscribe<T>(pending, subscriber);
  }
  const generation = cacheGeneration;
  const controller = new AbortController();
  const timeoutMs = isClient ? 15_000 : 6_000;
  const timeoutId = setTimeout(() => controller.abort(new Error(`CardboardDex API ${path} timed out after ${timeoutMs}ms`)), timeoutMs);
  const shared: SharedRequest = { controller, subscribers: 0, settled: false, promise: Promise.resolve(null!) };
  shared.promise = (async () => {
    try {
      const response = await fetch(fullUrl, {
        ...options,
        ...(isClient && ttl ? { cache: "no-cache" as const } : {}),
        // Backend timestamps own freshness; do not stack a Next data cache over them.
        ...(!isClient && browserTtl(path) ? { cache: "no-store" as const, next: undefined } : {}),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`CardboardDex API ${path} returned ${response.status}`);
      const data = await response.json();
      const parseDate = (name: string) => {
        const value = response.headers.get(name);
        const parsed = value ? Date.parse(value) : NaN;
        return Number.isFinite(parsed) ? parsed : null;
      };
      const metadata: CacheMetadata = {
        status: response.headers.get("X-Cache-Status") ?? "unknown",
        generatedAt: parseDate("X-Cache-Generated-At"),
        expiresAt: parseDate("X-Cache-Expires-At"),
      };
      const entry = { data, metadata, expiresAt: Math.min(Date.now() + ttl, metadata.expiresAt ?? Infinity) };
      if (ttl && clientInflight.get(fullUrl) === shared && generation === cacheGeneration && !controller.signal.aborted &&
          !metadata.status.startsWith("stale") && entry.expiresAt > Date.now()) {
        for (const [key, value] of clientCache) if (value.expiresAt <= Date.now()) clientCache.delete(key);
        clientCache.delete(fullUrl);
        clientCache.set(fullUrl, entry);
        while (clientCache.size > CLIENT_CACHE_MAX_ENTRIES) clientCache.delete(clientCache.keys().next().value!);
      }
      return entry;
    } finally {
      shared.settled = true;
      clearTimeout(timeoutId);
      if (clientInflight.get(fullUrl) === shared) clientInflight.delete(fullUrl);
    }
  })();
  if (ttl) clientInflight.set(fullUrl, shared);
  return subscribe<T>(shared, subscriber);
}


type SearchCardOptions = CacheOptions & {
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
    : { cache: "no-cache" };
  return request<CardSummary[]>(`/cards/search${qs}`, reqOptions, options);
}

export function getSetStats(
  setId: string,
  options: CacheOptions & {
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
    : { cache: "no-cache" };
  return request<SetStats>(`/cards/sets/${encodeURIComponent(setId)}/stats${qs}`, reqOptions, options);
}

export function getPokemonCards(
  pokemonName: string,
  options: CacheOptions & {
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
    { cache: "no-cache" }, options
  );
}

export function getCardSets(game?: GameLanguage, options: CacheOptions = {}): Promise<CardSetOption[]> {
  const qs = buildQueryString({
    game: game && game !== "all" ? game : undefined,
  });
  return request<CardSetOption[]>(`/cards/sets${qs}`, {
    next: { revalidate: 86400 },
  }, options);

}

export function getMarketMovers(options: CacheOptions & {
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
  }, options);
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

export function getGradingProfit(options: CacheOptions & {
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
  }, options);
}

export function getSealedSignals(options: CacheOptions & {
  game?: GameLanguage;
  era?: "newer" | "older";
  period?: 30 | 90;
  signal?: SealedSignalType;
  productType?: SealedProductType;
  sortBy?: SealedSortOption;
  setId?: string;
  query?: string;
  page?: number;
  perPage?: number;
} = {}): Promise<SealedSignalsResponse> {
  const qs = buildQueryString({
    era: options.era,
    game: options.game && options.game !== "all" ? options.game : undefined,
    period: options.period ?? 30,
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
  }, options);
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
  abortSignal?: AbortSignal;
  timeframe?: VolumeTimeframe;
  query?: string;
} = {}): Promise<TrendingDashboardResponse> {
  const qs = buildQueryString({
    include_observation_volume: false,
    timeframe: options.timeframe,
    q: options.query,
  });
  return request<TrendingDashboardResponse>(`/cards/trending${qs}`, {
    cache: "no-store",
    signal: options.abortSignal,
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

export function getLiveUpdates(options: CacheOptions & {
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
  }, options);
}

export function getLiveFeed(options: CacheOptions & {
  provider?: LiveUpdateProviderFilter;
  gradeFilter?: LiveUpdateGradeFilter;
  setId?: string;
  query?: string;
  page?: number;
  perPage?: number;
} = {}): Promise<LiveFeedResponse> {
  const qs = buildQueryString({
    provider: options.provider ?? "all",
    grade_filter: options.gradeFilter ?? "all",
    page: options.page ?? 1,
    per_page: options.perPage ?? 24,
    set_id: options.setId,
    q: options.query,
  });
  return request<LiveFeedResponse>(`/cards/live-updates/feed${qs}`, {
    cache: "no-store",
  }, options);
}

export function getLiveStats(options: CacheOptions = {}): Promise<LiveStatsResponse> {
  return request<LiveStatsResponse>("/cards/live-updates/stats", { cache: "no-store" }, options);
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

export function getMarketHistory(cardId: string, days: 30 | 90 | 365 = 30, signal?: AbortSignal): Promise<MarketHistory> {
  return request(`/cards/${encodeURIComponent(cardId)}/market-history?days=${days}`, { signal, cache: "no-store" });
}
export function getSalesActivity(days: 7 | 30 | 90 = 30, query = "", signal?: AbortSignal): Promise<SalesActivity> {
  return request(`/market/sales-activity${buildQueryString({ days, q: query })}`, { signal, cache: "no-store" });
}

export function getHomeOverview(signal?: AbortSignal, options: CacheOptions = {}): Promise<HomeOverview> {
  return request("/home/overview", { signal, cache: "no-cache" }, options);
}

export function getHomeStats(signal?: AbortSignal): Promise<HomeStats> {
  return request("/home/stats", { signal, cache: "no-store" });
}

export function getGradedSalesActivity(query = "", signal?: AbortSignal): Promise<GradedSalesActivity> {
  return request(`/market/graded-sales-activity${buildQueryString({ q: query })}`, { signal, cache: "no-store" });
}
