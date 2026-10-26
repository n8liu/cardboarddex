"use client";

import { AnimatedNumber } from "@/components/ui/animated-number";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { ShopOnEbayButton, type EbaySearchCardTarget } from "@/components/shop-ebay-button";
import type { CardPricing, PriceObservation } from "@/types/card";
import { GRADING_COMPANIES, gradeCompany, mergeProviderHistory, providerSeriesName, robustMedian, selectHistorySeries, seriesPrinting, withoutAskingOutliers, type GradingCompany } from "@/lib/provider-history";
import type { ChartPoint } from "@/components/price-history-chart";
import { isStalePriceDate, PriceSourceBadge } from "@/components/ui/price-source-badge";

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

// Use the same identity for deduplication and React rows, including each printing/grade.
function variantKey(item: PriceObservation): string {
  return JSON.stringify([item.provider, item.variant_id,
    isEbayObservation(item) ? item.provider_card_id : null,
    item.printing, item.condition, item.grading_company, item.grade, item.currency]);
}

function latestByVariant(observations: PriceObservation[]): PriceObservation[] {
  const latest = new Map<string, PriceObservation>();
  for (const observation of observations) {
    const key = variantKey(observation);
    const current = latest.get(key);
    if (!current || timestamp(observation) >= timestamp(current)) latest.set(key, observation);
  }
  return [...latest.values()];
}

function providerName(value: string): string {
  if (value.toLowerCase().includes("ebay")) return "eBay listings";
  if (value === "tcgapi") return "Legacy market history";
  return value;
}

function isEbayObservation(item: PriceObservation): boolean {
  return item.provider.toLowerCase().includes("ebay");
}

const SERIES_ASKING_BAND = 10;

