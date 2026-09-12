"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { ShopOnEbayButton, type EbaySearchCardTarget } from "@/components/shop-ebay-button";
import type { CardPricing, PriceObservation } from "@/types/card";
import type { ChartPoint } from "@/components/price-history-chart";

const PriceHistoryChart = dynamic(
  () => import("@/components/price-history-chart").then((mod) => mod.PriceHistoryChart),
  {
    loading: () => (
      <div className="flex h-64 w-full items-center justify-center rounded-lg border border-dashed border-zinc-200 bg-zinc-50/50 animate-pulse text-xs text-zinc-400">
        Loading price history chart...
      </div>
    ),
  },
);

type PriceDashboardProps = {
  pricing: CardPricing;
  cardMeta?: EbaySearchCardTarget;
};

function timestamp(item: PriceObservation): number {
  const obsTime = item.observed_at ? new Date(item.observed_at).getTime() : 0;
  const provTime = item.provider_updated_at ? new Date(item.provider_updated_at).getTime() : 0;
  return Math.max(obsTime, provTime);
}

function latestByVariant(observations: PriceObservation[]): PriceObservation[] {
  const latest = new Map<string, PriceObservation>();
  for (const observation of observations) {
    // For eBay comps, keep individual verified listings distinct by provider_card_id;
    // for catalog providers like TCG API, deduplicate by variant printing.
    const key = isEbayObservation(observation)
      ? `${observation.provider}:${observation.variant_id}:${observation.provider_card_id}`
      : `${observation.provider}:${observation.variant_id}`;
    const current = latest.get(key);
    if (!current || timestamp(observation) >= timestamp(current)) latest.set(key, observation);
  }
  return [...latest.values()];
}

function providerName(value: string): string {
  if (value.toLowerCase().includes("ebay")) return "eBay listings";
  if (value === "tcgapi") return "TCG API";
  return value;
}

function isEbayObservation(item: PriceObservation): boolean {
  return item.provider.toLowerCase().includes("ebay");
}

