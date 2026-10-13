"use client";
import { CacheNotice, useCacheNotice } from "@/components/cache-notice";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import Image from "@/components/card-image";
import { HistorySparkline, PriceFreshness, PurchaseReturn } from "@/components/market-history-panel";
import { SearchInput } from "@/components/ui/search-input";
import { useCurrency } from "@/context/currency-context";
import { cardImageUrl, getSealedSignals } from "@/lib/api";
import type { GameLanguage, SealedProductType, SealedSignalItem, SealedSignalsResponse, SealedSignalType, SealedSortOption } from "@/types/card";

type Era = "newer" | "older";
type Filters = { game: GameLanguage; period: 30 | 90; query: string; productType: SealedProductType; signal: SealedSignalType; sortBy: SealedSortOption };
const languages = { all: "All", pokemon: "English", "pokemon-japan": "Japanese" };
const products = { all: "All products", booster_box: "Booster boxes", etb: "Elite Trainer Boxes", bundle: "Booster bundles", case: "Cases", pack: "Booster packs", blister: "Blisters", collection: "Collections & tins" };
const signals = { all: "All signals", strong_buy: "Strong buy", buy: "Buy", hold: "Hold", underperform: "Underperform" };
const sorts = { momentum_desc: "30-day growth", score_desc: "Signal score", price_asc: "Lowest price", price_desc: "Highest price", supply_asc: "Fewest listings", age_desc: "Oldest release" };
const selectClass = "min-h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-800 transition hover:bg-slate-100 focus:border-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900/10";

function ProductRow({ item, rank, period }: { item: SealedSignalItem; rank: number; period: 30 | 90 }) {
  const { formatPrice } = useCurrency();
  const growth = item.return_percent !== undefined ? item.return_percent : period === 30 ? item.price_change_30d : null;
  const hasGrowth = growth != null && Number.isFinite(growth);
  return (
    <li className="rounded-xl border border-slate-200/80 bg-white p-3 transition hover:border-slate-400 focus-within:border-slate-400">
      <div className="flex items-center gap-2.5">
        <span className="w-5 shrink-0 text-center text-xs font-bold tabular-nums text-slate-400">{String(rank).padStart(2, "0")}</span>
        <Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} tabIndex={-1} aria-hidden="true" className="relative h-12 w-10 shrink-0 overflow-hidden rounded-lg border border-slate-100 bg-slate-50/60">
          <Image src={cardImageUrl(item.image_url)} alt="" fill sizes="40px" className="object-contain p-0.5" />
        </Link>
        <div className="min-w-0 flex-1">
          <h3 className="text-xs font-bold leading-snug text-slate-950 sm:text-sm"><Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} className="hover:underline focus-visible:outline-slate-900">{item.name}</Link></h3>
          <p className="mt-1 truncate text-[10px] text-slate-500">{item.set_name} · {item.release_date?.slice(0, 4)}</p>
        </div>
        <div className="shrink-0 text-right tabular-nums">
          <p className="text-xs font-bold text-slate-950 sm:text-sm">{formatPrice(item.market_price)}</p>
          <p className={`mt-1 text-[11px] font-semibold ${hasGrowth && growth > 0 ? "text-emerald-700" : hasGrowth && growth < 0 ? "text-rose-700" : "text-slate-500"}`}><span className="sr-only">{period}-day growth: </span>{hasGrowth ? `${growth > 0 ? "+" : ""}${growth.toFixed(1)}%` : "Unavailable"}</p>
        </div>
      </div>
      <details className="mt-2 text-[11px] text-slate-500">
        <summary className="cursor-pointer py-1 hover:text-slate-950">Price history & purchase return<span className="sr-only"> for {item.name}</span></summary>
        <div className="mt-2 border-t border-slate-100 pt-3">
          <p className="mb-2">{item.product_type} · Signal score {item.signal_score}/100</p>
          <PriceFreshness value={item} />
          <HistorySparkline points={item.history?.points ?? []} />
          {item.history?.coverage_start && <p>History: {item.history.coverage_start} – {item.history.coverage_end}</p>}
          <p className="mt-3 font-semibold text-slate-700">Estimate return on your purchase</p>
          <PurchaseReturn price={item.market_price} />
          <p className="mt-2 text-[10px]">{item.total_listings > 0 ? `${item.total_listings} active listings` : "Listing count unavailable"}{item.last_updated_at ? ` · Observed ${item.last_updated_at.slice(0, 10)}` : ""}</p>
        </div>
      </details>
    </li>
  );
}

