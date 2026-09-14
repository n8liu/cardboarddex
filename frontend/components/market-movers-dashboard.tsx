"use client";

import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { cardImageUrl, getMarketMovers } from "@/lib/api";
import { BackToTop } from "@/components/ui/back-to-top";
import { InfiniteScrollSentinel } from "@/components/ui/infinite-scroll-sentinel";
import { SearchInput } from "@/components/ui/search-input";
import type { MarketMoverItem, MarketMoversResponse, MoverDirection, MoverPeriod } from "@/types/card";

type MarketMoversDashboardProps = {
  initialData: MarketMoversResponse;
};

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercentage(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Recently updated";
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

function MoverCard({ item }: { item: MarketMoverItem }) {
  const [imageFailed, setImageFailed] = useState(false);
  const isUp = item.direction === "up" || item.price_change_percentage >= 0;

  return (
    <Link
      href={`/cards/${encodeURIComponent(item.card_id)}`}
      prefetch={false}
      className="group relative flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs transition duration-150 hover:border-slate-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-slate-900"
    >
      <div className="flex gap-3.5">
        {/* Card Image Thumbnail */}
        <div className="relative h-24 w-18 shrink-0 overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-1">
          {imageFailed ? (
            <div className="flex h-full w-full items-center justify-center text-xs font-bold text-slate-400">
              {item.name.slice(0, 1).toUpperCase()}
            </div>
          ) : (
            <Image
              src={cardImageUrl(item.image_url)}
              alt={item.name}
              fill
              className="object-contain transition duration-200 group-hover:scale-105"
              sizes="80px"
              onError={() => setImageFailed(true)}
            />
          )}
        </div>

        {/* Card Details */}
        <div className="flex min-w-0 flex-1 flex-col">
          <h3 className="line-clamp-2 text-xs sm:text-sm font-bold leading-snug text-slate-950 group-hover:text-slate-900">
            {item.name}
          </h3>
          <p className="mt-0.5 truncate text-[11px] font-medium text-slate-500">{item.set_name}</p>

          <div className="mt-2 flex flex-wrap items-center gap-1 text-[10px] font-semibold text-slate-600">
            {item.printing && (
              <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5">
                {item.printing}
              </span>
            )}
            {item.rarity && (
              <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-slate-500">
                {item.rarity}
              </span>
            )}
            {item.number && (
              <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-500">
                #{item.number}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Pricing & Change Footer */}
      <div className="mt-3.5 flex items-end justify-between border-t border-slate-100 pt-2.5">
        <div>
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Market</span>
          <p className="font-mono text-sm sm:text-base font-black tracking-tight text-slate-950">
            {formatMoney(item.market_price)}
          </p>
        </div>

        <div className="text-right">
          <span
            className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-black ${
              isUp
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200/60"
                : "bg-rose-50 text-rose-700 border border-rose-200/60"
            }`}
          >
            <span>{isUp ? "▲" : "▼"}</span>
            <span>{formatPercentage(item.price_change_percentage)}</span>
          </span>
          {item.price_change_amount !== null && item.price_change_amount !== undefined && (
            <p className="mt-0.5 text-[10px] text-slate-400 font-mono">
              {item.price_change_amount >= 0 ? "+" : ""}
              {formatMoney(item.price_change_amount)}
            </p>
          )}
        </div>
      </div>

      <div className="mt-2 text-[10px] text-slate-400">
        Updated {formatRelativeTime(item.last_updated_at)}
      </div>
    </Link>
  );
}

export function MarketMoversDashboard({ initialData }: MarketMoversDashboardProps) {
  const searchParams = useSearchParams();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const p = (params.get("period") as MoverPeriod) || initialData.period || "24h";
    const validPeriods: MoverPeriod[] = ["24h", "7d", "30d"];
    const period = validPeriods.includes(p) ? p : "24h";
    const d = (params.get("direction") as MoverDirection) || "all";
    const validDirections: MoverDirection[] = ["all", "up", "down"];
    const direction = validDirections.includes(d) ? d : "all";
    const g = params.get("game");
    const game: "pokemon" | "pokemon-japan" = g === "pokemon-japan" ? "pokemon-japan" : "pokemon";
    const q = params.get("q")?.trim() ?? "";
    return { period, direction, game, q };
  }, [initialData.period, searchParams]);

  const initialParams = getUrlParams();
  const [data, setData] = useState<MarketMoversResponse>(initialData);
  const [gainers, setGainers] = useState<MarketMoverItem[]>(initialData.gainers);
  const [losers, setLosers] = useState<MarketMoverItem[]>(initialData.losers);
  const [period, setPeriod] = useState<MoverPeriod>(initialParams.period);
  const [direction, setDirection] = useState<MoverDirection>(initialParams.direction);
  const [game, setGame] = useState<"pokemon" | "pokemon-japan">(initialParams.game);
  const [searchTerm, setSearchTerm] = useState(initialParams.q);
  const [page, setPage] = useState(initialData.page || 1);
  const [perPage] = useState(initialData.per_page || 24);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isInitialized = useRef(false);

  const fetchFresh = useCallback(
    async (selectedPeriod: MoverPeriod, selectedGame: "pokemon" | "pokemon-japan") => {
      setIsLoading(true);
      setError(null);
      setPage(1);
      try {
        const response = await getMarketMovers({
          direction: "all",
          period: selectedPeriod,
          game: selectedGame,
          page: 1,
          perPage,
        });
        setData(response);
        setGainers(response.gainers);
        setLosers(response.losers);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load market movers");
      } finally {
        setIsLoading(false);
      }
    },
    [perPage]
  );

  useEffect(() => {
    const handlePopState = () => {
      const params = getUrlParams();
      setPeriod(params.period);
      setDirection(params.direction);
      setGame(params.game);
      setSearchTerm(params.q);
      void fetchFresh(params.period, params.game);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [getUrlParams, fetchFresh]);

  // Keep URL in sync with active filters
  useEffect(() => {
    if (!isInitialized.current) {
      isInitialized.current = true;
      if (
        initialParams.period !== (initialData.period || "24h") ||
        initialParams.game !== "pokemon" ||
        ((!initialData.gainers || initialData.gainers.length === 0) &&
          (!initialData.losers || initialData.losers.length === 0))
      ) {
        void fetchFresh(initialParams.period, initialParams.game);
      }
      return;
    }

    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href);
      period !== "24h" ? url.searchParams.set("period", period) : url.searchParams.delete("period");
      direction !== "all" ? url.searchParams.set("direction", direction) : url.searchParams.delete("direction");
      game !== "pokemon" ? url.searchParams.set("game", game) : url.searchParams.delete("game");
      searchTerm.trim() ? url.searchParams.set("q", searchTerm.trim()) : url.searchParams.delete("q");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }, 150);

    return () => window.clearTimeout(timer);
  }, [period, direction, game, searchTerm, fetchFresh, initialParams.period, initialParams.game, initialData.period]);

  const handlePeriodChange = (newPeriod: MoverPeriod) => {
    setPeriod(newPeriod);
    void fetchFresh(newPeriod, game);
  };

  const handleGameChange = (newGame: "pokemon" | "pokemon-japan") => {
    setGame(newGame);
    void fetchFresh(period, newGame);
  };

  const hasMore = page < (data.total_pages || 1);

  const loadMore = useCallback(async () => {
    if (!hasMore || isLoading || isLoadingMore) return;
    const nextPage = page + 1;
    setIsLoadingMore(true);
    try {
      const response = await getMarketMovers({
        direction: "all",
        period,
        game,
        page: nextPage,
        perPage,
      });
      setGainers((prev) => {
        const seen = new Set(prev.map((i) => `${i.card_id}-${i.printing}`));
        const newItems = response.gainers.filter((i) => !seen.has(`${i.card_id}-${i.printing}`));
        return [...prev, ...newItems];
      });
      setLosers((prev) => {
        const seen = new Set(prev.map((i) => `${i.card_id}-${i.printing}`));
        const newItems = response.losers.filter((i) => !seen.has(`${i.card_id}-${i.printing}`));
        return [...prev, ...newItems];
      });
      setData(response);
      setPage(nextPage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load more market movers");
    } finally {
      setIsLoadingMore(false);
    }
  }, [hasMore, isLoading, isLoadingMore, page, period, game, perPage]);

  const filteredGainers = useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    if (!term) return gainers;
    return gainers.filter(
      (item) =>
        item.name.toLowerCase().includes(term) ||
        item.set_name.toLowerCase().includes(term) ||
        (item.number && item.number.toLowerCase().includes(term)),
    );
  }, [gainers, searchTerm]);

  const filteredLosers = useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    if (!term) return losers;
    return losers.filter(
      (item) =>
        item.name.toLowerCase().includes(term) ||
        item.set_name.toLowerCase().includes(term) ||
        (item.number && item.number.toLowerCase().includes(term)),
    );
  }, [losers, searchTerm]);

  const topGainer = gainers[0] ?? null;
  const topLoser = losers[0] ?? null;

  return (
    <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8 font-mono">
      {/* Header Banner */}
      <div className="border-b border-slate-200/80 pb-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>MOMENTUM RADAR</span>
            <span className="text-slate-300">|</span>
            <span className="text-slate-500">TCG MARKET PRICES</span>
          </span>
        </div>
        <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-950 uppercase">
          Market Movers
        </h1>
        <p className="mt-2 max-w-2xl text-xs sm:text-sm text-slate-600 leading-relaxed">
          Price surges and drops across 24-hour, 7-day, and 30-day velocity windows.
        </p>
      </div>

      {/* Telemetry Stats Grid */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Top Surge ({period})
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-emerald-600">
            {topGainer ? `+${topGainer.price_change_percentage}%` : "—"}
          </div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500">
            {topGainer ? `${topGainer.name} (${formatMoney(topGainer.market_price)})` : "No gainers recorded"}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Steepest Drop ({period})
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-rose-600">
            {topLoser ? `${topLoser.price_change_percentage}%` : "—"}
          </div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500">
            {topLoser ? `${topLoser.name} (${formatMoney(topLoser.market_price)})` : "No drops recorded"}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Total Gainers
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-slate-950">
            {data.total_gainers || 0}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            {period} window velocity
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Total Drops
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-slate-950">
            {data.total_losers || 0}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            {period} window velocity
          </div>
        </div>
      </div>

      {/* Control Bar: Period, Direction & Filter */}
      <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs sm:flex-row sm:items-center sm:justify-between">
        {/* Region & Time Period Tabs */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Region Tabs */}
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs font-bold">
            <button
              type="button"
              onClick={() => handleGameChange("pokemon")}
              className={`rounded-lg px-3 py-1.5 transition ${
                game === "pokemon"
                  ? "bg-white text-slate-950 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              English
            </button>
            <button
              type="button"
              onClick={() => handleGameChange("pokemon-japan")}
              className={`rounded-lg px-3 py-1.5 transition ${
                game === "pokemon-japan"
                  ? "bg-white text-red-950 shadow-xs font-black"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Japanese
            </button>
          </div>

          {/* Time Period Tabs */}
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs font-semibold">
            {(["24h", "7d", "30d"] as MoverPeriod[]).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => handlePeriodChange(p)}
                className={`rounded-lg px-3 py-1.5 transition ${
                  period === p
                    ? "bg-white text-slate-950 shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {p === "24h" ? "24h" : p === "7d" ? "7d" : "30d"}
              </button>
            ))}
          </div>
        </div>

        {/* View Mode & Search */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setDirection("all")}
              className={`rounded-lg px-3 py-1.5 transition ${
                direction === "all" ? "bg-white text-slate-950 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Split View
            </button>
            <button
              type="button"
              onClick={() => setDirection("up")}
              className={`flex items-center gap-1 rounded-lg px-3 py-1.5 transition ${
                direction === "up" ? "bg-emerald-600 text-white shadow-sm" : "text-emerald-700 hover:bg-emerald-50"
              }`}
            >
              <span>Gainers</span>
              <span className="rounded-full bg-emerald-800/40 px-1.5 py-0.2 text-[10px] text-white">
                {data.total_gainers || filteredGainers.length}
              </span>
            </button>
            <button
              type="button"
              onClick={() => setDirection("down")}
              className={`flex items-center gap-1 rounded-lg px-3 py-1.5 transition ${
                direction === "down" ? "bg-rose-600 text-white shadow-sm" : "text-rose-700 hover:bg-rose-50"
              }`}
            >
              <span>Losers</span>
              <span className="rounded-full bg-rose-800/40 px-1.5 py-0.2 text-[10px] text-white">
                {data.total_losers || filteredLosers.length}
              </span>
            </button>
          </div>

          <div className="w-full sm:w-56">
            <SearchInput
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder="Filter by card or set..."
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}

      {/* Main Movers Display */}
      <div className={`mt-8 ${isLoading ? "opacity-40 transition-opacity" : "transition-opacity"}`}>
        {direction === "all" ? (
          <div className="grid gap-10 lg:grid-cols-2">
            {/* Top Gainers Section */}
            <div>
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-100 text-xs font-bold text-emerald-700">
                    ▲
                  </span>
                  <h2 className="text-lg font-bold text-slate-950">Top Price Gainers</h2>
                </div>
                <span className="text-xs font-semibold text-emerald-700">
                  {data.total_gainers || filteredGainers.length} total gainers
                </span>
              </div>

              {filteredGainers.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
                  No gainers found for this period.
                </div>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {filteredGainers.map((item) => (
                    <MoverCard key={`gain-${item.card_id}-${item.printing}`} item={item} />
                  ))}
                </div>
              )}
            </div>

            {/* Top Losers Section */}
            <div>
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-rose-100 text-xs font-bold text-rose-700">
                    ▼
                  </span>
                  <h2 className="text-lg font-bold text-slate-950">Top Price Drops</h2>
                </div>
                <span className="text-xs font-semibold text-rose-700">
                  {data.total_losers || filteredLosers.length} total drops
                </span>
              </div>

              {filteredLosers.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
                  No price drops recorded for this period.
                </div>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {filteredLosers.map((item) => (
                    <MoverCard key={`loss-${item.card_id}-${item.printing}`} item={item} />
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : direction === "up" ? (
          <div>
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-xl font-bold text-slate-950">
                Top Price Gainers ({period === "24h" ? "24 Hours" : period === "7d" ? "7 Days" : "30 Days"})
              </h2>
              <span className="font-mono text-xs font-medium text-slate-500">
                {filteredGainers.length} of {data.total_gainers || filteredGainers.length} cards loaded
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {filteredGainers.map((item) => (
                <MoverCard key={`gain-${item.card_id}-${item.printing}`} item={item} />
              ))}
            </div>
          </div>
        ) : (
          <div>
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-xl font-bold text-slate-950">
                Top Price Drops ({period === "24h" ? "24 Hours" : period === "7d" ? "7 Days" : "30 Days"})
              </h2>
              <span className="font-mono text-xs font-medium text-slate-500">
                {filteredLosers.length} of {data.total_losers || filteredLosers.length} cards loaded
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {filteredLosers.map((item) => (
                <MoverCard key={`loss-${item.card_id}-${item.printing}`} item={item} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Infinite Scroll Sentinel */}
      <InfiniteScrollSentinel
        hasMore={hasMore}
        isLoading={isLoadingMore}
        onLoadMore={() => void loadMore()}
        itemName="movers"
        totalLoaded={
          direction === "up"
            ? filteredGainers.length
            : direction === "down"
              ? filteredLosers.length
              : filteredGainers.length + filteredLosers.length
        }
        totalItems={
          direction === "up"
            ? data.total_gainers
            : direction === "down"
              ? data.total_losers
              : (data.total_gainers || 0) + (data.total_losers || 0)
        }
      />

      {/* Floating Back To Top Button */}
      <BackToTop />
    </div>
  );
}