function buildMultiSeriesHistory(observations: PriceObservation[]): {
  history: ChartPoint[];
  obsCounts: { raw: number; tcg: number; psa10: number; psa9: number };
} {
  const dates = new Set<string>();
  const rawByDate = new Map<string, { total: number; count: number }>();
  const tcgByDate = new Map<string, { total: number; count: number }>();
  const psa10ByDate = new Map<string, { total: number; count: number }>();
  const psa9ByDate = new Map<string, { total: number; count: number }>();

  let rawObsCount = 0;
  let tcgObsCount = 0;
  let psa10ObsCount = 0;
  let psa9ObsCount = 0;

  for (const obs of observations) {
    if (!obs.price || obs.price <= 0) continue;
    const date = (obs.provider_updated_at ?? obs.observed_at ?? "").slice(0, 10);
    if (!date) continue;

    if (isEbayObservation(obs)) {
      dates.add(date);
      if (!obs.grading_company) {
        rawObsCount++;
        const cur = rawByDate.get(date) ?? { total: 0, count: 0 };
        rawByDate.set(date, { total: cur.total + obs.price, count: cur.count + 1 });
      } else if (obs.grading_company.toUpperCase() === "PSA") {
        if (obs.grade === 10) {
          psa10ObsCount++;
          const cur = psa10ByDate.get(date) ?? { total: 0, count: 0 };
          psa10ByDate.set(date, { total: cur.total + obs.price, count: cur.count + 1 });
        } else if (obs.grade === 9) {
          psa9ObsCount++;
          const cur = psa9ByDate.get(date) ?? { total: 0, count: 0 };
          psa9ByDate.set(date, { total: cur.total + obs.price, count: cur.count + 1 });
        }
      }
    } else if (obs.provider === "tcgapi" || obs.provider.toLowerCase().includes("tcg")) {
      dates.add(date);
      tcgObsCount++;
      const cur = tcgByDate.get(date) ?? { total: 0, count: 0 };
      tcgByDate.set(date, { total: cur.total + obs.price, count: cur.count + 1 });
    }
  }

  // If no specific series dates found, fallback to all observations
  if (dates.size === 0) {
    for (const obs of observations) {
      const date = (obs.provider_updated_at ?? obs.observed_at ?? "").slice(0, 10);
      if (!date || !obs.price) continue;
      dates.add(date);
      rawObsCount++;
      const cur = rawByDate.get(date) ?? { total: 0, count: 0 };
      rawByDate.set(date, { total: cur.total + obs.price, count: cur.count + 1 });
    }
  }

  if (dates.size === 0) {
    return {
      history: [],
      obsCounts: { raw: 0, tcg: 0, psa10: 0, psa9: 0 },
    };
  }

  const today = new Date().toISOString().slice(0, 10);
  dates.add(today);

  // If earliest date is today, anchor from yesterday so a continuous line segment is drawn
  const earliestDate = [...dates].sort((a, b) => a.localeCompare(b))[0];
  if (earliestDate === today) {
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    dates.add(yesterday);
  }

  const sortedDates = [...dates].sort((a, b) => a.localeCompare(b));

  // Determine initial prices for each series
  let initialRaw: number | null = null;
  let initialTcg: number | null = null;
  let initialPsa10: number | null = null;
  let initialPsa9: number | null = null;

  for (const d of sortedDates) {
    const raw = rawByDate.get(d);
    if (raw && initialRaw === null) initialRaw = Math.round((raw.total / raw.count) * 100) / 100;
    const tcg = tcgByDate.get(d);
    if (tcg && initialTcg === null) initialTcg = Math.round((tcg.total / tcg.count) * 100) / 100;
    const psa10 = psa10ByDate.get(d);
    if (psa10 && initialPsa10 === null) initialPsa10 = Math.round((psa10.total / psa10.count) * 100) / 100;
    const psa9 = psa9ByDate.get(d);
    if (psa9 && initialPsa9 === null) initialPsa9 = Math.round((psa9.total / psa9.count) * 100) / 100;
  }

  // Forward-fill to today's date so every active series displays a continuous line
  let lastRaw: number | null = rawObsCount === 1 ? initialRaw : null;
  let lastTcg: number | null = tcgObsCount === 1 ? initialTcg : null;
  let lastPsa10: number | null = psa10ObsCount === 1 ? initialPsa10 : null;
  let lastPsa9: number | null = psa9ObsCount === 1 ? initialPsa9 : null;

  const points: ChartPoint[] = sortedDates.map((date) => {
    const raw = rawByDate.get(date);
    if (raw) lastRaw = Math.round((raw.total / raw.count) * 100) / 100;

    const tcg = tcgByDate.get(date);
    if (tcg) lastTcg = Math.round((tcg.total / tcg.count) * 100) / 100;

    const psa10 = psa10ByDate.get(date);
    if (psa10) lastPsa10 = Math.round((psa10.total / psa10.count) * 100) / 100;

    const psa9 = psa9ByDate.get(date);
    if (psa9) lastPsa9 = Math.round((psa9.total / psa9.count) * 100) / 100;

    return {
      date,
      rawPrice: lastRaw,
      tcgPrice: lastTcg,
      psa10Price: lastPsa10,
      psa9Price: lastPsa9,
    };
  });

  return {
    history: points,
    obsCounts: {
      raw: rawObsCount,
      tcg: tcgObsCount,
      psa10: psa10ObsCount,
      psa9: psa9ObsCount,
    },
  };
}

function money(value: number | null | undefined, currency = "USD", compact = false): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: compact ? 0 : 2,
    notation: compact ? "compact" : "standard",
  }).format(value);
}