function RankingColumn({ era, filters, initial }: { era: Era; filters: Filters; initial?: SealedSignalsResponse | null }) {
  const [cacheMetadata, setCacheMetadata] = useCacheNotice();
  const previousFilters = useRef<string | null>(null);
  const [data, setData] = useState(initial ?? null);
  const [items, setItems] = useState(initial?.items ?? []);
  const [loading, setLoading] = useState(!initial);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const mounted = useRef(false);
  const busy = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    if (initial && retry === 0) return;
    const key = JSON.stringify([era, filters]);
    if (previousFilters.current !== null && previousFilters.current !== key) { setItems([]); setData(null); }
    previousFilters.current = key;
    setCacheMetadata(null);
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getSealedSignals({ ...filters, era, page: 1, perPage: 12, abortSignal: controller.signal, bypassCache: retry > 0, onCache: (metadata) => { if (!cancelled) setCacheMetadata(metadata); } }).then((result) => {
      if (!cancelled) { setData(result); setItems(result.items); }
    }).catch((err) => {
      console.error(`Failed loading ${era} sealed rankings:`, err);
      if (!cancelled) setError("Could not load this ranking. Please try again.");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; controller.abort(); };
  }, [era, filters, initial, retry]);

  async function loadMore(bypassCache = false) {
    if (!data || busy.current) return;
    busy.current = true;
    setLoading(true);
    setError("");
    try {
      const result = await getSealedSignals({ ...filters, era, page: data.page + 1, perPage: 12, bypassCache, onCache: setCacheMetadata });
      if (mounted.current) {
        setData(result);
        setItems((previous) => {
          const seen = new Set(previous.map((item) => item.card_id));
          return [...previous, ...result.items.filter((item) => !seen.has(item.card_id))];
        });
      }
    } catch (err) {
      console.error(`Failed loading more ${era} sealed products:`, err);
      if (mounted.current) setError("Could not load more products. Please try again.");
    } finally {
      busy.current = false;
      if (mounted.current) setLoading(false);
    }
  }
  const newer = era === "newer";
  return (
    <section aria-labelledby={`${era}-heading`} aria-busy={loading} className="min-w-0 rounded-2xl border border-slate-200/90 bg-slate-50/50 p-3.5 shadow-2xs sm:p-4">
      <div className="mb-3 border-b border-slate-200 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 id={`${era}-heading`} className="text-xs font-bold uppercase tracking-wider text-slate-900">{newer ? "Newer releases" : "Older & vintage"}</h2><span className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold tabular-nums text-slate-500">{data ? `${data.total_items} products` : "…"}</span></div>
        <p className="mt-1 text-xs text-slate-500">{newer ? "Sets released within the last 3 years" : "Sets released 3 or more years ago"}</p>
        <p className="mt-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Ranked by {filters.sortBy === "momentum_desc" ? `${filters.period}-day growth` : sorts[filters.sortBy].toLowerCase()}</p>
      </div>
      {items.length > 0 && <ol className="space-y-2">{items.map((item, index) => <ProductRow key={item.card_id} item={item} rank={index + 1} period={filters.period} />)}</ol>}
      {loading && <div role="status" className="space-y-3 p-5"><span className="text-xs text-slate-500">Loading {newer ? "newer" : "older"} products…</span>{!items.length && [0, 1, 2].map((n) => <div key={n} className="h-24 animate-pulse rounded-xl bg-slate-100" />)}</div>}
      <CacheNotice metadata={cacheMetadata} />
      {error && <div role="alert" className="m-4 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}<button type="button" className="ml-2 font-semibold underline" onClick={() => data ? loadMore(true) : setRetry((n) => n + 1)}>Retry</button></div>}
      {!loading && !error && !items.length && <div className="px-6 py-16 text-center"><p className="text-sm font-semibold text-slate-700">No matching {newer ? "newer" : "older"} products</p><p className="mt-2 text-xs text-slate-500">Try another language or product type, or clear your filters.</p></div>}
      {!error && data && data.page < data.total_pages && <div className="border-t border-slate-100 p-4"><button type="button" disabled={loading} onClick={() => void loadMore()} className="min-h-10 w-full rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-slate-900 disabled:opacity-50">{loading ? "Loading…" : `Load more ${newer ? "newer" : "older"} products`}</button></div>}
    </section>
  );
}