function buildMultiSeriesHistory(observations: PriceObservation[]): {
  history: ChartPoint[];
  obsCounts: { raw: number; tcg: number; psa10: number; psa9: number };
} {
  const dates = new Set<string>();
  const byDate = { raw: new Map<string, number[]>(), tcg: new Map<string, number[]>(),
    psa10: new Map<string, number[]>(), psa9: new Map<string, number[]>() };
  const add = (series: keyof typeof byDate, date: string, price: number) => {
    dates.add(date);
    byDate[series].set(date, [...(byDate[series].get(date) ?? []), price]);
  };

  for (const obs of observations) {
    if (!obs.price || obs.price <= 0) continue;
    const date = (obs.provider_updated_at ?? obs.observed_at ?? "").slice(0, 10);
    if (!date) continue;

    if (isEbayObservation(obs)) {
      if (!obs.grading_company) add("raw", date, obs.price);
      else if (obs.grading_company.toUpperCase() === "PSA") {
        if (obs.grade === 10) add("psa10", date, obs.price);
        else if (obs.grade === 9) add("psa9", date, obs.price);
      }
    } else if (obs.provider === "tcgapi" || obs.provider.toLowerCase().includes("tcg")) {
      add("tcg", date, obs.price);
    }
  }

  // If no specific series dates found, fallback to all observations
  const fallback = dates.size === 0;
  if (fallback) {
    for (const obs of observations) {
      const date = (obs.provider_updated_at ?? obs.observed_at ?? "").slice(0, 10);
      if (!date || !obs.price) continue;
      add("raw", date, obs.price);
    }
  }

  if (dates.size === 0) {
    return {
      history: [],
      obsCounts: { raw: 0, tcg: 0, psa10: 0, psa9: 0 },
    };
  }

  // eBay rows are asking listings: drop absurd asks across the whole series (a loose band,
  // so real moves over a year survive), then take each day's robust median.
  for (const series of fallback ? [] : ["raw", "psa10", "psa9"] as const) {
    const kept = new Set(withoutAskingOutliers([...byDate[series].values()].flat(), SERIES_ASKING_BAND));
    for (const [date, prices] of byDate[series]) {
      const remaining = prices.filter((price) => kept.has(price));
      if (remaining.length) byDate[series].set(date, remaining);
      else byDate[series].delete(date);
    }
  }

  const sortedDates = [...dates].sort((a, b) => a.localeCompare(b));
  const round = (value: number | null) => value === null ? null : Math.round(value * 100) / 100;
  const average = (prices: number[] | undefined) => prices ? round(prices.reduce((a, b) => a + b, 0) / prices.length) : null;
  const daily = (prices: number[] | undefined) => !prices ? null : fallback ? average(prices) : round(robustMedian(prices));

  const points: ChartPoint[] = sortedDates.map((date) => ({
    date, rawPrice: daily(byDate.raw.get(date)), tcgPrice: average(byDate.tcg.get(date)),
    psa10Price: daily(byDate.psa10.get(date)), psa9Price: daily(byDate.psa9.get(date)),
  }));
  const count = (series: keyof typeof byDate) => [...byDate[series].values()].reduce((n, prices) => n + prices.length, 0);

  return {
    history: points,
    obsCounts: { raw: count("raw"), tcg: count("tcg"), psa10: count("psa10"), psa9: count("psa9") },
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
  let url: string | null = null;
  if (item.listing_url) {
    url = item.listing_url;
  } else if (isEbayObservation(item)) {
    const rawId = item.provider_card_id.replace(/^v1\|/, "").split("|")[0];
    if (rawId && /^\d+$/.test(rawId)) {
      url = `https://www.ebay.com/itm/${rawId}`;
    }
  }
  if (url && (url.startsWith("https://") || url.startsWith("http://"))) {
    return url;
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

export function PriceDashboard({ pricing: originalPricing, cardMeta }: PriceDashboardProps) {
  const [listingGroup, setListingGroup] = useState<string | null>(null);
  const selectedPrinting = originalPricing.selected_printing ?? "Standard";
  const selectedCondition = originalPricing.selected_condition ?? "Near Mint";
  const groupKey = listingGroup ?? JSON.stringify([selectedPrinting, selectedCondition]);
  const group = originalPricing.listing_groups?.find((item) => JSON.stringify([item.printing, item.condition]) === groupKey);
  const pricing = useMemo(() => ({
    ...originalPricing,
    ...(group ?? {}),
    observations: originalPricing.observations.filter((item) => !group || !isEbayObservation(item) || item.grading_company ||
      (item.printing === group.printing && item.condition === group.condition)),
  }), [originalPricing, group]);
  const [timeframe, setTimeframe] = useState<"1M" | "3M" | "6M" | "1Y">("3M");
  const [sortBy, setSortBy] = useState<"date" | "price" | "printing" | "variant" | "name">("date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [showAllVariants, setShowAllVariants] = useState(false);

  const latest = useMemo(() => latestByVariant(pricing.observations), [pricing.observations]);
  const primaryRaw = useMemo(() => choosePrimaryRaw(latest), [latest]);
  const tcgSnapshot = useMemo(
    () => choosePrimaryRaw((pricing.tcg_market_prices ?? []).filter((item) => item.provider === "tcgapi")),
    [pricing.tcg_market_prices],
  );

  // Historical observations also power the graph; use their newest raw TCG
  // quote when a current provider snapshot is unavailable, without stale momentum.
  const legacyTcgPrimary = useMemo(
    () => tcgSnapshot ?? latest
      .filter((item) => item.provider === "tcgapi" && !item.grading_company && Number.isFinite(item.price) && item.price > 0)
      .sort((a, b) => timestamp(b) - timestamp(a))[0] ?? null,
    [tcgSnapshot, latest],
  );

  const pptPrimary = (pricing.market_quotes ?? pricing.provider_quotes)?.find((quote) => quote.primary && !quote.grade);
  const tcgPrimary = pptPrimary ? { ...pptPrimary, provider_updated_at: pptPrimary.price_date, observed_at: pptPrimary.fetched_at ?? pptPrimary.price_date } : legacyTcgPrimary;
  const pptPsaTen = pricing.provider_quotes?.find((quote) => quote.grade === "psa10" && quote.metric === "median_7d" && !quote.stale);
  const pptPsaNine = pricing.provider_quotes?.find((quote) => quote.grade === "psa9" && quote.metric === "median_7d" && !quote.stale);
  const psaTen = pricing.ppt_mapped ? pptPsaTen : latest
    .filter((item) => item.grading_company === "PSA" && item.grade === 10)
    .sort((a, b) => timestamp(b) - timestamp(a))[0] ?? null;
  const graded = latest.filter((item) => item.grading_company);
  const matchedSources = pricing.provider_states.filter((item) => item.match_status === "matched").length + (pricing.ppt_mapped ? 1 : 0);
  const gradedMin = graded.length ? Math.min(...graded.map((item) => item.price)) : null;
  const gradedMax = graded.length ? Math.max(...graded.map((item) => item.price)) : null;
  const momentum = pptPrimary?.stale ? null : pptPrimary;
  const p24h = momentum?.price_change_24h;
  const p7d = momentum?.price_change_7d;
  const p30d = momentum?.price_change_30d;

  // --- STRICT RAW EBAY PRICES ONLY ---
  const rawEbayListings = latest.filter(
    (item) => isEbayObservation(item) && !item.grading_company,
  );
  const rawEbayPrices = rawEbayListings.map((item) => item.price).sort((a, b) => a - b);

  const lowestMatched = pricing.lowest_matched_price ?? null;
  const lowestMatchedSubtitle = `Past 7 days · ${pricing.listing_sample_count ?? 0} matched listings · ${pricing.listing_seller_count ?? 0} sellers`;

  // Both summaries use the server's seven-day window and one price per listing.
  const avgListingPrice = pricing.avg_listing_price ?? null;
  const medianListing = pricing.median_listing_price ?? null;
  const sampleCount = pricing.listing_sample_count ?? 0;
  const avgListingSubtitle = avgListingPrice == null ? "Insufficient comparable listings (need 3 listings and 2 sellers)" : sampleCount ? `Mean of ${sampleCount} raw USD eBay listings observed in the past 7 days` : "No raw USD eBay listings observed in the past 7 days";
  const medianListingSubtitle = medianListing == null ? "Insufficient comparable listings (need 3 listings and 2 sellers)" : sampleCount ? `Median of ${sampleCount} raw USD eBay listings observed in the past 7 days` : "No raw USD eBay listings observed in the past 7 days";

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
  const historyData = useMemo(() => buildMultiSeriesHistory(pricing.market_history_series ? pricing.observations.filter(isEbayObservation) : pricing.observations), [pricing.observations, pricing.market_history_series]);

  // Printings start on (hidden ones are tracked) and grading companies start off.
  const [hiddenPrintings, setHiddenPrintings] = useState<string[]>([]);
  const [shownCompanies, setShownCompanies] = useState<GradingCompany[]>([]);
  const providerHistory = pricing.market_history_series ?? pricing.provider_history ?? [];
  const historyPrintings = [...new Set(providerHistory.filter((series) => !series.grade).map(seriesPrinting))];
  const companySeriesCount = (company: GradingCompany) => providerHistory.filter((series) => gradeCompany(series.grade) === company).length
    + (company === "psa" ? (historyData.obsCounts.psa10 ? 1 : 0) + (historyData.obsCounts.psa9 ? 1 : 0) : 0);
  const visibleProviderHistory = selectHistorySeries(providerHistory, {
    printings: new Set(historyPrintings.filter((printing) => !hiddenPrintings.includes(printing))),
    companies: new Set(shownCompanies),
    preferredCondition: pptPrimary?.condition,
  });
  const colors = ["#e11d48", "#0891b2", "#d97706", "#4f46e5", "#16a34a", "#db2777", "#0d9488", "#9333ea", "#ca8a04", "#2563eb"];
  const extraSeries = visibleProviderHistory.map((series, index) => ({ key: series.id, name: providerSeriesName(series), color: colors[index % colors.length] }));
  const days = timeframe === "1M" ? 30 : timeframe === "3M" ? 90 : timeframe === "6M" ? 180 : 365;
  // eBay PSA asking-price lines follow the PSA toggle too.
  const ebayHistory = shownCompanies.includes("psa") ? historyData.history
    : historyData.history.map(({ psa10Price: _psa10, psa9Price: _psa9, ...point }) => point);
  const filteredHistory = mergeProviderHistory(ebayHistory, visibleProviderHistory,
    new Date(Date.now() - days * 86400000).toISOString().slice(0, 10), new Date().toISOString().slice(0, 10));

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

  if (pricing.observations.length === 0 && !tcgPrimary && !pricing.eligibility_version && !providerHistory.length) {
    return (
      <section className="mt-8 border-t border-stone-200 pt-6 sm:mt-10 sm:pt-8">
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
    <section className="mt-8 border-t border-stone-200 pt-6 sm:mt-10 sm:pt-8">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-lime-700">Market data</p>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-950">Price overview</h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs text-slate-500">Stored market prices and matched eBay asking listings</p>
          {cardMeta && <ShopOnEbayButton card={cardMeta} variant="compact" />}
        </div>
      </div>

      {/* Comprehensive Price Breakdown Cards */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {/* Market Price Card with Momentum */}
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-50/50 p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-800">Market Price</span>
            {tcgPrimary?.printing && (
              <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                {tcgPrimary.printing}
              </span>
            )}
          </div>
          <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">
            {tcgPrimary?.price != null ? <AnimatedNumber value={tcgPrimary.price} format={(value) => money(value, tcgPrimary.currency)} /> : "—"}
          </p>
          {pptPrimary && <p className="mt-1.5">
            <PriceSourceBadge stale={pptPrimary.stale}
              label={`${pptPrimary.stale ? "Last known" : "PPT market"} · ${pptPrimary.condition} · ${formatUpdatedDate(pptPrimary.price_date)}`}
              title={pptPrimary.stale ? "Pokémon Price Tracker has not reported a current price; this is the last recorded one." : "Pokémon Price Tracker market price"} />
          </p>}
          {tcgPrimary && !pptPrimary && (() => {
            const date = tcgPrimary.provider_updated_at ?? tcgPrimary.observed_at;
            const stale = isStalePriceDate(date);
            return <p className="mt-1.5">
              <PriceSourceBadge stale={stale} title="Recorded from the retired legacy market source"
                label={`${stale ? "Last known" : "Legacy market"} · ${formatUpdatedDate(date)}`} />
            </p>;
          })()}
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

        {/* Lowest Matched Listing (Raw eBay only) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Lowest Matched Listing</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {lowestMatched != null ? <AnimatedNumber value={lowestMatched} format={money} /> : "—"}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={lowestMatchedSubtitle}>
            {lowestMatchedSubtitle}
          </p>
        </div>

        {/* Avg Listing Price (Raw eBay only) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Avg Listing (Raw, 7d)</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {avgListingPrice != null ? <AnimatedNumber value={avgListingPrice} format={money} /> : "—"}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={avgListingSubtitle}>
            {avgListingSubtitle}
          </p>
        </div>

        {/* Median Listing (Raw eBay only) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Median Listing (Raw, 7d)</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {medianListing != null ? <AnimatedNumber value={medianListing} format={money} /> : "—"}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={medianListingSubtitle}>
            {medianListingSubtitle}
          </p>
        </div>

        {/* Volatility Value (Replaces Store Buylist) */}
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Volatility</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">
            {volatilityPct !== null ? <AnimatedNumber value={volatilityPct} format={(value) => `±${value.toFixed(1)}%`} /> : "—"}
          </p>
          <p className="mt-2 truncate text-xs text-slate-400" title={volatilitySubtitle}>
            {volatilitySubtitle}
          </p>
        </div>
      </div>

      {pricing.eligibility_version && (
        <div className="mt-4 rounded-xl border border-slate-200 p-4">
          <label className="text-sm font-semibold" htmlFor="listing-comparison">eBay comparison group</label>
          <select id="listing-comparison" className="ml-3 max-w-full rounded-lg border p-2 text-sm" value={groupKey} onChange={(event) => setListingGroup(event.target.value)}>
            {(originalPricing.listing_groups ?? []).map((item) => (
              <option key={JSON.stringify([item.printing, item.condition])} value={JSON.stringify([item.printing, item.condition])}>{item.printing} · {item.condition}</option>
            ))}
          </select>
          <p className="mt-2 text-xs text-slate-500">Asking prices, not completed sales. Product matching does not authenticate physical cards.</p>
          {!!pricing.excluded_listing_count && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm">Unconfirmed listings ({pricing.excluded_listing_count}) · Excluded from statistics</summary>
              <ul className="mt-2 max-h-72 space-y-2 overflow-auto">
                {pricing.unconfirmed_listings?.map((item) => (
                  <li key={item.item_id} className="rounded border p-2 text-sm">
                    {item.listing_url?.startsWith("https://") ? <a href={item.listing_url} target="_blank" rel="noopener noreferrer" className="underline">{item.title}</a> : item.title}
                    <p className="text-xs text-slate-500">{item.status} · {item.reasons.map((reason) => reason.replaceAll("_", " ")).join(", ")}</p>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Graded & Coverage Summary */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Metric
          label={pricing.ppt_mapped ? "PSA 10 · 7-day median" : "PSA 10 Comps"}
          value={money(psaTen?.price ?? null, psaTen?.currency)}
          note={pricing.ppt_mapped ? "Provider-reported eBay / Fanatics Collect sales" : psaTen ? providerName(psaTen.provider) : "No recent exact match"}
        />
        <Metric
          label={pricing.ppt_mapped ? "PSA 9 · 7-day median" : "Graded Range"}
          value={pricing.ppt_mapped ? money(pptPsaNine?.price ?? null, pptPsaNine?.currency) : gradedMin === null ? "—" : `${money(gradedMin)}–${money(gradedMax)}`}
          note={pricing.ppt_mapped ? "Provider-reported eBay / Fanatics Collect sales" : `${graded.length} graded variants`}
        />
        <Metric
          label="Source Coverage"
          value={`${matchedSources}/${pricing.provider_states.length + (pricing.ppt_mapped ? 1 : 0) || 1}`}
          note={`${pricing.observations.length} observations`}
        />
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
        <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-[0_8px_30px_rgba(33,45,25,0.04)] sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-slate-950">
                Price history
              </h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                PPT market history includes earlier recorded prices. Each line holds its last recorded price until a new one arrives; held days are not new reported values. Different printings and grades remain separate. eBay lines are asking prices.
              </p>
            </div>
          </div>
          <div className="mt-5">
            {/* Phones: one horizontally scrolling row of chips; wider screens wrap. */}
            {(historyPrintings.length > 0 || GRADING_COMPANIES.some((company) => companySeriesCount(company) > 0)) && (
              <div className="-mx-1 mb-3 flex flex-nowrap items-center gap-x-4 gap-y-2 overflow-x-auto px-1 pb-1 text-xs [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
                {historyPrintings.length > 0 && <div role="group" aria-label="Printings" className="flex shrink-0 flex-nowrap items-center gap-1.5 sm:shrink sm:flex-wrap">
                  {historyPrintings.map((printing) => {
                    const on = !hiddenPrintings.includes(printing);
                    return <button key={printing} type="button" aria-pressed={on}
                      onClick={() => setHiddenPrintings((hidden) => on ? [...hidden, printing] : hidden.filter((item) => item !== printing))}
                      className={`shrink-0 whitespace-nowrap rounded-lg border px-2.5 py-1 font-semibold transition ${on ? "border-slate-900 bg-slate-900 text-white" : "border-stone-200 bg-white text-slate-500 hover:border-slate-300"}`}>
                      {printing}
                    </button>;
                  })}
                </div>}
                <div role="group" aria-label="Graded" className="flex shrink-0 flex-nowrap items-center gap-1.5 sm:shrink sm:flex-wrap">
                  {/* Only companies with history for this card get a toggle. */}
                  {GRADING_COMPANIES.filter((company) => companySeriesCount(company) > 0).map((company) => {
                    const on = shownCompanies.includes(company);
                    const count = companySeriesCount(company);
                    return <button key={company} type="button" aria-pressed={on}
                      title={`Show all ${company.toUpperCase()} grades`}
                      onClick={() => setShownCompanies((shown) => on ? shown.filter((item) => item !== company) : [...shown, company])}
                      className={`shrink-0 whitespace-nowrap rounded-lg border px-2.5 py-1 font-semibold transition ${on ? "border-amber-600 bg-amber-500 text-white" : "border-stone-200 bg-white text-slate-600 hover:border-slate-300"}`}>
                      {company.toUpperCase()}<span className="ml-1 font-normal opacity-70">{count}</span>
                    </button>;
                  })}
                </div>
              </div>
            )}
            {visibleProviderHistory.some((series) => series.cutover_date) && <p className="mb-2 text-[11px] text-slate-500">
              {visibleProviderHistory.filter((series) => series.cutover_date).map((series) => `PPT continuation from ${series.cutover_date} · ${providerSeriesName(series)}`).join(" · ")}
            </p>}
            <PriceHistoryChart
              data={filteredHistory}
              currency={historyCurrency}
              label="eBay listings"
              obsCounts={historyData.obsCounts}
              extraSeries={extraSeries}
            />
          </div>

          {/* Timeframe Buttons below chart */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-stone-100 pt-4">
            <span className="text-xs font-medium text-slate-500">History timeframe:</span>
            <div className="flex flex-wrap items-center gap-2">
              {(["1M", "3M", "6M", "1Y"] as const).map((range) => {
                const label = range === "1M" ? "1 Month" : range === "3M" ? "3 Months" : range === "6M" ? "6 Months" : "1 Year";
                const active = timeframe === range;
                return (
                  <button
                    key={range}
                    type="button"
                    aria-pressed={active}
                    aria-label={label}
                    onClick={() => setTimeframe(range)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                      active
                        ? "bg-slate-950 text-white shadow-sm"
                        : "border border-stone-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-stone-50"
                    }`}
                  >
                    <span className="sm:hidden">{range}</span>
                    <span className="hidden sm:inline">{label}</span>
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
                  <tr key={variantKey(item)}>
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
