"use client";
import { PriceComparison } from "@/components/price-comparison";
import { CacheNotice, useCacheNotice } from "@/components/cache-notice";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Image from "@/components/card-image";
import { HistorySparkline, PriceFreshness, PurchaseReturn } from "@/components/market-history-panel";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { SearchInput } from "@/components/ui/search-input";
import { useCurrency } from "@/context/currency-context";
import { cardImageUrl, getSealedSignals } from "@/lib/api";
import type { GameLanguage, SealedProductType, SealedSignalItem, SealedSignalsResponse, SealedSignalType, SealedSortOption } from "@/types/card";
import { IMAGE_HOVER, TILE_HOVER } from "@/lib/card-hover";

type Layout = "cards" | "table";
type View = "split" | "newer" | "older";
const readView = (value: string | null): View => value === "newer" || value === "older" ? value : "split";
const toggleClass = "rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:text-slate-900 focus-visible:outline-slate-900 aria-pressed:bg-white aria-pressed:font-bold aria-pressed:text-slate-950 aria-pressed:shadow-xs";
type Era = "newer" | "older";
type Filters = { game: GameLanguage; period: 30 | 90; query: string; productType: SealedProductType; signal: SealedSignalType; sortBy: SealedSortOption };
const languages = { all: "All", pokemon: "English", "pokemon-japan": "Japanese" };
const products = { all: "All products", booster_box: "Booster boxes", etb: "Elite Trainer Boxes", bundle: "Booster bundles", case: "Cases", pack: "Booster packs", blister: "Blisters", collection: "Collections & tins" };
const signals = { all: "All signals", strong_buy: "Strong buy", buy: "Buy", hold: "Hold", underperform: "Underperform" };
const sorts = { momentum_desc: "30-day growth", score_desc: "Signal score", price_asc: "Lowest price", price_desc: "Highest price", supply_asc: "Fewest listings", age_desc: "Oldest release" };
const selectClass = "py-2 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-800 transition hover:bg-slate-100 focus:border-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900/10";

function ProductDetails({ item }: { item: SealedSignalItem }) {
  return (
        <div className="mt-2 border-t border-slate-100 pt-3">
          <p className="mb-2">{item.product_type} · Signal score {item.signal_score}/100</p>
          <PriceFreshness value={item} />
          <HistorySparkline points={item.history?.points ?? []} />
          {item.history?.coverage_start && <p>History: {item.history.coverage_start} – {item.history.coverage_end}</p>}
          <p className="mt-3 font-semibold text-slate-700">Estimate return on your purchase</p>
          <PurchaseReturn price={item.market_price} />
          <p className="mt-2 text-[10px]">{item.market_source === "pokemonpricetracker" ? "Pokémon Price Tracker · " : "Legacy market history · "}{item.total_listings > 0 ? `${item.total_listings} active listings` : "Listing count unavailable"}{item.last_updated_at ? ` · Observed ${item.last_updated_at.slice(0, 10)}` : ""}</p>
        </div>
  );
}