export function SealedSignalsDashboard({ initialData }: { initialData: Record<Era, SealedSignalsResponse | null> }) {
  const params = useSearchParams();
  const [game, setGame] = useState<GameLanguage>((Object.hasOwn(languages, params.get("game") ?? "") ? params.get("game") : "all") as GameLanguage);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [debounced, setDebounced] = useState(query);
  const [productType, setProductType] = useState<SealedProductType>((Object.hasOwn(products, params.get("type") ?? "") ? params.get("type") : "all") as SealedProductType);
  const [signal, setSignal] = useState<SealedSignalType>((Object.hasOwn(signals, params.get("signal") ?? "") ? params.get("signal") : "all") as SealedSignalType);
  const [sortBy, setSortBy] = useState<SealedSortOption>((Object.hasOwn(sorts, params.get("sort") ?? "") ? params.get("sort") : "momentum_desc") as SealedSortOption);
  const [period, setPeriod] = useState<30 | 90>(params.get("period") === "90" ? 90 : 30);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setDebounced(query.trim()), 250); return () => clearTimeout(timer); }, [query]);
  useEffect(() => {
    function restore() {
      const p = new URLSearchParams(window.location.search);
      setGame((Object.hasOwn(languages, p.get("game") ?? "") ? p.get("game") : "all") as GameLanguage);
      setPeriod(p.get("period") === "90" ? 90 : 30);
      setQuery(p.get("q") ?? ""); setDebounced(p.get("q") ?? "");
      setProductType((Object.hasOwn(products, p.get("type") ?? "") ? p.get("type") : "all") as SealedProductType);
      setSignal((Object.hasOwn(signals, p.get("signal") ?? "") ? p.get("signal") : "all") as SealedSignalType);
      setSortBy((Object.hasOwn(sorts, p.get("sort") ?? "") ? p.get("sort") : "momentum_desc") as SealedSortOption);
    }
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    for (const [name, value, fallback] of [["game", game, "all"], ["period", String(period), "30"], ["q", debounced, ""], ["type", productType, "all"], ["signal", signal, "all"], ["sort", sortBy, "momentum_desc"]]) {
      if (value === fallback) url.searchParams.delete(name); else url.searchParams.set(name, value);
    }
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [debounced, productType, signal, sortBy, period, game]);
  const filters = useMemo(() => ({ query: debounced, productType, signal, sortBy, period, game }), [debounced, productType, signal, sortBy, period, game]);
  const key = JSON.stringify(filters);
  const defaults = game === "all" && period === 30 && !debounced && productType === "all" && signal === "all" && sortBy === "momentum_desc";
  function reset() { setGame("all"); setPeriod(30); setQuery(""); setDebounced(""); setProductType("all"); setSignal("all"); setSortBy("momentum_desc"); }
  return (
    <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 font-mono sm:px-6 lg:px-8">
      <header className="mb-6">
        <div className="mb-3 inline-flex flex-wrap items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-emerald-500" />
          <span>SEALED MARKET</span>
          <span aria-hidden="true" className="text-slate-300">|</span>
          <span className="text-slate-500">TCG MARKET PRICES</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">Sealed Signals</h1>
        <p className="mt-2 max-w-2xl text-xs leading-relaxed text-slate-600 sm:text-sm">Compare {period}-day price growth across newer releases and older sealed products, ranked independently in each era.</p>
      </header>
      <div className="mb-4 border-y border-slate-200 py-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1"><label htmlFor="sealed-search" className="sr-only">Search sealed products</label><SearchInput id="sealed-search" value={query} onChange={setQuery} placeholder="Search products or sets…" inputClassName="min-h-10" /></div>
          <div className="sm:w-48"><label htmlFor="sealed-type" className="sr-only">Product type</label><select id="sealed-type" className={selectClass} value={productType} onChange={(e) => setProductType(e.target.value as SealedProductType)}>{Object.entries(products).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
          <button type="button" aria-expanded={expanded} aria-controls="sealed-more-filters" onClick={() => setExpanded(!expanded)} className="min-h-10 shrink-0 rounded-lg border border-slate-200 bg-white px-4 text-xs font-bold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-slate-900 aria-expanded:border-slate-900 aria-expanded:bg-slate-900 aria-expanded:text-white">Filters & sort{signal !== "all" || sortBy !== "momentum_desc" ? " •" : ""} <span aria-hidden="true">{expanded ? "−" : "+"}</span></button>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
          <div role="group" aria-label="Product language" className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-slate-500">Language</span>
            <div className="inline-flex gap-1 rounded-lg bg-slate-100 p-1">
              {(Object.entries(languages) as [GameLanguage, string][]).map(([value, label]) => <button key={value} type="button" aria-pressed={game === value} onClick={() => setGame(value)} className="min-h-9 rounded-lg px-3 text-xs font-bold text-slate-600 transition hover:bg-slate-200 focus-visible:outline-slate-900 aria-pressed:bg-slate-900 aria-pressed:text-white aria-pressed:shadow-xs">{label}</button>)}
            </div>
          </div>
          <div role="group" aria-label="Comparison period" className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-slate-500">Comparison period</span>
            <div className="inline-flex gap-1 rounded-lg bg-slate-100 p-1">
              {([30, 90] as const).map((days) => <button key={days} type="button" aria-pressed={period === days} onClick={() => setPeriod(days)} className="min-h-9 rounded-lg px-3 text-xs font-bold text-slate-600 transition hover:bg-slate-200 focus-visible:outline-slate-900 aria-pressed:bg-slate-900 aria-pressed:text-white aria-pressed:shadow-xs">{days} days</button>)}
            </div>
          </div>
          <span className="text-[10px] text-slate-400">USD source prices · TCG API</span>
        </div>
        {expanded && <div id="sealed-more-filters" className="mt-3 grid gap-3 border-t border-slate-100 pt-3 sm:grid-cols-2"><label className="text-xs font-medium text-slate-600">Signal<select className={`${selectClass} mt-1`} value={signal} onChange={(e) => setSignal(e.target.value as SealedSignalType)}>{Object.entries(signals).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-xs font-medium text-slate-600">Rank by<select className={`${selectClass} mt-1`} value={sortBy} onChange={(e) => setSortBy(e.target.value as SealedSortOption)}>{Object.entries(sorts).map(([value, label]) => <option key={value} value={value}>{value === "momentum_desc" ? `${period}-day growth` : label}</option>)}</select></label></div>}
        {!defaults && <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-xs text-slate-600"><span>{[game !== "all" && languages[game], period !== 30 && `${period}-day growth`, debounced && `“${debounced}”`, productType !== "all" && products[productType], signal !== "all" && signals[signal], sortBy !== "momentum_desc" && sorts[sortBy]].filter(Boolean).join(" · ")}</span><button type="button" onClick={reset} className="ml-auto min-h-8 font-semibold text-slate-700 hover:text-slate-950 hover:underline">Reset filters</button></div>}
      </div>
      <p className="mb-6 text-[11px] leading-relaxed text-slate-500">{period}-day growth is historical price change before fees, not projected ROI.</p>
      <div className="grid items-start gap-5 lg:grid-cols-2">{(["newer", "older"] as const).map((era) => <RankingColumn key={`${era}:${key}`} era={era} filters={filters} initial={defaults ? initialData[era] : null} />)}</div>
      <p className="mt-5 text-xs leading-relaxed text-slate-500">Era is based on the set release date, not confirmed print status. Products with unknown or future release dates are excluded. Missing return data appears last; the signal score is a separate supply, demand, age, and momentum indicator.</p>
    </div>
  );
}
