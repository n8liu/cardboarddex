"use client";

import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { cardImageUrl, getGradingProfit } from "@/lib/api";
import { BackToTop } from "@/components/ui/back-to-top";
import { EmptyState } from "@/components/ui/empty-state";
import { InfiniteScrollSentinel } from "@/components/ui/infinite-scroll-sentinel";
import { SearchInput } from "@/components/ui/search-input";
import type {
  GradingProfitItem,
  GradingProfitResponse,
  GradingSortOption,
} from "@/types/card";

type PresetFilter = "all" | "safe" | "high_profit" | "high_roi" | "budget" | "high_spread";

type GradingProfitDashboardProps = {
  initialData: GradingProfitResponse;
};

export function GradingProfitDashboard({ initialData }: GradingProfitDashboardProps) {
  const searchParams = useSearchParams();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const pf = (params.get("preset") as PresetFilter) || "all";
    const validPresets: PresetFilter[] = ["all", "safe", "high_profit", "high_roi", "budget", "high_spread"];
    const presetFilter = validPresets.includes(pf) ? pf : "all";

    const sb = (params.get("sort") as GradingSortOption) || (initialData.sort_by as GradingSortOption) || "psa10_profit_desc";
    const validSorts: GradingSortOption[] = ["psa10_profit_desc", "psa10_roi_desc", "psa9_profit_desc", "psa9_roi_desc", "ev_desc", "spread_desc", "raw_price_asc", "raw_price_desc"];
    const sortBy = validSorts.includes(sb) ? sb : "psa10_profit_desc";

    const tg = (params.get("grade") as "all" | "psa10" | "psa9") || "all";
    const validGrades = ["all", "psa10", "psa9"];
    const targetGrade = validGrades.includes(tg) ? tg : "all";

    const feeRaw = params.get("fee");
    const gradingFee = feeRaw && !isNaN(Number(feeRaw)) ? Number(feeRaw) : (initialData.grading_fee || 24.99);

    const q = params.get("q")?.trim() ?? "";
    return { presetFilter, sortBy, targetGrade, gradingFee, q };
  }, [initialData.grading_fee, initialData.sort_by, searchParams]);

  const initialParams = getUrlParams();
  const [data, setData] = useState<GradingProfitResponse>(initialData);
  const [items, setItems] = useState<GradingProfitItem[]>(initialData.items);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // Filter & State controls
  const [gradingFee, setGradingFee] = useState<number>(initialParams.gradingFee);
  const [sortBy, setSortBy] = useState<GradingSortOption>(initialParams.sortBy);
  const [targetGrade, setTargetGrade] = useState<"all" | "psa10" | "psa9">(initialParams.targetGrade);
  const [presetFilter, setPresetFilter] = useState<PresetFilter>(initialParams.presetFilter);
  const [searchQuery, setSearchQuery] = useState(initialParams.q);
  const [debouncedQuery, setDebouncedQuery] = useState(initialParams.q);
  const [page, setPage] = useState(initialData.page || 1);
  const [perPage] = useState(initialData.per_page || 24);
  const isFirstMount = useRef(true);

  // Sync browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const params = getUrlParams();
      setPresetFilter(params.presetFilter);
      setSortBy(params.sortBy);
      setTargetGrade(params.targetGrade);
      setGradingFee(params.gradingFee);
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
      presetFilter !== "all" ? url.searchParams.set("preset", presetFilter) : url.searchParams.delete("preset");
      sortBy !== "psa10_profit_desc" ? url.searchParams.set("sort", sortBy) : url.searchParams.delete("sort");
      targetGrade !== "all" ? url.searchParams.set("grade", targetGrade) : url.searchParams.delete("grade");
      gradingFee !== 24.99 ? url.searchParams.set("fee", String(gradingFee)) : url.searchParams.delete("fee");
      debouncedQuery.trim() ? url.searchParams.set("q", debouncedQuery.trim()) : url.searchParams.delete("q");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }, 150);

    return () => window.clearTimeout(timer);
  }, [presetFilter, sortBy, targetGrade, gradingFee, debouncedQuery]);

  // Debounce search query
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 250);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Derived filter arguments from preset
  const { minProfit, psa9SafeOnly } = useMemo(() => {
    let minP: number | undefined = undefined;
    let safeOnly = false;

    if (presetFilter === "safe") {
      safeOnly = true;
    } else if (presetFilter === "high_profit") {
      minP = 100;
    }

    return { minProfit: minP, psa9SafeOnly: safeOnly };
  }, [presetFilter]);

  // Fetch fresh data when filters change
  const fetchFresh = useCallback(async () => {
    setLoading(true);
    setPage(1);
    try {
      const res = await getGradingProfit({
        gradingFee,
        sortBy,
        targetGrade,
        minProfit,
        maxRawPrice: presetFilter === "budget" ? 25 : undefined,
        minSpread: presetFilter === "high_spread" ? 10 : undefined,
        psa9SafeOnly,
        query: debouncedQuery.trim() || undefined,
        page: 1,
        perPage,
      });
      setData(res);
      setItems(res.items);
    } catch (err) {
      console.error("Failed fetching grading profit opportunities:", err);
    } finally {
      setLoading(false);
    }
  }, [gradingFee, sortBy, targetGrade, minProfit, presetFilter, psa9SafeOnly, debouncedQuery, perPage]);

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
      const res = await getGradingProfit({
        gradingFee,
        sortBy,
        targetGrade,
        minProfit,
        maxRawPrice: presetFilter === "budget" ? 25 : undefined,
        minSpread: presetFilter === "high_spread" ? 10 : undefined,
        psa9SafeOnly,
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
      console.error("Failed loading more grading opportunities:", err);
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loading, loadingMore, page, gradingFee, sortBy, targetGrade, minProfit, presetFilter, psa9SafeOnly, debouncedQuery, perPage]);

  // Local preset quick-filters apply
  const handlePresetClick = (preset: PresetFilter) => {
    const next = presetFilter === preset ? "all" : preset;
    setPresetFilter(next);
    setPage(1);
    if (next === "high_roi") {
      setSortBy("psa10_roi_desc");
    } else if (next === "budget") {
      setSortBy("raw_price_asc");
    } else if (next === "high_spread") {
      setSortBy("spread_desc");
    } else if (next === "safe") {
      setSortBy("psa9_profit_desc");
    } else {
      setSortBy("psa10_profit_desc");
    }
  };

  // Preset fee options
  const feePresets = [
    { label: "PSA Bulk ($19)", fee: 19.0 },
    { label: "PSA Value ($24.99)", fee: 24.99 },
    { label: "PSA Regular ($40)", fee: 40.0 },
    { label: "CGC / SGC ($15)", fee: 15.0 },
  ];

  // Stats calculation
  const stats = useMemo(() => {
    if (!items.length) return { avgSpread: "0.0x", safeCount: 0, topProfit: "$0", topRoi: "0%" };

    const spreads = items
      .map((i) => i.spread_multiplier)
      .filter((s): s is number => typeof s === "number" && s > 0);
    const avgSpreadVal = spreads.length ? spreads.reduce((a, b) => a + b, 0) / spreads.length : 0;
    const safeCountVal = items.filter((i) => i.psa9_safe).length;

    const maxProfit = Math.max(...items.map((i) => i.psa10_profit || 0));
    const maxRoi = Math.max(...items.map((i) => i.psa10_roi || 0));

    return {
      avgSpread: `${avgSpreadVal.toFixed(1)}x`,
      safeCount: safeCountVal,
      topProfit: maxProfit > 0 ? `+$${maxProfit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "$0",
      topRoi: maxRoi > 0 ? `+${maxRoi.toFixed(0)}%` : "0%",
    };
  }, [items]);

  return (
    <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8 font-mono">
      {/* Header & Simulator Bar */}
      <div className="flex flex-col justify-between gap-6 border-b border-slate-200/80 pb-6 lg:flex-row lg:items-end">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
              <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
              <span>ARBITRAGE CALCULATOR</span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-500">PSA 10 &amp; 9 COMP ENGINE</span>
            </span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-950 uppercase">
            Grading Profitability
          </h1>
          <p className="mt-2 max-w-2xl text-xs sm:text-sm text-slate-600 leading-relaxed">
            Calculated net dollar spreads and expected returns between raw cards and graded slabs.
          </p>
        </div>

        {/* Interactive Fee Simulator Inline */}
        <div className="flex flex-col gap-2 rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs sm:min-w-[320px]">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
              Grading Fee Simulator
            </span>
            <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-black text-indigo-700 border border-indigo-200/60 font-mono">
              ${gradingFee.toFixed(2)} / card
            </span>
          </div>

          <div className="flex items-center gap-2.5">
            <span className="text-[10px] font-bold text-slate-400">$10</span>
            <input
              type="range"
              min="10"
              max="100"
              step="1"
              value={gradingFee}
              onChange={(e) => setGradingFee(parseFloat(e.target.value))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-slate-200 accent-slate-900"
              aria-label="Grading Fee Slider"
            />
            <span className="text-[10px] font-bold text-slate-400">$100</span>
          </div>

          <div className="flex items-center gap-1 pt-0.5">
            {feePresets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => setGradingFee(preset.fee)}
                className={`flex-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold transition ${
                  Math.abs(gradingFee - preset.fee) < 0.01
                    ? "bg-slate-900 text-white shadow-xs"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                ${preset.fee}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Telemetry Stats Grid */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Top PSA 10 Profit
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-emerald-600">
            {stats.topProfit}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            Net after ${gradingFee.toFixed(0)} fee
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Top Expected ROI
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-emerald-600">
            {stats.topRoi}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            Highest return percentage
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Average Multiplier
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-slate-950">
            {stats.avgSpread}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            PSA 10 vs. Raw Price
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            PSA 9 Safe Floor
          </div>
          <div className="mt-1 text-xl font-black tracking-tight text-indigo-600">
            {stats.safeCount} Cards
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            Profit even at PSA 9 grade
          </div>
        </div>
      </div>

      {/* Filter and Control Bar */}
      <div className="mt-6 space-y-3 rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs">
        {/* Preset Quick-Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => handlePresetClick("all")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              presetFilter === "all"
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All Opportunities
          </button>
          <button
            type="button"
            onClick={() => handlePresetClick("safe")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              presetFilter === "safe"
                ? "bg-emerald-600 text-white"
                : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
            }`}
          >
            PSA 9 Safe Floor
          </button>
          <button
            type="button"
            onClick={() => handlePresetClick("high_profit")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              presetFilter === "high_profit"
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            $100+ Net Profit
          </button>
          <button
            type="button"
            onClick={() => handlePresetClick("high_roi")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              presetFilter === "high_roi"
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Highest ROI %
          </button>
          <button
            type="button"
            onClick={() => handlePresetClick("budget")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              presetFilter === "budget"
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Budget Raw (&lt;$25)
          </button>
          <button
            type="button"
            onClick={() => handlePresetClick("high_spread")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              presetFilter === "high_spread"
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            10x+ Multiplier
          </button>
        </div>

        {/* Detailed Controls Grid */}
        <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search card name or set..."
          />

          <div className="flex flex-wrap items-center gap-3">
            {/* Target Grade Selector */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="target-grade-select" className="text-xs font-bold text-slate-600">Grade:</label>
              <select
                id="target-grade-select"
                value={targetGrade}
                onChange={(e) => {
                  setTargetGrade(e.target.value as "all" | "psa10" | "psa9");
                  setPage(1);
                }}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 transition hover:bg-slate-100 focus:border-indigo-500 focus:outline-none"
              >
                <option value="all">All Grades</option>
                <option value="psa10">PSA 10 Only</option>
                <option value="psa9">PSA 9 Only</option>
              </select>
            </div>

            {/* Sort Selector */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="sort-by-select" className="text-xs font-bold text-slate-600">Sort By:</label>
              <select
                id="sort-by-select"
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value as GradingSortOption);
                  setPage(1);
                }}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 transition hover:bg-slate-100 focus:border-indigo-500 focus:outline-none"
              >
                <option value="psa10_profit_desc">Highest PSA 10 Net Profit ($)</option>
                <option value="psa10_roi_desc">Highest PSA 10 ROI (%)</option>
                <option value="psa9_profit_desc">Highest PSA 9 Net Profit ($)</option>
                <option value="psa9_roi_desc">Highest PSA 9 ROI (%)</option>
                <option value="ev_desc">Risk-Adjusted Expected Value ($)</option>
                <option value="spread_desc">Highest PSA 10 / Raw Multiplier</option>
                <option value="raw_price_asc">Lowest Raw Entry Cost ($)</option>
                <option value="raw_price_desc">Highest Raw Value ($)</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Card Results Grid */}
      {loading ? (
        <div className="flex min-h-[400px] items-center justify-center rounded-3xl border border-slate-200 bg-white p-12">
          <div className="flex flex-col items-center gap-3">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
            <span className="text-xs font-semibold text-slate-500">Calculating grading profit margins...</span>
          </div>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No grading opportunities found"
          description="Try adjusting your search query, grading fee, or switching the filter to 'All Opportunities'."
          onReset={() => {
            setSearchQuery("");
            setPresetFilter("all");
            setTargetGrade("all");
            setSortBy("psa10_profit_desc");
          }}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => {
            const rawCost = item.raw_price;
            const fee = item.grading_fee;
            const totalBuyIn = rawCost + fee;

            return (
              <div
                key={item.card_id}
                className="group relative flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs transition duration-150 hover:border-slate-400 hover:shadow-md"
              >
                <div>
                  {/* Top Bar: Safe Tag & Spread Multiplier */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700">
                      {item.rarity || "Standard"}
                    </span>

                    <div className="flex items-center gap-1.5">
                      {item.psa9_safe && (
                        <span className="rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200/60 px-2 py-0.5 text-[10px] font-bold">
                          PSA 9 Safe
                        </span>
                      )}
                      {item.spread_multiplier && (
                        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-black text-slate-800">
                          {item.spread_multiplier}x Spread
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Thumbnail & Core Info */}
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
                          {item.set_name} {item.number ? `#${item.number}` : ""}
                        </div>
                        <h2 className="text-xs sm:text-sm font-bold text-slate-950 line-clamp-2 leading-snug">
                          <Link href={`/cards/${encodeURIComponent(item.card_id)}`} className="hover:underline group-hover:text-slate-900">
                            {item.name}
                          </Link>
                        </h2>
                      </div>

                      {/* Compact Raw + Fee summary */}
                      <div className="mt-2 text-[10px] text-slate-500 font-mono">
                        <span>Raw: ${item.raw_price.toFixed(2)}</span>
                        <span className="text-slate-300"> · </span>
                        <span>Total: ${totalBuyIn.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Grade Targets: PSA 10 & PSA 9 comparison */}
                  <div className="mt-3.5 space-y-2">
                    {/* PSA 10 Target */}
                    {typeof item.psa10_price === "number" && typeof item.psa10_profit === "number" && (
                      <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-2.5 font-mono">
                        <div className="flex items-center justify-between">
                          <span className="rounded-md bg-slate-900 px-1.5 py-0.5 text-[10px] font-black text-white">
                            PSA 10
                          </span>
                          <span className="text-xs font-bold text-slate-900">
                            ${item.psa10_price.toFixed(2)}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center justify-between text-[11px]">
                          <span className="font-semibold text-emerald-700">
                            {item.psa10_profit >= 0 ? "+" : ""}${item.psa10_profit.toFixed(2)} Net
                          </span>
                          {typeof item.psa10_roi === "number" && (
                            <span className="rounded-md bg-emerald-50 border border-emerald-200/60 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                              +{item.psa10_roi.toFixed(0)}% ROI
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* PSA 9 Target / Floor */}
                    {typeof item.psa9_price === "number" && typeof item.psa9_profit === "number" && (
                      <div className="rounded-xl border border-slate-200/80 bg-white p-2.5 font-mono">
                        <div className="flex items-center justify-between">
                          <span className="rounded-md bg-slate-700 px-1.5 py-0.5 text-[10px] font-black text-white">
                            PSA 9
                          </span>
                          <span className="text-xs font-bold text-slate-900">
                            ${item.psa9_price.toFixed(2)}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center justify-between text-[11px]">
                          <span
                            className={`font-semibold ${
                              item.psa9_profit >= 0 ? "text-emerald-700" : "text-rose-600"
                            }`}
                          >
                            {item.psa9_profit >= 0 ? "+" : ""}${item.psa9_profit.toFixed(2)} Net
                          </span>
                          {typeof item.psa9_roi === "number" && (
                            <span
                              className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                                item.psa9_roi >= 0
                                  ? "bg-slate-100 text-slate-700"
                                  : "bg-rose-50 text-rose-700 border border-rose-200/60"
                              }`}
                            >
                              {item.psa9_roi >= 0 ? "+" : ""}{item.psa9_roi.toFixed(0)}% ROI
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Footer Link */}
                <div className="mt-3 border-t border-slate-100 pt-2.5">
                  <Link
                    href={`/cards/${encodeURIComponent(item.card_id)}`}
                    className="flex w-full items-center justify-between text-xs font-bold text-slate-700 transition hover:text-slate-950"
                  >
                    <span>View Comps &amp; History</span>
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
        itemName="opportunities"
        totalLoaded={items.length}
        totalItems={data.total_cards}
      />

      {/* Floating Back To Top Button */}
      <BackToTop />
    </div>
  );
}