function Growth({ item, period }: { item: SealedSignalItem; period: 30 | 90 }) {
  const growth = item.return_percent !== undefined ? item.return_percent : period === 30 ? item.price_change_30d : null;
  const known = growth != null && Number.isFinite(growth);
  return <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-bold ${known && growth > 0 ? "border-emerald-200/60 bg-emerald-50 text-emerald-700" : known && growth < 0 ? "border-rose-200/60 bg-rose-50 text-rose-700" : "border-slate-200 bg-slate-50 text-slate-500"}`}>{known ? `${growth > 0 ? "+" : ""}${growth.toFixed(1)}%` : "Unavailable"}</span>;
}

function ProductRow({ item, rank, period, era }: { item: SealedSignalItem; rank: number; period: 30 | 90; era: Era }) {
  const { formatPrice } = useCurrency();
  const [expanded, setExpanded] = useState(false);
  const detailsId = `${era}-${item.card_id}-details`;
  return <Fragment>
    <tr className="border-t border-slate-100 text-xs hover:bg-slate-50 focus-within:bg-slate-50">
      <td className="p-3 text-slate-400">#{rank}</td>
      <td className="p-3"><Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} className="flex items-center gap-3 font-bold hover:underline"><span className="relative h-20 w-14 shrink-0 rounded border border-slate-100 bg-slate-50"><Image src={cardImageUrl(item.image_url)} alt="" fill sizes="56px" className="object-contain" /></span><span className="min-w-28 max-w-52"><span className="line-clamp-2">{item.name}</span><span className="mt-1 block text-[10px] font-normal text-slate-500">{item.set_name} · {item.product_type}</span></span></Link></td>
      <td className="p-3 text-right"><Growth item={item} period={period} /></td>
      <td className="p-3 text-right font-bold">{formatPrice(item.market_price)}<PriceComparison value={item} period={`${period}d`} /></td>
      <td className="hidden p-3 text-slate-500 xl:table-cell">{item.signal_label}<span className="block">{item.signal_score}/100</span></td>
      <td className="p-3"><button type="button" aria-expanded={expanded} aria-controls={detailsId} aria-label={`Details for ${item.name}`} onClick={() => setExpanded(!expanded)} className="min-h-9 rounded-lg border border-slate-200 px-3 font-semibold hover:bg-slate-100">{expanded ? "Close" : "Details"}</button></td>
    </tr>
    <tr id={detailsId} hidden={!expanded}><td colSpan={6} className="px-4 pb-4 text-xs text-slate-500">{expanded && <ProductDetails item={item} />}</td></tr>
  </Fragment>;
}

function ProductCard({ item, rank, period }: { item: SealedSignalItem; rank: number; period: 30 | 90 }) {
  const { formatPrice } = useCurrency();
  const signalStyle = item.signal_label === "STRONG BUY" || item.signal_label === "BUY"
    ? "border-emerald-200/60 bg-emerald-50 text-emerald-700"
    : item.signal_label === "UNDERPERFORM" ? "border-rose-200/60 bg-rose-50 text-rose-700"
    : "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <li className={`group relative flex min-w-0 flex-col rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs focus-within:border-slate-400 ${TILE_HOVER}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700">#{String(rank).padStart(2, "0")} · {item.product_type}</span>
        <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${signalStyle}`}>{item.signal_label.replaceAll("_", " ")}</span>
      </div>
      <div className="flex gap-3.5">
        <Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} tabIndex={-1} aria-hidden="true" className="relative h-40 w-28 shrink-0 overflow-hidden rounded-xl border border-slate-100 bg-slate-50 sm:h-52 sm:w-36">
          <Image src={cardImageUrl(item.image_url)} alt="" fill sizes="(min-width: 640px) 144px, 112px" className={`object-contain p-1.5 ${IMAGE_HOVER}`} />
        </Link>
        <div className="flex min-w-0 flex-1 flex-col justify-between">
          <div>
            <p className="truncate text-[11px] font-semibold text-slate-400">{item.set_name}</p>
            <h3 className="mt-1 text-xs font-bold leading-snug text-slate-950 sm:text-sm"><Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} className="hover:underline focus-visible:outline-slate-900">{item.name}</Link></h3>
          </div>
          <div className="mt-3 text-[10px] leading-relaxed text-slate-500">
            <p>Released {item.release_date?.slice(0, 4) ?? "Unknown"}</p>
            <p className="mt-1">Signal score {item.signal_score}/100</p>
          </div>
        </div>
      </div>
      <div className="mt-3.5 flex flex-wrap items-end justify-between gap-2 border-t border-slate-100 pt-2.5">
        <div><span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Market price</span><p className="text-base font-black tabular-nums">{formatPrice(item.market_price)}</p></div>
        <div className="text-right"><p className="mb-1 text-[10px] text-slate-500">{period}-day growth</p><Growth item={item} period={period} /><PriceComparison value={item} period={`${period}d`} /></div>
      </div>
      <details className="mt-4 border-t border-slate-100 pt-3 text-[11px] text-slate-500">
        <summary className="cursor-pointer py-1 hover:text-slate-950">Price history & purchase return<span className="sr-only"> for {item.name}</span></summary>
        <ProductDetails item={item} />
      </details>
    </li>
  );
}

function useRanking({ era, filters, initial }: { era: Era; filters: Filters; initial?: SealedSignalsResponse | null }) {
  const [cacheMetadata, setCacheMetadata] = useCacheNotice();
  const filterKey = JSON.stringify(filters);
  const [loadedKey, setLoadedKey] = useState(filterKey);
  const generation = useRef(0);
  const moreController = useRef<AbortController | null>(null);
  const [data, setData] = useState(initial ?? null);
  const [items, setItems] = useState(initial?.items ?? []);
  const [loading, setLoading] = useState(!initial);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const mounted = useRef(false);
  const busy = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; moreController.current?.abort(); };
  }, []);
  useEffect(() => {
    generation.current += 1;
    moreController.current?.abort();
    busy.current = false;
    setLoadedKey(filterKey);
    setData(initial ?? null);
    setItems(initial?.items ?? []);
    setError("");
    setCacheMetadata(null);
    if (initial) { setLoading(false); return; }
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
  }, [era, filters, filterKey, initial, retry]);

  async function loadMore(bypassCache = false) {
    if (!data || busy.current) return;
    const requestGeneration = generation.current;
    const controller = new AbortController();
    moreController.current = controller;
    busy.current = true;
    setLoading(true);
    setError("");
    try {
      const result = await getSealedSignals({ ...filters, era, page: data.page + 1, perPage: 12, bypassCache, abortSignal: controller.signal, onCache: (metadata) => { if (mounted.current && requestGeneration === generation.current) setCacheMetadata(metadata); } });
      if (mounted.current && requestGeneration === generation.current) {
        setData(result);
        setItems((previous) => {
          const seen = new Set(previous.map((item) => item.card_id));
          return [...previous, ...result.items.filter((item) => !seen.has(item.card_id))];
        });
      }
    } catch (err) {
      console.error(`Failed loading more ${era} sealed products:`, err);
      if (mounted.current && requestGeneration === generation.current) setError("Could not load more products. Please try again.");
    } finally {
      if (requestGeneration === generation.current) busy.current = false;
      if (mounted.current && requestGeneration === generation.current) setLoading(false);
    }
  }
  const current = loadedKey === filterKey;
  return { data: current ? data : null, items: current ? items : [], loading: !current || loading, error: current ? error : "", cacheMetadata: current ? cacheMetadata : null, loadMore, retry: () => setRetry((n) => n + 1) };
}

function RankingColumn({ era, filters, ranking, layout, view }: { era: Era; filters: Filters; ranking: ReturnType<typeof useRanking>; layout: Layout; view: View }) {
  const { data, items, loading, error, cacheMetadata, loadMore, retry } = ranking;
  const newer = era === "newer";
  return (
    <section aria-labelledby={`${era}-heading`} aria-busy={loading} className="min-w-0">
      <div className="mb-3 border-b border-slate-200 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 id={`${era}-heading`} className="text-lg font-bold text-slate-950">{newer ? "Newer releases" : "Older & vintage"}</h2><span className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold tabular-nums text-slate-500">{data ? `${data.total_items} products` : "…"}</span></div>
        <p className="mt-1 text-xs text-slate-500">{newer ? "Sets released within the last 3 years" : "Sets released 3 or more years ago"}</p>
        <p className="mt-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Ranked by {filters.sortBy === "momentum_desc" ? `${filters.period}-day growth` : sorts[filters.sortBy].toLowerCase()}</p>
      </div>
      {items.length > 0 && (layout === "cards" ? <ol className={`grid grid-cols-1 items-start gap-4 sm:grid-cols-2 ${view === "split" ? "lg:grid-cols-1 xl:grid-cols-2" : "lg:grid-cols-3 xl:grid-cols-4"}`}>{items.map((item, index) => <ProductCard key={item.card_id} item={item} rank={index + 1} period={filters.period} />)}</ol> :
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-2xs" tabIndex={0} role="region" aria-label={`${newer ? "Newer" : "Older"} products table`}><table className="w-full text-left"><caption className="sr-only">{newer ? "Newer releases" : "Older & vintage"} rankings</caption><thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500"><tr><th className="p-3">#</th><th className="p-3">Product</th><th className="p-3 text-right">{filters.period}d growth</th><th className="p-3 text-right">Market / delta</th><th className="hidden p-3 xl:table-cell">Signal</th><th className="p-3">Details</th></tr></thead><tbody>{items.map((item, index) => <ProductRow key={item.card_id} item={item} rank={index + 1} period={filters.period} era={era} />)}</tbody></table></div>)}
      {loading && <div role="status" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2"><span className="col-span-full text-xs text-slate-500">Loading {newer ? "newer" : "older"} products…</span>{!items.length && [0, 1, 2, 3].map((n) => <div key={n} className="h-96 animate-pulse rounded-2xl bg-slate-100 motion-reduce:animate-none" />)}</div>}
      <CacheNotice metadata={cacheMetadata} />
      {error && <div role="alert" className="m-4 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}<button type="button" className="ml-2 font-semibold underline" onClick={() => data ? loadMore(true) : retry()}>Retry</button></div>}
      {!loading && !error && !items.length && <div className="px-6 py-16 text-center"><p className="text-sm font-semibold text-slate-700">No matching {newer ? "newer" : "older"} products</p><p className="mt-2 text-xs text-slate-500">Try another language or product type, or clear your filters.</p></div>}
      {!error && data && data.page < data.total_pages && <div className="border-t border-slate-100 p-4"><button type="button" disabled={loading} onClick={() => void loadMore()} className="min-h-10 w-full rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-slate-900 disabled:opacity-50">{loading ? "Loading…" : `Load more ${newer ? "newer" : "older"} products`}</button></div>}
    </section>
  );
}

function SealedResults({ filters, initialData, layout, view, children }: { filters: Filters; initialData: Record<Era, SealedSignalsResponse | null>; layout: Layout; view: View; children: ReactNode }) {
  const newer = useRanking({ era: "newer", filters, initial: initialData.newer });
  const older = useRanking({ era: "older", filters, initial: initialData.older });
  const rankings = { newer, older };
  const criterion = filters.sortBy === "momentum_desc" ? `${filters.period}-day growth` : sorts[filters.sortBy];
  return <>
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Sealed market summary">
      {(["newer", "older"] as const).map((era) => <div key={era} className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs"><p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">{era === "newer" ? "Newer products" : "Older products"}</p><p className="mt-1 text-xl font-black">{rankings[era].data ? <AnimatedNumber value={rankings[era].data!.total_items} /> : rankings[era].error ? "Unavailable" : "—"}</p><p className="mt-1 text-[11px] text-slate-500">Matching current filters</p></div>)}
      {(["newer", "older"] as const).map((era) => <div key={era} className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs"><p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">First-ranked {era} product</p><p className="mt-2 line-clamp-2 text-sm font-bold">{rankings[era].items[0]?.name ?? (rankings[era].error ? "Unavailable" : rankings[era].loading ? "—" : "No matching products")}</p><p className="mt-1 text-[11px] text-slate-500">Ranked by {criterion}</p></div>)}
    </div>
    {children}
    <p className="mb-6 text-[11px] leading-relaxed text-slate-500">{filters.period}-day growth is historical price change before fees, not projected ROI. Prices reflect stored observations; check product freshness below.</p>
    <div className={`grid items-start gap-10 ${view === "split" ? "lg:grid-cols-2" : ""}`}>
      {(["newer", "older"] as const).map((era) => <div key={era} hidden={view !== "split" && view !== era} className="min-w-0"><RankingColumn era={era} filters={filters} ranking={rankings[era]} layout={layout} view={view} /></div>)}
    </div>
  </>;
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
  const [view, setView] = useState<View>(readView(params.get("view")));
  const [layout, setLayout] = useState<Layout>(params.get("layout") === "table" ? "table" : "cards");
  useEffect(() => { const timer = setTimeout(() => setDebounced(query.trim()), 250); return () => clearTimeout(timer); }, [query]);
  useEffect(() => {
    function restore() {
      const p = new URLSearchParams(window.location.search);
      setGame((Object.hasOwn(languages, p.get("game") ?? "") ? p.get("game") : "all") as GameLanguage);
      setView(readView(p.get("view")));
      setLayout(p.get("layout") === "table" ? "table" : "cards");
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
    for (const [name, value, fallback] of [["game", game, "all"], ["period", String(period), "30"], ["q", debounced, ""], ["type", productType, "all"], ["signal", signal, "all"], ["sort", sortBy, "momentum_desc"], ["view", view, "split"], ["layout", layout, "cards"]]) {
      if (value === fallback) url.searchParams.delete(name); else url.searchParams.set(name, value);
    }
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [debounced, productType, signal, sortBy, period, game, view, layout]);
  const filters = useMemo(() => ({ query: debounced, productType, signal, sortBy, period, game }), [debounced, productType, signal, sortBy, period, game]);
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
        <h1 className="text-2xl font-black uppercase tracking-tight text-slate-950 sm:text-4xl">Sealed Signals</h1>
        <p className="mt-2 max-w-2xl text-xs leading-relaxed text-slate-600 sm:text-sm">Compare {period}-day price growth across newer releases and older sealed products, ranked independently in each era.</p>
      </header>
      <SealedResults filters={filters} initialData={defaults ? initialData : { newer: null, older: null }} layout={layout} view={view}>
      <div className="mb-4 rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <div role="group" aria-label="Era view" className="flex flex-wrap items-center gap-1 rounded-xl bg-slate-100 p-1">{([["split", "Split View"], ["newer", "Newer"], ["older", "Older"]] as const).map(([value, label]) => <button key={value} type="button" className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition focus-visible:outline-slate-900 ${view === value ? value === "newer" ? "bg-emerald-600 text-white shadow-sm" : value === "older" ? "bg-rose-600 text-white shadow-sm" : "bg-white text-slate-950 shadow-sm" : value === "newer" ? "text-emerald-700 hover:bg-emerald-50" : value === "older" ? "text-rose-700 hover:bg-rose-50" : "text-slate-600 hover:text-slate-900"}`} aria-pressed={view === value} onClick={() => setView(value)}>{label}</button>)}</div>
          <div role="group" aria-label="Result layout" className="flex items-center rounded-xl bg-slate-100 p-1">{(["cards", "table"] as const).map((value) => <button key={value} type="button" className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition focus-visible:outline-slate-900 ${layout === value ? "bg-white text-slate-950 shadow-xs font-bold" : "text-slate-600 hover:text-slate-900"}`} aria-pressed={layout === value} onClick={() => setLayout(value)}><span aria-hidden="true">{value === "cards" ? "⊞" : "☰"}</span><span>{value === "cards" ? "Cards" : "Table"}</span></button>)}</div>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1"><label htmlFor="sealed-search" className="sr-only">Search sealed products</label><SearchInput id="sealed-search" value={query} onChange={setQuery} placeholder="Search products or sets…" /></div>
          <div className="sm:w-48"><label htmlFor="sealed-type" className="sr-only">Product type</label><select id="sealed-type" className={selectClass} value={productType} onChange={(e) => setProductType(e.target.value as SealedProductType)}>{Object.entries(products).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
          <button type="button" aria-expanded={expanded} aria-controls="sealed-more-filters" onClick={() => setExpanded(!expanded)} className="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-slate-900 aria-expanded:border-slate-900 aria-expanded:bg-slate-900 aria-expanded:text-white">Filters & sort{signal !== "all" || sortBy !== "momentum_desc" ? " •" : ""} <span aria-hidden="true">{expanded ? "−" : "+"}</span></button>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
          <div role="group" aria-label="Product language" className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-slate-500">Language</span>
            <div className="inline-flex items-center gap-1 rounded-xl bg-slate-100 p-1">
              {(Object.entries(languages) as [GameLanguage, string][]).map(([value, label]) => <button key={value} type="button" aria-pressed={game === value} onClick={() => setGame(value)} className={`rounded-lg px-3 py-1.5 text-xs font-bold transition focus-visible:outline-slate-900 ${game === value ? value === "pokemon-japan" ? "bg-white text-red-950 shadow-xs font-black" : "bg-white text-slate-950 shadow-xs" : "text-slate-600 hover:text-slate-900"}`}>{label}</button>)}
            </div>
          </div>
          <div role="group" aria-label="Comparison period" className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-slate-500">Comparison period</span>
            <div className="inline-flex items-center gap-1 rounded-xl bg-slate-100 p-1">
              {([30, 90] as const).map((days) => <button key={days} type="button" aria-pressed={period === days} onClick={() => setPeriod(days)} className={toggleClass}>{days} days</button>)}
            </div>
          </div>
          <span className="text-[10px] text-slate-400">USD market prices · Source shown per product</span>
        </div>
        {expanded && <div id="sealed-more-filters" className="mt-3 grid gap-3 border-t border-slate-100 pt-3 sm:grid-cols-2"><label className="text-xs font-medium text-slate-600">Signal<select className={`${selectClass} mt-1`} value={signal} onChange={(e) => setSignal(e.target.value as SealedSignalType)}>{Object.entries(signals).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-xs font-medium text-slate-600">Rank by<select className={`${selectClass} mt-1`} value={sortBy} onChange={(e) => setSortBy(e.target.value as SealedSortOption)}>{Object.entries(sorts).map(([value, label]) => <option key={value} value={value}>{value === "momentum_desc" ? `${period}-day growth` : label}</option>)}</select></label></div>}
        {!defaults && <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-xs text-slate-600"><span>{[game !== "all" && languages[game], period !== 30 && `${period}-day growth`, debounced && `“${debounced}”`, productType !== "all" && products[productType], signal !== "all" && signals[signal], sortBy !== "momentum_desc" && sorts[sortBy]].filter(Boolean).join(" · ")}</span><button type="button" onClick={reset} className="ml-auto min-h-8 font-semibold text-slate-700 hover:text-slate-950 hover:underline">Reset filters</button></div>}
      </div>
      </SealedResults>
      <p className="mt-5 text-xs leading-relaxed text-slate-500">Era is based on the set release date, not confirmed print status. Products with unknown or future release dates are excluded. Missing return data appears last; the signal score is a separate supply, demand, age, and momentum indicator.</p>
    </div>
  );
}
