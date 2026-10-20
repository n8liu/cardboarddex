"use client";

import { useLiveStats } from "@/lib/use-live-stats";

import { AnimatedNumber } from "@/components/ui/animated-number";

import { SectionLoadingBar } from "@/components/section-loading-bar";
import Image from "@/components/card-image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { cardImageUrl, getLiveFeed } from "@/lib/api";
import { BackToTop } from "@/components/ui/back-to-top";
import { EmptyState } from "@/components/ui/empty-state";
import { InfiniteScrollSentinel } from "@/components/ui/infinite-scroll-sentinel";
import { SearchInput } from "@/components/ui/search-input";
import type {
  LiveUpdateGradeFilter,
  LiveUpdateItem,
  LiveUpdateProviderFilter,
  LiveFeedResponse,
} from "@/types/card";
import { IMAGE_HOVER, TILE_HOVER } from "@/lib/card-hover";

type LiveUpdatesDashboardProps = {
  initialData: LiveFeedResponse;
};

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatRelativeTime(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "Recently updated";
    const diffMs = Date.now() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 30) return `${diffDays}d ago`;
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(d);
  } catch {
    return "Recently updated";
  }
}

function GradeBadge({ item }: { item: LiveUpdateItem }) {
  if (item.grading_company && item.grade) {
    const gradeStr = `${item.grading_company} ${item.grade}`;
    if (gradeStr.includes("PSA 10") || gradeStr.includes("10")) {
      return (
        <span className="inline-flex items-center rounded-md bg-purple-600 px-2 py-0.5 text-[10px] font-black text-white shadow-xs">
          {gradeStr}
        </span>
      );
    }
    if (gradeStr.includes("PSA 9") || gradeStr.includes("9")) {
      return (
        <span className="inline-flex items-center rounded-md bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-white shadow-xs">
          {gradeStr}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded-md bg-indigo-600 px-2 py-0.5 text-[10px] font-bold text-white shadow-xs">
        {gradeStr}
      </span>
    );
  }

  if (item.condition) {
    return (
      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-700">
        {item.condition}
      </span>
    );
  }

  return (
    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
      Raw / Ungraded
    </span>
  );
}

function LiveUpdateRow({ item, grid = false }: { item: LiveUpdateItem; grid?: boolean }) {
  const [imageFailed, setImageFailed] = useState(false);
  const isEbay = item.provider.toLowerCase().includes("ebay");

  return (
    <div className={`group relative flex min-w-0 flex-col justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-xs ${TILE_HOVER} ${grid ? "" : "sm:flex-row sm:items-center sm:p-4"}`}>
      {/* Left: Thumbnail & Card Details */}
      <div className={`flex min-w-0 gap-3.5 ${grid ? "flex-col" : "items-center"}`}>
        <div className={`relative shrink-0 overflow-hidden rounded-lg bg-slate-100 shadow-xs ${grid ? "aspect-[5/7] w-full" : "h-14 w-10"}`}>
          {imageFailed ? (
            <div className="flex h-full w-full items-center justify-center bg-slate-100 text-xs font-bold text-slate-400">
              {item.card_name.slice(0, 1).toUpperCase()}
            </div>
          ) : (
            <Image
              src={cardImageUrl(item.image_url)}
              alt={item.card_name}
              fill
              className={`object-contain ${grid ? "p-1.5" : "p-0.5"} ${IMAGE_HOVER}`}
              sizes={grid ? "(min-width: 1536px) 230px, (min-width: 1280px) 200px, (min-width: 1024px) 23vw, (min-width: 640px) 30vw, 45vw" : "40px"}
              onError={() => setImageFailed(true)}
            />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={`/cards/${encodeURIComponent(item.card_id)}`}
              prefetch={false}
              className="line-clamp-2 text-xs font-bold text-slate-950 transition hover:text-emerald-700 hover:underline sm:text-sm"
            >
              {item.card_name}
            </Link>
            {item.number && (
              <span className="rounded bg-slate-100 px-1.5 py-0.2 text-[10px] font-semibold text-slate-500">
                #{item.number}
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-slate-500">{item.set_name}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <GradeBadge item={item} />
            {item.printing && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                {item.printing}
              </span>
            )}
            {item.listing_title && (
              <span className="hidden max-w-[240px] truncate text-[10px] text-slate-400 lg:inline">
                “{item.listing_title}”
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Right: Price, Source & Link */}
      <div className={`flex shrink-0 gap-3 border-t border-slate-100 pt-2 ${grid ? "flex-col" : "items-center justify-between sm:flex-col sm:items-end sm:border-t-0 sm:pt-0"}`}>
        <div className={grid ? "text-left" : "text-left sm:text-right"}>
          <div className="text-base font-black tracking-tight text-slate-950">
            {formatMoney(item.price)}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-medium text-slate-400">
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                isEbay ? "bg-sky-500" : "bg-emerald-500"
              }`}
            />
            <span>{isEbay ? "eBay matched asking listing" : item.provider === "pokemonpricetracker" ? (item.update_type === "graded_aggregate" ? "PPT graded aggregate · 7-day median" : "PPT market update") : "Legacy market record"}</span>
            {item.provider === "pokemonpricetracker" && item.price_date && <span className="text-[10px] text-slate-500">Price date {item.price_date.slice(0, 10)}</span>}
            <span>•</span>
            <span>{formatRelativeTime(item.observed_at)}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {item.listing_url && (item.listing_url.startsWith("https://") || item.listing_url.startsWith("http://")) && (
            <a
              href={item.listing_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
            >
              <span>Listing</span>
              <span className="text-[10px]">↗</span>
            </a>
          )}
          <Link
            href={`/cards/${encodeURIComponent(item.card_id)}`}
            prefetch={false}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-900 transition hover:bg-emerald-600 hover:text-white"
          >
            <span>View Card</span>
            <span>→</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

export function LiveUpdatesDashboard({ initialData }: LiveUpdatesDashboardProps) {
  const searchParams = useSearchParams();
  const { stats, loading: statsLoading, error: statsError, stale: statsStale, retry: retryStats } = useLiveStats();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const p = (params.get("provider") as LiveUpdateProviderFilter) || "all";
    const validProviders: LiveUpdateProviderFilter[] = ["all", "ebay", "tcgapi", "pokemonpricetracker"];
    const provider = validProviders.includes(p) ? p : "all";

    const gf = (params.get("grade") as LiveUpdateGradeFilter) || "all";
    const validGrades: LiveUpdateGradeFilter[] = ["all", "psa10", "psa9", "graded", "raw"];
    const gradeFilter = validGrades.includes(gf) ? gf : "all";

    const vm = params.get("view");
    const viewMode: "side-by-side" | "stacked" = vm === "stacked" ? "stacked" : "side-by-side";

    const q = params.get("q")?.trim() ?? "";
    return { provider, gradeFilter, viewMode, q };
  }, [searchParams]);

  const initialParams = getUrlParams();
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);
  const [data, setData] = useState<LiveFeedResponse>(initialData);
  const [items, setItems] = useState<LiveUpdateItem[]>(initialData.items);
  const [provider, setProvider] = useState<LiveUpdateProviderFilter>(initialParams.provider);
  const [gradeFilter, setGradeFilter] = useState<LiveUpdateGradeFilter>(initialParams.gradeFilter);
  const [searchQuery, setSearchQuery] = useState(initialParams.q);
  const [page, setPage] = useState(1);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(15);
  const [isLoading, setIsLoading] = useState(initialData.items.length === 0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [secondsUntilRefresh, setSecondsUntilRefresh] = useState<number>(15);
  const [viewMode, setViewMode] = useState<"side-by-side" | "stacked">(initialParams.viewMode);
  const isFirstMount = useRef(true);

  // Sync browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const params = getUrlParams();
      setProvider(params.provider);
      setGradeFilter(params.gradeFilter);
      setViewMode(params.viewMode);
      setSearchQuery(params.q);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [getUrlParams]);

  // Keep URL in sync with active filters
  useEffect(() => {
    if (isFirstMount.current) {
      isFirstMount.current = false;
      return;
    }

    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href);
      provider !== "all" ? url.searchParams.set("provider", provider) : url.searchParams.delete("provider");
      gradeFilter !== "all" ? url.searchParams.set("grade", gradeFilter) : url.searchParams.delete("grade");
      viewMode !== "side-by-side" ? url.searchParams.set("view", viewMode) : url.searchParams.delete("view");
      searchQuery.trim() ? url.searchParams.set("q", searchQuery.trim()) : url.searchParams.delete("q");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }, 150);

    return () => window.clearTimeout(timer);
  }, [provider, gradeFilter, viewMode, searchQuery]);

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const activeRequests = useRef(0);
  const pollController = useRef<AbortController | null>(null);
  const foregroundController = useRef<AbortController | null>(null);
  const moreController = useRef<AbortController | null>(null);

  // Fetch fresh updates on filter change
  const fetchFresh = useCallback(
    async (prov: LiveUpdateProviderFilter, gf: LiveUpdateGradeFilter, q: string) => {
      pollController.current?.abort();
      foregroundController.current?.abort();
      moreController.current?.abort();
      moreController.current = null;
      setIsLoadingMore(false);
      const controller = new AbortController();
      foregroundController.current = controller;
      activeRequests.current++;
      const version = ++requestVersion.current;
      setError(null);
      setIsLoading(true);
      setPage(1);
      try {
        const res = await getLiveFeed({
          provider: prov,
          gradeFilter: gf,
          query: q.trim() || undefined,
          page: 1,
          perPage: 24,
          abortSignal: controller.signal,
        });
        if (version !== requestVersion.current || controller.signal.aborted) return;
        setData(res);
        setItems(res.items);
      } catch (err) {
        if (version !== requestVersion.current || controller.signal.aborted) return;
        setError("Could not load results. Please try again.");
        console.error("Failed fetching live updates:", err);
      } finally {
        activeRequests.current--;
        if (version === requestVersion.current) setIsLoading(false);
      }
    },
    []
  );

  // One foreground request for the active filters; ignore obsolete responses.
  useEffect(() => {
    setIsLoading(true);
    const timer = window.setTimeout(() => void fetchFresh(provider, gradeFilter, searchQuery), 250);
    return () => {
      window.clearTimeout(timer);
      requestVersion.current++;
      foregroundController.current?.abort();
      moreController.current?.abort();
    };
  }, [fetchFresh, provider, gradeFilter, searchQuery]);

  const hasMore = data.has_more;

  const loadMore = useCallback(async () => {
    if (!hasMore || isLoading || isLoadingMore) return;
    const nextPage = page + 1;
    const controller = new AbortController();
    moreController.current = controller;
    const version = requestVersion.current;
    setIsLoadingMore(true);
    activeRequests.current++;
    try {
      const res = await getLiveFeed({
        provider,
        gradeFilter,
        query: searchQuery.trim() || undefined,
        page: nextPage,
        perPage: 24,
        abortSignal: controller.signal,
      });
      if (version !== requestVersion.current || controller.signal.aborted) return;
      setItems((prev) => {
        const seen = new Set(prev.map((i) => i.id));
        const newItems = res.items.filter((i) => !seen.has(i.id));
        return [...prev, ...newItems];
      });
      setData(res);
      setPage(nextPage);
    } catch (err) {
      if (!controller.signal.aborted) console.error("Failed loading more live updates:", err);
    } finally {
      activeRequests.current--;
      if (moreController.current === controller) {
        moreController.current = null;
        setIsLoadingMore(false);
      }
    }
  }, [hasMore, isLoading, isLoadingMore, page, provider, gradeFilter, searchQuery]);

  // Background polling pauses in hidden tabs and never overlaps another read.
  useEffect(() => {
    if (!autoRefreshInterval) return;
    let remaining = autoRefreshInterval;
    let disposed = false;
    setSecondsUntilRefresh(remaining);
    const refresh = async () => {
      if (disposed || document.hidden || activeRequests.current > 0) return;
      const controller = new AbortController();
      pollController.current = controller;
      activeRequests.current++;
      const version = requestVersion.current;
      try {
        const res = await getLiveFeed({ provider, gradeFilter,
          query: searchQuery.trim() || undefined, page: 1, perPage: 24,
          abortSignal: controller.signal });
        if (disposed || controller.signal.aborted || version !== requestVersion.current) return;
        setItems((existing) => {
          const ids = new Set(existing.map((item) => item.id));
          return [...res.items.filter((item) => !ids.has(item.id)), ...existing];
        });
        // A first-page poll must not overwrite the pagination state of loaded later pages.
        setData((previous) => previous.page === 1 ? res : previous);
      } catch (error) {
        if (!controller.signal.aborted) console.error("Auto-refresh live updates error:", error);
      } finally {
        activeRequests.current--;
        if (pollController.current === controller) pollController.current = null;
      }
    };
    const visibility = () => {
      if (document.hidden) pollController.current?.abort();
      else { remaining = autoRefreshInterval; setSecondsUntilRefresh(remaining); void refresh(); }
    };
    const interval = setInterval(() => {
      if (document.hidden) return;
      remaining--;
      if (remaining <= 0) { remaining = autoRefreshInterval; void refresh(); }
      setSecondsUntilRefresh(remaining);
    }, 1000);
    timerRef.current = interval;
    document.addEventListener("visibilitychange", visibility);
    return () => {
      disposed = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", visibility);
      pollController.current?.abort();
    };
  }, [autoRefreshInterval, provider, gradeFilter, searchQuery]);

  const handleProviderChange = (newProv: LiveUpdateProviderFilter) => {
    setProvider(newProv);
  };

  const handleGradeChange = (newGf: LiveUpdateGradeFilter) => {
    setGradeFilter(newGf);
  };

  return (
    <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-8 sm:flex-row sm:items-end">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-sky-500 animate-ping" />
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-sky-700">
              Real-Time Ingestion Stream
            </span>
          </div>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-950 sm:text-4xl">
            Live Updated Items &amp; Comps
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
            Current market updates, matched eBay asking listings, and provider-reported graded sales aggregates. History backfills are excluded.
          </p>
        </div>

        {/* Top KPI Stats */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-3 rounded-xl border border-sky-500/20 bg-sky-50/70 px-3.5 py-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-600 text-xs font-mono font-bold text-white shadow-xs">
              OBS
            </span>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-sky-800">Global Observations</p>
              <p className="text-xs font-black text-slate-950">{stats ? <><AnimatedNumber value={stats.total_items} /> Comps</> : statsLoading ? "Loading totals…" : "Unavailable"}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-xl border border-purple-500/20 bg-purple-50/70 px-3.5 py-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-600 text-xs font-mono font-bold text-white shadow-xs">
              SLAB
            </span>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-purple-800">Global Graded Updates</p>
              <p className="text-xs font-black text-purple-950">{stats ? <><AnimatedNumber value={stats.graded_updates_count} /> Tracked</> : statsLoading ? "Loading totals…" : "Unavailable"}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-2 text-xs text-slate-500" aria-live="polite">
        Global totals cover all sources and filters.
        {stats && <span> Updated {new Date(stats.generated_at).toLocaleTimeString()}{statsStale ? " · Stale" : ""}.</span>}
        {statsError && <span> Totals temporarily unavailable. <button type="button" onClick={retryStats} className="underline">Retry totals</button></span>}
      </div>

      {/* Control Bar: Providers, Grades, Search & Auto-Refresh */}
      <div className="mt-8 space-y-4">
        <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs lg:flex-row lg:items-center lg:justify-between">
          {/* Source Tabs */}
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs font-semibold">
            <button
              type="button"
              onClick={() => handleProviderChange("all")}
              className={`rounded-lg px-3.5 py-1.5 transition ${
                provider === "all"
                  ? "bg-white text-slate-950 shadow-xs font-bold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All Sources
            </button>
            <button
              type="button"
              onClick={() => handleProviderChange("ebay")}
              className={`rounded-lg px-3.5 py-1.5 transition ${
                provider === "ebay"
                  ? "bg-white text-slate-950 shadow-xs font-bold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              eBay Comps
            </button>
            <button type="button" onClick={() => handleProviderChange("pokemonpricetracker")}
              className={`rounded-lg px-3 py-2 text-xs font-semibold ${provider === "pokemonpricetracker" ? "bg-emerald-100 text-emerald-800" : "text-slate-600"}`}>
              Pokémon Price Tracker
            </button>
            <button
              type="button"
              onClick={() => handleProviderChange("tcgapi")}
              className={`rounded-lg px-3.5 py-1.5 transition ${
                provider === "tcgapi"
                  ? "bg-white text-slate-950 shadow-xs font-bold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Legacy market history
            </button>
          </div>

          {/* Search Bar, View Mode & Auto-Refresh */}
          <div className="flex flex-wrap items-center gap-3">
            {/* View Mode Toggle: Side-by-Side vs Stacked */}
            <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setViewMode("side-by-side")}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition ${
                  viewMode === "side-by-side"
                    ? "bg-white font-bold text-slate-950 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
                title="Catalog-style grid"
                aria-pressed={viewMode === "side-by-side"}
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="2" width="6" height="12" rx="1.5" />
                  <rect x="9" y="2" width="6" height="12" rx="1.5" />
                </svg>
                <span>Grid</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode("stacked")}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition ${
                  viewMode === "stacked"
                    ? "bg-white font-bold text-slate-950 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
                title="Full-width list (1 column)"
                aria-pressed={viewMode === "stacked"}
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="2" width="14" height="5" rx="1" />
                  <rect x="1" y="9" width="14" height="5" rx="1" />
                </svg>
                <span>Full Width</span>
              </button>
            </div>

            {/* Auto-Refresh Ticker */}
            <div className="flex items-center gap-2 rounded-xl bg-slate-50 border border-slate-200 px-3 py-1.5 text-xs text-slate-600">
              <span className="relative flex h-2 w-2">
                {autoRefreshInterval && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                )}
                <span
                  className={`relative inline-flex h-2 w-2 rounded-full ${
                    autoRefreshInterval ? "bg-emerald-500" : "bg-slate-300"
                  }`}
                />
              </span>
              <span className="text-[11px] font-medium">
                {autoRefreshInterval ? `Auto-refresh: ${secondsUntilRefresh}s` : "Auto-refresh: Paused"}
              </span>
              <button
                type="button"
                onClick={() => setAutoRefreshInterval((prev) => (prev ? null : 15))}
                className="text-[10px] font-bold uppercase text-sky-600 hover:underline"
              >
                {autoRefreshInterval ? "Pause" : "Resume"}
              </button>
            </div>

            {/* Search Input */}
            <div className="w-full sm:w-64">
              <SearchInput
                value={searchQuery}
                onChange={(val) => {
                  setSearchQuery(val);
                }}
                onSubmit={() => fetchFresh(provider, gradeFilter, searchQuery)}
                placeholder="Search card, set, or comp..."
              />
            </div>
          </div>
        </div>

        {/* Grade Filter Sub-Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-bold uppercase tracking-wider text-slate-400">Grade:</span>
          {(
            [
              { id: "all", label: "All Items" },
              { id: "psa10", label: "PSA 10 Gem Mint" },
              { id: "psa9", label: "PSA 9 Mint" },
              { id: "graded", label: "All Graded Slabs" },
              { id: "raw", label: "Raw / Ungraded" },
            ] as { id: LiveUpdateGradeFilter; label: string }[]
          ).map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => handleGradeChange(g.id)}
              className={`rounded-lg px-3 py-1 text-xs font-bold transition shadow-2xs ${
                gradeFilter === g.id
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
              }`}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>

      {/* Live Stream List / Side-by-Side Grid */}
      {error && <div role="alert" className="my-4 text-sm text-rose-700">{error} <button type="button" className="underline" onClick={() => void fetchFresh(provider, gradeFilter, searchQuery)}>Retry</button></div>}
      {isLoading && <SectionLoadingBar label="Loading latest market updates…" />}
      <div
        className={
          viewMode === "side-by-side"
            ? "mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6"
            : "mt-6 space-y-2.5"
        }
      >
        {isLoading ? (
          viewMode === "side-by-side" ? (
            Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="aspect-[3/5] w-full animate-pulse rounded-2xl bg-slate-200/70" />
            ))
          ) : (
            Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-20 w-full animate-pulse rounded-2xl bg-slate-200/70" />
            ))
          )
        ) : items.length === 0 ? (
          <div className={viewMode === "side-by-side" ? "col-span-full" : ""}>
            <EmptyState
              title="No live updates found matching your filters"
              description="Try switching the source to 'All Sources' or clearing the search query."
              onReset={() => {
                setProvider("all");
                setGradeFilter("all");
                setSearchQuery("");
              }}
            />
          </div>
        ) : (
          items.map((item) => <LiveUpdateRow key={item.id} item={item} grid={viewMode === "side-by-side"} />)
        )}
      </div>

      <p className="mt-4 text-xs text-slate-500">{items.length.toLocaleString()} records loaded</p>

      {/* Infinite Scroll Sentinel */}
      <InfiniteScrollSentinel
        hasMore={hasMore}
        isLoading={isLoadingMore}
        onLoadMore={() => void loadMore()}
        itemName="records"
        totalLoaded={items.length}
      />

      {/* Floating Back To Top Button */}
      <BackToTop />
    </div>
  );
}