function formatPercent(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

function variantLabel(item: PriceObservation): string {
  if (item.grading_company) return `${item.grading_company} ${item.grade ?? "Authentic"}`;
  return item.condition ?? "Raw";
}

function choosePrimaryRaw(items: PriceObservation[]): PriceObservation | null {
  const raw = items.filter((item) => !item.grading_company);
  return (
    raw.sort((a, b) => {
      const score = (item: PriceObservation) =>
        (item.provider === "tcgapi" ? 4 : 0) +
        (item.condition === "Near Mint" ? 3 : 0) +
        (/unlimited/i.test(item.printing ?? "") ? 2 : 0);
      return score(b) - score(a) || timestamp(b) - timestamp(a);
    })[0] ?? null
  );
}

function getListingUrl(item: PriceObservation): string | null {
  if (item.listing_url) return item.listing_url;
  if (isEbayObservation(item)) {
    const rawId = item.provider_card_id.replace(/^v1\|/, "").split("|")[0];
    if (rawId && /^\d+$/.test(rawId)) {
      return `https://www.ebay.com/itm/${rawId}`;
    }
  }
  return null;
}

function formatUpdatedDate(value: string | null): string {
  if (!value) return "Recent";
  try {
    const d = new Date(value);
    if (isNaN(d.getTime())) return "Recent";
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(d);
  } catch {
    return "Recent";
  }
}

export function PriceDashboard({ pricing, cardMeta }: PriceDashboardProps) {
  const [timeframe, setTimeframe] = useState<"1M" | "3M" | "1Y">("1Y");
  const [sortBy, setSortBy] = useState<"date" | "price" | "printing" | "variant" | "name">("date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [showAllVariants, setShowAllVariants] = useState(false);

  const latest = useMemo(() => latestByVariant(pricing.observations), [pricing.observations]);
  const primaryRaw = useMemo(() => choosePrimaryRaw(latest), [latest]);
  const tcgPrimary = useMemo(
    () => latest.find((item) => item.provider === "tcgapi") ?? primaryRaw,
    [latest, primaryRaw],
  );

  const psaTen = latest
    .filter((item) => item.grading_company === "PSA" && item.grade === 10)
    .sort((a, b) => timestamp(b) - timestamp(a))[0] ?? null;
  const graded = latest.filter((item) => item.grading_company);
  const matchedSources = pricing.provider_states.filter((item) => item.match_status === "matched").length;

  const gradedMin = graded.length ? Math.min(...graded.map((item) => item.price)) : null;
  const gradedMax = graded.length ? Math.max(...graded.map((item) => item.price)) : null;

  const p24h = tcgPrimary?.price_change_24h;
  const p7d = tcgPrimary?.price_change_7d;
  const p30d = tcgPrimary?.price_change_30d;

  // --- STRICT RAW EBAY PRICES ONLY ---
  const rawEbayListings = latest.filter(
    (item) => isEbayObservation(item) && !item.grading_company,
  );
  const rawEbayPrices = rawEbayListings.map((item) => item.price).sort((a, b) => a - b);

  // 1. Lowest Verified (Raw eBay Only)
  let lowestVerified: number | null = null;
  let lowestVerifiedSubtitle = "No raw eBay listings recorded";
  if (rawEbayPrices.length > 0) {
    lowestVerified = rawEbayPrices[0];
    lowestVerifiedSubtitle = `Lowest of ${rawEbayPrices.length} raw eBay listing${rawEbayPrices.length === 1 ? "" : "s"}`;
  }

  // 2. Avg Listing Price (Raw eBay Only)
  let avgListingPrice: number | null = null;
  let avgListingSubtitle = "No raw eBay listings recorded";
  if (rawEbayPrices.length > 0) {
    avgListingPrice = rawEbayPrices.reduce((sum, p) => sum + p, 0) / rawEbayPrices.length;
    avgListingSubtitle = `Mean of ${rawEbayPrices.length} raw eBay listing${rawEbayPrices.length === 1 ? "" : "s"}`;
  }

  // 3. Median Listing (Raw eBay Only)
  let medianListing: number | null = null;
  let medianListingSubtitle = "No raw eBay listings recorded";
  if (rawEbayPrices.length > 0) {
    const mid = Math.floor(rawEbayPrices.length / 2);
    medianListing =
      rawEbayPrices.length % 2 !== 0
        ? rawEbayPrices[mid]
        : (rawEbayPrices[mid - 1] + rawEbayPrices[mid]) / 2;
    medianListingSubtitle = `Midpoint of ${rawEbayPrices.length} raw eBay listing${rawEbayPrices.length === 1 ? "" : "s"}`;
  }

  // 4. Volatility Value (Replaces Store Buylist)
  // Calculates price dispersion (Coefficient of Variation CV = stdDev / mean) across active comps
  let volatilityPct: number | null = null;
  let volatilitySubtitle = "Insufficient data";
  const volPrices =
    rawEbayPrices.length >= 2
      ? rawEbayPrices
      : latest.filter(isEbayObservation).map((i) => i.price);

  if (volPrices.length >= 2) {
    const mean = volPrices.reduce((a, b) => a + b, 0) / volPrices.length;
    const variance = volPrices.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / volPrices.length;
    const stdDev = Math.sqrt(variance);
    const cv = mean > 0 ? (stdDev / mean) * 100 : 0;
    volatilityPct = cv;
    const rating = cv < 15 ? "Low" : cv < 35 ? "Moderate" : "High";
    volatilitySubtitle = `σ = ${money(stdDev, "USD", true)} · ${rating} Volatility`;
  } else if (p30d !== null && p30d !== undefined) {
    volatilityPct = Math.abs(p30d);
    volatilitySubtitle = "30-day price momentum";
  }

  // --- Multi-series History & Timeframe Filtering ---
  const historyData = useMemo(() => buildMultiSeriesHistory(pricing.observations), [pricing.observations]);

  const filteredHistory = useMemo(() => {
    const { history } = historyData;
    if (history.length === 0) return [];
    const now = new Date();
    const days = timeframe === "1M" ? 30 : timeframe === "3M" ? 90 : 365;
    const cutoffDate = new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

    // Find the last known point before or on cutoffDate to anchor the left edge
    let baselinePoint: ChartPoint | null = null;
    for (const p of history) {
      if (p.date <= cutoffDate) {
        baselinePoint = p;
      } else {
        break;
      }
    }

    const inWindow = history.filter((p) => p.date >= cutoffDate);
    if (inWindow.length === 0) return history;

    // If first in-window point is after cutoffDate and baseline exists, anchor flush to cutoffDate
    if (baselinePoint && inWindow[0].date > cutoffDate) {
      return [{ ...baselinePoint, date: cutoffDate }, ...inWindow];
    }
    return inWindow;
  }, [historyData, timeframe]);

  const historyCurrency = (rawEbayListings[0] ?? primaryRaw)?.currency ?? "USD";

  // --- Variants Sorting ---
  const toggleSort = (column: "date" | "price" | "printing" | "variant" | "name") => {
    const targetCol = column === "name" ? "variant" : column;
    const activeCol = sortBy === "name" ? "variant" : sortBy;
    if (activeCol === targetCol) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(targetCol);
      setSortOrder(targetCol === "printing" || targetCol === "variant" ? "asc" : "desc");
    }
  };

  const sortedVariants = useMemo(() => {
    const list = [...latest];
    list.sort((a, b) => {
      if (sortBy === "date") {
        const diff = timestamp(b) - timestamp(a);
        return sortOrder === "desc" ? diff : -diff;
      }
      if (sortBy === "price") {
        const diff = b.price - a.price;
        return sortOrder === "desc" ? diff : -diff;
      }
      if (sortBy === "printing") {
        const printA = (a.printing || "Standard").toLowerCase();
        const printB = (b.printing || "Standard").toLowerCase();
        const comp = printA.localeCompare(printB);
        if (comp !== 0) {
          return sortOrder === "asc" ? comp : -comp;
        }
        return b.price - a.price;
      }
      if (sortBy === "variant" || sortBy === "name") {
        const nameA = variantLabel(a).toLowerCase();
        const nameB = variantLabel(b).toLowerCase();
        const comp = nameA.localeCompare(nameB);
        if (comp !== 0) {
          return sortOrder === "asc" ? comp : -comp;
        }
        return b.price - a.price;
      }
      return 0;
    });
    return list;
  }, [latest, sortBy, sortOrder]);

  const displayedVariants = showAllVariants ? sortedVariants : sortedVariants.slice(0, 15);

  if (pricing.observations.length === 0) {
    return (
      <section className="mt-14 border-t border-stone-200 pt-10">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-lime-700">Market data</p>
        <div className="mt-4 rounded-2xl border border-stone-200 bg-white p-5 shadow-[0_8px_30px_rgba(33,45,25,0.04)] sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-950">eBay listings price history</h2>
            {cardMeta && <ShopOnEbayButton card={cardMeta} variant="compact" />}
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            No verified exact-match eBay listings have been collected for this card yet. Its history will appear here as listings are verified.
          </p>
          <div className="mt-5">
            <PriceHistoryChart data={[]} currency="USD" label="eBay listings" />
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="mt-14 border-t border-stone-200 pt-10">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-lime-700">Market data</p>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-950">Price overview</h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs text-slate-500">Exact card matches only · Live TCG API & eBay market pricing</p>
          {cardMeta && <ShopOnEbayButton card={cardMeta} variant="compact" />}
        </div>
      </div>

      {/* Comprehensive Price Breakdown Cards */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {/* TCG Market Price Card with Momentum */}
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-50/50 p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-800">TCG Market Price</span>
            {tcgPrimary?.printing && (
              <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                {tcgPrimary.printing}
              </span>
            )}
          </div>
          <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">
            {money(tcgPrimary?.price, tcgPrimary?.currency)}
          </p>
          {/* 24h / 7d / 30d Momentum Pills */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {p24h !== null && p24h !== undefined && (
              <span
                className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                  p24h >= 0 ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                }`}
                title="24-Hour Price Change"
              >
                24h: {formatPercent(p24h)}
              </span>
            )}
            {p7d !== null && p7d !== undefined && (
              <span
                className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                  p7d >= 0 ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                }`}
                title="7-Day Price Change"
              >
                7d: {formatPercent(p7d)}
              </span>
            )}
            {p30d !== null && p30d !== undefined && (
              <span
                className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                  p30d >= 0 ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                }`}
                title="30-Day Price Change"
              >
                30d: {formatPercent(p30d)}
              </span>
            )}
          </div>
        </div>

        {/* Lowest Verified Listing (Raw eBay only) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Lowest Verified (Raw)</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {money(lowestVerified)}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={lowestVerifiedSubtitle}>
            {lowestVerifiedSubtitle}
          </p>
        </div>

        {/* Avg Listing Price (Raw eBay only) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Avg Listing (Raw)</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {money(avgListingPrice)}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={avgListingSubtitle}>
            {avgListingSubtitle}
          </p>
        </div>

        {/* Median Listing (Raw eBay only) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Median Listing (Raw)</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {money(medianListing)}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={medianListingSubtitle}>
            {medianListingSubtitle}
          </p>
        </div>

        {/* Volatility Value (Replaces Store Buylist) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Volatility</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {volatilityPct !== null ? `±${volatilityPct.toFixed(1)}%` : "—"}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={volatilitySubtitle}>
            {volatilitySubtitle}
          </p>
        </div>
      </div>

      {/* Graded & Coverage Summary */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Metric
          label="PSA 10 Comps"
          value={money(psaTen?.price ?? null, psaTen?.currency)}
          note={psaTen ? providerName(psaTen.provider) : "No recent exact match"}
        />
        <Metric
          label="Graded Range"
          value={gradedMin === null ? "—" : `${money(gradedMin)}–${money(gradedMax)}`}
          note={`${graded.length} graded variants`}
        />
        <Metric
          label="Source Coverage"
          value={`${matchedSources}/${pricing.provider_states.length || 1}`}
          note={`${pricing.observations.length} observations`}
        />
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-[0_8px_30px_rgba(33,45,25,0.04)] sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-slate-950">
                eBay listings price history
              </h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Daily averages for Raw eBay, TCG API, PSA 10, and PSA 9 comps
              </p>
            </div>
          </div>
          <div className="mt-5">
            <PriceHistoryChart
              data={filteredHistory}
              currency={historyCurrency}
              label="eBay listings"
              obsCounts={historyData.obsCounts}
            />
          </div>

          {/* Timeframe Buttons below chart */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-stone-100 pt-4">
            <span className="text-xs font-medium text-slate-500">History timeframe:</span>
            <div className="flex items-center gap-2">
              {(["1M", "3M", "1Y"] as const).map((range) => {
                const label = range === "1M" ? "1 Month" : range === "3M" ? "3 Months" : "1 Year";
                const active = timeframe === range;
                return (
                  <button
                    key={range}
                    type="button"
                    onClick={() => setTimeframe(range)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                      active
                        ? "bg-slate-950 text-white shadow-sm"
                        : "border border-stone-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-stone-50"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-stone-200 bg-stone-50/70 p-5 sm:p-6">
          <h3 className="text-sm font-bold text-slate-950">Provider status</h3>
          <div className="mt-4 divide-y divide-zinc-200 border-y border-zinc-200">
            {pricing.provider_states.map((state) => (
              <div className="flex items-center justify-between gap-4 py-3" key={state.provider}>
                <span className="text-sm text-zinc-700">{providerName(state.provider)}</span>
                <span
                  className={`rounded-full border px-2 py-1 text-[11px] font-medium ${
                    state.match_status === "matched"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-zinc-200 bg-white text-zinc-500"
                  }`}
                >
                  {state.match_status === "matched" ? "Matched" : "No exact match"}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs leading-5 text-zinc-500">
            Unmatched provider results are excluded from every displayed price.
          </p>
        </div>
      </div>

      {/* Latest Variants Table with Interactive Sorting */}
      <div className="mt-8 overflow-hidden rounded-xl border border-zinc-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 bg-zinc-50/70 px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold text-zinc-950">Latest variants & pricing data</h3>
            <p className="text-xs text-zinc-500 mt-0.5">
              Showing {displayedVariants.length} of {sortedVariants.length} variants
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-zinc-500 mr-1">Sort:</span>
            <button
              type="button"
              onClick={() => toggleSort("date")}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                sortBy === "date"
                  ? "bg-zinc-900 text-white"
                  : "border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50"
              }`}
            >
              Date {sortBy === "date" ? (sortOrder === "desc" ? "↓" : "↑") : ""}
            </button>
            <button
              type="button"
              onClick={() => toggleSort("price")}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                sortBy === "price"
                  ? "bg-zinc-900 text-white"
                  : "border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50"
              }`}
            >
              Price {sortBy === "price" ? (sortOrder === "desc" ? "↓" : "↑") : ""}
            </button>
            <button
              type="button"
              onClick={() => toggleSort("printing")}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                sortBy === "printing"
                  ? "bg-zinc-900 text-white"
                  : "border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50"
              }`}
            >
              Printing Name {sortBy === "printing" ? (sortOrder === "asc" ? "A–Z" : "Z–A") : ""}
            </button>
            <button
              type="button"
              onClick={() => toggleSort("variant")}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                sortBy === "variant" || sortBy === "name"
                  ? "bg-zinc-900 text-white"
                  : "border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50"
              }`}
            >
              Variant {sortBy === "variant" || sortBy === "name" ? (sortOrder === "asc" ? "A–Z" : "Z–A") : ""}
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left">
            <thead>
              <tr className="border-b border-zinc-200 text-xs text-zinc-500">
                <th
                  onClick={() => toggleSort("variant")}
                  className="px-5 py-3 font-medium cursor-pointer hover:text-zinc-900 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Variant / Condition</span>
                    {(sortBy === "variant" || sortBy === "name") && <span>{sortOrder === "asc" ? "↑" : "↓"}</span>}
                  </div>
                </th>
                <th
                  onClick={() => toggleSort("printing")}
                  className="px-5 py-3 font-medium cursor-pointer hover:text-zinc-900 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Printing Name</span>
                    {sortBy === "printing" && <span>{sortOrder === "asc" ? "↑" : "↓"}</span>}
                  </div>
                </th>
                <th className="px-5 py-3 font-medium">Source</th>
                <th className="px-5 py-3 font-medium">Lowest Price</th>
                <th className="px-5 py-3 font-medium">Median</th>
                <th className="px-5 py-3 font-medium">Buylist</th>
                <th
                  onClick={() => toggleSort("date")}
                  className="px-5 py-3 font-medium cursor-pointer hover:text-zinc-900 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Last updated</span>
                    {sortBy === "date" && <span>{sortOrder === "asc" ? "↑" : "↓"}</span>}
                  </div>
                </th>
                <th
                  onClick={() => toggleSort("price")}
                  className="px-5 py-3 text-right font-medium cursor-pointer hover:text-zinc-900 transition-colors select-none"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>Market price</span>
                    {sortBy === "price" && <span>{sortOrder === "asc" ? "↑" : "↓"}</span>}
                  </div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {displayedVariants.map((item) => {
                const listingUrl = getListingUrl(item);
                return (
                  <tr key={`${item.provider}:${item.provider_card_id || item.variant_id}`}>
                    <td className="px-5 py-3 text-sm font-medium text-zinc-900">{variantLabel(item)}</td>
                    <td className="px-5 py-3 text-sm text-zinc-600">{item.printing ?? "Standard"}</td>
                    <td className="px-5 py-3 text-sm">
                      {listingUrl ? (
                        <a
                          href={listingUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="group inline-flex items-center gap-1.5 font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
                          title="View listing on eBay"
                        >
                          <span>{providerName(item.provider)}</span>
                          <svg
                            className="h-3.5 w-3.5 opacity-70 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:opacity-100"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                            />
                          </svg>
                        </a>
                      ) : (
                        <span className="text-zinc-600">{providerName(item.provider)}</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-xs text-zinc-600">
                      {item.low_price !== null && item.low_price !== undefined ? money(item.low_price) : "—"}
                    </td>
                    <td className="px-5 py-3 text-xs text-zinc-600">{money(item.median_price)}</td>
                    <td className="px-5 py-3 text-xs text-zinc-600">{money(item.buylist_price)}</td>
                    <td className="px-5 py-3 text-xs text-zinc-500">
                      {formatUpdatedDate(item.provider_updated_at ?? item.observed_at)}
                    </td>
                    <td className="px-5 py-3 text-right font-mono text-sm font-bold text-zinc-950">
                      {money(item.price, item.currency)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {sortedVariants.length > 15 && (
          <div className="border-t border-zinc-200 bg-zinc-50/50 px-5 py-3 text-center">
            <button
              type="button"
              onClick={() => setShowAllVariants((prev) => !prev)}
              className="text-xs font-semibold text-emerald-700 hover:text-emerald-800 hover:underline"
            >
              {showAllVariants
                ? "Show top 15 variants"
                : `Show all ${sortedVariants.length} variants (${sortedVariants.length - 15} more)`}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-[0_8px_24px_rgba(33,45,25,0.035)]">
      <p className="text-xs font-semibold text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-bold tracking-tight text-slate-950">{value}</p>
      <p className="mt-2 truncate text-xs text-slate-500">{note}</p>
    </div>
  );
}
