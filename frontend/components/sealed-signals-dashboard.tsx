"use client";

import Image from "@/components/card-image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { cardImageUrl, getSealedSignals } from "@/lib/api";
import { BackToTop } from "@/components/ui/back-to-top";
import { EmptyState } from "@/components/ui/empty-state";
import { InfiniteScrollSentinel } from "@/components/ui/infinite-scroll-sentinel";
import { SearchInput } from "@/components/ui/search-input";
import type {
  SealedProductType,
  SealedSignalsResponse,
  SealedSignalItem,
  SealedSignalType,
  SealedSortOption,
} from "@/types/card";

type SealedSignalsDashboardProps = {
  initialData: SealedSignalsResponse;
};

export function SealedSignalsDashboard({ initialData }: SealedSignalsDashboardProps) {
  const searchParams = useSearchParams();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const s = (params.get("signal") as SealedSignalType) || (initialData.signal_filter as SealedSignalType) || "all";
    const validSignals: SealedSignalType[] = ["all", "strong_buy", "buy", "hold", "underperform"];
    const signal = validSignals.includes(s) ? s : "all";

    const pt = (params.get("type") as SealedProductType) || (initialData.product_type_filter as SealedProductType) || "all";
    const validTypes: SealedProductType[] = ["all", "booster_box", "etb", "bundle", "case", "pack", "blister", "collection"];
    const productType = validTypes.includes(pt) ? pt : "all";

    const sb = (params.get("sort") as SealedSortOption) || (initialData.sort_by as SealedSortOption) || "score_desc";
    const validSorts: SealedSortOption[] = ["score_desc", "supply_asc", "momentum_desc", "price_desc", "price_asc", "age_desc"];
    const sortBy = validSorts.includes(sb) ? sb : "score_desc";

    const q = params.get("q")?.trim() ?? "";
    return { signal, productType, sortBy, q };
  }, [initialData.product_type_filter, initialData.signal_filter, initialData.sort_by, searchParams]);

  const initialParams = getUrlParams();
  const [data, setData] = useState<SealedSignalsResponse>(initialData);
  const [items, setItems] = useState<SealedSignalItem[]>(initialData.items);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // Filters & State
  const [signal, setSignal] = useState<SealedSignalType>(initialParams.signal);
  const [productType, setProductType] = useState<SealedProductType>(initialParams.productType);
  const [sortBy, setSortBy] = useState<SealedSortOption>(initialParams.sortBy);
  const [searchQuery, setSearchQuery] = useState(initialParams.q);
  const [debouncedQuery, setDebouncedQuery] = useState(initialParams.q);
  const [page, setPage] = useState(initialData.page || 1);
  const [perPage] = useState(initialData.per_page || 24);
  const isFirstMount = useRef(true);

  // Sync browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const params = getUrlParams();
      setSignal(params.signal);
      setProductType(params.productType);
      setSortBy(params.sortBy);
      setSearchQuery(params.q);
      setDebouncedQuery(params.q);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [getUrlParams]);

  // Keep URL in sync with active filters
  useEffect(() => {
    if (isFirstMount.current) return;

    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href);
      signal !== "all" ? url.searchParams.set("signal", signal) : url.searchParams.delete("signal");
      productType !== "all" ? url.searchParams.set("type", productType) : url.searchParams.delete("type");
      sortBy !== "score_desc" ? url.searchParams.set("sort", sortBy) : url.searchParams.delete("sort");
      debouncedQuery.trim() ? url.searchParams.set("q", debouncedQuery.trim()) : url.searchParams.delete("q");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }, 150);

    return () => window.clearTimeout(timer);
  }, [signal, productType, sortBy, debouncedQuery]);

  // Debounce search query
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 250);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Fetch fresh data when filters change
  const fetchFresh = useCallback(async () => {
    setLoading(true);
    setPage(1);
    try {
      const res = await getSealedSignals({
        signal,
        productType,
        sortBy,
        query: debouncedQuery.trim() || undefined,
        page: 1,
        perPage,
      });
      setData(res);
      setItems(res.items);
    } catch (err) {
      console.error("Failed fetching sealed investment signals:", err);
    } finally {
      setLoading(false);
    }
  }, [signal, productType, sortBy, debouncedQuery, perPage]);

  useEffect(() => {
    if (isFirstMount.current) {
      isFirstMount.current = false;
      return;
    }
    fetchFresh();
  }, [fetchFresh]);

  const hasMore = page < data.total_pages;

  const loadMore = useCallback(async () => {
    if (!hasMore || loading || loadingMore) return;
    const nextPage = page + 1;
    setLoadingMore(true);
    try {
      const res = await getSealedSignals({
        signal,
        productType,
        sortBy,
        query: debouncedQuery.trim() || undefined,
        page: nextPage,
        perPage,
      });
      setItems((prev) => {
        const seen = new Set(prev.map((i) => i.card_id));
        const newItems = res.items.filter((i) => !seen.has(i.card_id));
        return [...prev, ...newItems];
      });
      setData(res);
      setPage(nextPage);
    } catch (err) {
      console.error("Failed loading more sealed items:", err);
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loading, loadingMore, page, signal, productType, sortBy, debouncedQuery, perPage]);

  // Stats calculation
  const stats = useMemo(() => {
    if (!items.length) {
      return {
        strongBuyCount: data.strong_buy_count || 0,
        lowSupplyCount: 0,
        avgScore: "0",
        topGain30d: "0%",
      };
    }

    const lowSupply = items.filter((i) => i.total_listings > 0 && i.total_listings < 15).length;
    const scores = items.map((i) => i.signal_score);
    const avgScoreVal = scores.reduce((a, b) => a + b, 0) / scores.length;

    const max30d = Math.max(...items.map((i) => i.price_change_30d || 0));

    return {
      strongBuyCount: data.strong_buy_count || 0,
      lowSupplyCount: lowSupply,
      avgScore: avgScoreVal.toFixed(0),
      topGain30d: max30d > 0 ? `+${max30d.toFixed(1)}%` : "0%",
    };
  }, [data.strong_buy_count, items]);

  return (
    <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8 font-mono">
      {/* Header */}
      <div className="border-b border-slate-200/80 pb-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
            <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
            <span>INVESTMENT SIGNALS</span>
            <span className="text-slate-300">|</span>
            <span className="text-slate-500">4-FACTOR QUANTITATIVE MODEL</span>
          </span>
        </div>
        <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-950 uppercase">
          Sealed Investment Signals
        </h1>
        <p className="mt-2 max-w-2xl text-xs sm:text-sm text-slate-600 leading-relaxed">
          Quantitative 0–100 buy ratings evaluating supply float, liquidity, velocity, and vintage age.
        </p>
      </div>

      {/* Telemetry Stats Grid */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Strong Buys
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-emerald-600">
            {data.strong_buy_count || 0}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            Top conviction rating
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Low Supply Float
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-amber-600">
            {stats.lowSupplyCount}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            &lt; 15 active listings
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Avg Signal Score
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-slate-950">
            {stats.avgScore}/100
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            Across {data.total_items} items
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Top 30d Momentum
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-emerald-600">
            {stats.topGain30d}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            30-day price gain
          </div>
        </div>
      </div>

      {/* Filter and Control Bar */}
      <div className="mt-6 space-y-3 rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs">
        {/* Signal Tier Buttons */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setSignal("all")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              signal === "all"
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All Signals ({data.total_items})
          </button>
          <button
            type="button"
            onClick={() => setSignal("strong_buy")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              signal === "strong_buy"
                ? "bg-emerald-600 text-white"
                : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
            }`}
          >
            Strong Buy ({data.strong_buy_count})
          </button>
          <button
            type="button"
            onClick={() => setSignal("buy")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              signal === "buy"
                ? "bg-amber-600 text-white"
                : "bg-amber-50 text-amber-700 hover:bg-amber-100"
            }`}
          >
            Buy ({data.buy_count})
          </button>
          <button
            type="button"
            onClick={() => setSignal("hold")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              signal === "hold"
                ? "bg-slate-700 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Hold ({data.hold_count})
          </button>
          <button
            type="button"
            onClick={() => setSignal("underperform")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              signal === "underperform"
                ? "bg-rose-600 text-white"
                : "bg-rose-50 text-rose-700 hover:bg-rose-100"
            }`}
          >
            Underperform ({data.underperform_count})
          </button>
        </div>

        {/* Product Type Filters */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <span className="text-xs font-bold text-slate-500 mr-1">Category:</span>
          {[
            { id: "all", label: "All Products" },
            { id: "booster_box", label: "Booster Boxes" },
            { id: "etb", label: "Elite Trainer Boxes (ETBs)" },
            { id: "bundle", label: "Booster Bundles" },
            { id: "case", label: "Cases" },
            { id: "blister", label: "Blisters" },
            { id: "pack", label: "Booster Packs" },
            { id: "collection", label: "Collections & Tins" },
          ].map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => {
                setProductType(cat.id as SealedProductType);
                setPage(1);
              }}
              className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
                productType === cat.id
                  ? "bg-amber-600 text-white shadow-sm"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Detailed Search & Sort Controls */}
        <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search sealed item (e.g. 151 Booster Bundle, Evolving Skies ETB)..."
          />

          <div className="flex items-center gap-3">
            {/* Sort Selector */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="sealed-sort-by-select" className="text-xs font-bold text-slate-600">Sort By:</label>
              <select
                id="sealed-sort-by-select"
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value as SealedSortOption);
                  setPage(1);
                }}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 transition hover:bg-slate-100 focus:border-amber-500 focus:outline-none"
              >
                <option value="score_desc">Highest Buy Signal Score (0-100)</option>
                <option value="supply_asc">Lowest Supply / Tightest Float</option>
                <option value="momentum_desc">Highest 30D Momentum Velocity</option>
                <option value="price_desc">Highest Market Price ($)</option>
                <option value="price_asc">Lowest Market Price ($)</option>
                <option value="age_desc">Oldest Set Vintage (Out of Print)</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Sealed Products Grid */}
      {loading ? (
        <div className="flex min-h-[400px] items-center justify-center rounded-3xl border border-slate-200 bg-white p-12">
          <div className="flex flex-col items-center gap-3">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-amber-200 border-t-amber-600" />
            <span className="text-xs font-semibold text-slate-500">Computing quantitative supply &amp; demand signals...</span>
          </div>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No sealed products match your criteria"
          description="Try adjusting your search query, product type filter, or selecting 'All Signals'."
          onReset={() => {
            setSearchQuery("");
            setSignal("all");
            setProductType("all");
            setSortBy("score_desc");
          }}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => {
            const isStrongBuy = item.signal_label === "STRONG BUY";
            const isBuy = item.signal_label === "BUY";
            const isHold = item.signal_label === "HOLD";

            return (
              <div
                key={item.card_id}
                className="group relative flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs transition duration-150 hover:border-slate-400 hover:shadow-md"
              >
                <div>
                  {/* Top Bar: Product Type & Signal Tag */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700">
                      {item.product_type}
                    </span>

                    <div className="flex items-center gap-1.5">
                      <span
                        className={`rounded-md px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${
                          isStrongBuy
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200/60"
                            : isBuy
                            ? "bg-amber-50 text-amber-700 border border-amber-200/60"
                            : isHold
                            ? "bg-slate-100 text-slate-700 border border-slate-200"
                            : "bg-rose-50 text-rose-700 border border-rose-200/60"
                        }`}
                      >
                        {item.signal_label}
                      </span>
                      <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-black text-slate-800">
                        {item.signal_score}
                      </span>
                    </div>
                  </div>

                  {/* Thumbnail & Product Details */}
                  <div className="flex gap-3.5">
                    <div className="relative h-24 w-18 shrink-0 overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-1">
                      <Image
                        src={cardImageUrl(item.image_url)}
                        alt={item.name}
                        fill
                        sizes="80px"
                        className="object-contain transition duration-200 group-hover:scale-105"
                      />
                    </div>

                    <div className="flex flex-1 flex-col justify-between overflow-hidden">
                      <div>
                        <div className="text-[11px] font-semibold text-slate-400 truncate">
                          {item.set_name}
                        </div>
                        <h2 className="text-xs sm:text-sm font-bold text-slate-950 line-clamp-2 leading-snug">
                          <Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} className="hover:underline group-hover:text-slate-900">
                            {item.name}
                          </Link>
                        </h2>
                        {item.set_age_months > 0 && (
                          <span className="mt-1 inline-block text-[10px] text-slate-500 font-mono">
                            {item.set_age_months}mo vintage · {item.set_age_months >= 24 ? "Out of Print" : "Active Era"}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 4-Factor Telemetry Strip */}
                  <div className="mt-3.5 flex items-center justify-between rounded-xl bg-slate-50 px-2.5 py-1.5 border border-slate-100 text-[10px] font-bold text-slate-600 font-mono">
                    <span title="Supply Score (out of 30)">SUP {item.supply_score}/30</span>
                    <span className="text-slate-300">·</span>
                    <span title="Demand Score (out of 25)">DEM {item.demand_score}/25</span>
                    <span className="text-slate-300">·</span>
                    <span title="Velocity Score (out of 25)">VEL {item.momentum_score}/25</span>
                    <span className="text-slate-300">·</span>
                    <span title="Vintage Score (out of 20)">AGE {item.vintage_score}/20</span>
                  </div>

                  {/* Pricing & Supply Float */}
                  <div className="mt-3 flex items-end justify-between border-t border-slate-100 pt-2.5">
                    <div>
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Market</span>
                      <div className="flex items-baseline gap-1.5">
                        <span className="font-mono text-sm sm:text-base font-black tracking-tight text-slate-950">
                          ${item.market_price.toFixed(2)}
                        </span>
                        {typeof item.price_change_30d === "number" && (
                          <span
                            className={`text-[10px] font-bold ${
                              item.price_change_30d >= 0 ? "text-emerald-600" : "text-rose-600"
                            }`}
                          >
                            {item.price_change_30d >= 0 ? "+" : ""}
                            {item.price_change_30d.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="text-right">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Float</span>
                      <p className="font-mono text-xs font-bold text-slate-800">
                        {item.total_listings > 0 ? `${item.total_listings} Listings` : "Low Float"}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Footer Link */}
                <div className="mt-3 border-t border-slate-100 pt-2.5">
                  <Link
                    href={`/cards/${encodeURIComponent(item.card_id)}`}
                    prefetch={false}
                    className="flex w-full items-center justify-between text-xs font-bold text-slate-700 transition hover:text-slate-950"
                  >
                    <span>View Comps &amp; Details</span>
                    <span>→</span>
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Infinite Scroll Sentinel */}
      <InfiniteScrollSentinel
        hasMore={hasMore}
        isLoading={loadingMore}
        onLoadMore={() => void loadMore()}
        itemName="sealed products"
        totalLoaded={items.length}
        totalItems={data.total_items}
      />

      {/* Floating Back To Top Button */}
      <BackToTop />
    </div>
  );
}
