"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import Image from "@/components/card-image";
import { CardLink } from "@/components/card-link";
import { PriceHistoryChart, type ValueFormatter } from "@/components/price-history-chart";
import { EmptyState } from "@/components/ui/empty-state";
import { useCurrency } from "@/context/currency-context";
import { cardImageUrl, getCard, getCardPricing, searchCards } from "@/lib/api";
import { indexToFirstValue, mergeProviderHistory, primaryMarketSeries } from "@/lib/provider-history";
import { shimmerBlurDataUrl } from "@/lib/shimmer";
import { writeUrlFilters } from "@/lib/url-state";
import type { CardDetail, CardPricing, CardSummary } from "@/types/card";

export const MAX_COMPARE = 4;
const COLORS = ["#e11d48", "#0891b2", "#d97706", "#4f46e5"];
const RANGES = [{ days: 90, label: "3M" }, { days: 180, label: "6M" }, { days: 365, label: "1Y" }] as const;

type Entry = { card: CardDetail | null; pricing: CardPricing | null; failed: boolean };

/** Unique, non-empty ids from `?ids=a,b,c`, at most four. */
export function parseCompareIds(raw: string | null): string[] {
  return [...new Set((raw ?? "").split(",").map((id) => id.trim()).filter(Boolean))].slice(0, MAX_COMPARE);
}

const indexFormat: ValueFormatter = (value, compact) => {
  const change = value - 100;
  return `${change >= 0 ? "+" : ""}${compact ? Math.round(change) : change.toFixed(1)}%`;
};

export function CompareDashboard() {
  const params = useSearchParams();
  const ids = useMemo(() => parseCompareIds(params.get("ids")), [params]);
  const { formatPrice } = useCurrency();
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [mode, setMode] = useState<"index" | "price">("index");
  const [days, setDays] = useState<number>(180);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CardSummary[]>([]);
  const [searching, setSearching] = useState(false);

  // Each card loads once; removed cards keep their entry in case they are added back.
  useEffect(() => {
    for (const id of ids) {
      if (entries[id]) continue;
      setEntries((current) => ({ ...current, [id]: { card: null, pricing: null, failed: false } }));
      Promise.all([getCard(id), getCardPricing(id)]).then(([card, pricing]) => {
        setEntries((current) => ({ ...current, [id]: { card, pricing, failed: !card } }));
      }).catch((err) => {
        console.error(`[Compare] Failed loading card ${id}:`, err);
        setEntries((current) => ({ ...current, [id]: { card: null, pricing: null, failed: true } }));
      });
    }
  }, [ids, entries]);

  useEffect(() => {
    const clean = query.trim();
    if (clean.length < 2) { setResults([]); setSearching(false); return; }
    const controller = new AbortController();
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchCards(clean, { limit: 6, abortSignal: controller.signal })
        .then((cards) => setResults(cards))
        .catch((err) => { if (!controller.signal.aborted) { console.error("[Compare] Card search failed:", err); setResults([]); } })
        .finally(() => { if (!controller.signal.aborted) setSearching(false); });
    }, 200);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query]);

  const setIds = (next: string[]) => writeUrlFilters({ ids: next.join(",") || null });
  const add = (id: string) => { if (!ids.includes(id) && ids.length < MAX_COMPARE) setIds([...ids, id]); setQuery(""); setResults([]); };
  const remove = (id: string) => setIds(ids.filter((item) => item !== id));

  const plotted = ids.flatMap((id, index) => {
    const entry = entries[id];
    const history = entry?.pricing?.market_history_series ?? entry?.pricing?.provider_history ?? [];
    const quotes = entry?.pricing?.market_quotes ?? entry?.pricing?.provider_quotes ?? [];
    const series = primaryMarketSeries(history, quotes.find((quote) => quote.primary && !quote.grade));
    if (!entry?.card || !series) return [];
    return [{ id, series: { ...series, id: `card:${id}` }, name: `${entry.card.name} · ${entry.card.set_name}`, color: COLORS[index % COLORS.length] }];
  });
  const today = new Date().toISOString().slice(0, 10);
  const rows = mergeProviderHistory([], plotted.map((item) => item.series), new Date(Date.now() - days * 86400000).toISOString().slice(0, 10), today);
  const keys = plotted.map((item) => item.series.id);
  const data = mode === "index" ? indexToFirstValue(rows, keys) : rows;
  const currency = plotted[0]?.series.currency ?? "USD";

  return (
    <div className="mx-auto min-w-0 max-w-[1200px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
      <header className="mb-6">
        <h1 className="text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">Compare cards</h1>
        <p className="mt-1 text-xs text-slate-600 sm:text-sm">Up to {MAX_COMPARE} cards on one chart, using each card&apos;s primary market price.</p>
      </header>

      <section aria-label="Cards being compared" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {ids.map((id, index) => {
          const entry = entries[id];
          const card = entry?.card;
          return <div key={id} className="flex min-w-0 items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3" style={{ borderLeft: `4px solid ${COLORS[index % COLORS.length]}` }}>
            {card ? <>
              <div className="relative h-14 w-10 shrink-0 overflow-hidden rounded bg-slate-50">
                <Image src={cardImageUrl(card.image_url)} alt={card.name} fill sizes="40px" className="object-contain" placeholder="blur" blurDataURL={shimmerBlurDataUrl(40, 56)} />
              </div>
              <div className="min-w-0 flex-1">
                <CardLink href={`/cards/${encodeURIComponent(card.id)}`} className="block truncate text-sm font-bold text-slate-950 hover:underline">{card.name}</CardLink>
                <p className="truncate text-[11px] text-slate-500">{card.set_name} · #{card.number}</p>
                <p className="font-mono text-sm font-black">{formatPrice(card.market_price, { showPending: true })}</p>
              </div>
            </> : <p className="flex-1 text-xs text-slate-500">{entry?.failed ? `Card ${id} could not be loaded.` : "Loading…"}</p>}
            <button type="button" onClick={() => remove(id)} aria-label={`Remove ${card?.name ?? id}`} className="shrink-0 rounded-full px-2 text-lg leading-none text-slate-400 hover:text-slate-900">×</button>
          </div>;
        })}
        {ids.length < MAX_COMPARE && <div className="relative rounded-2xl border border-dashed border-slate-300 bg-white/60 p-3">
          <label htmlFor="compare-search" className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Add a card</label>
          <input id="compare-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name…" autoComplete="off"
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500" />
          {(results.length > 0 || searching) && <ul role="listbox" aria-label="Search results" className="absolute inset-x-3 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
            {searching && !results.length && <li className="px-2 py-2 text-xs text-slate-400">Searching…</li>}
            {results.map((card) => <li key={card.id} role="option" aria-selected={false}>
              <button type="button" onClick={() => add(card.id)} disabled={ids.includes(card.id)}
                className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-slate-100 disabled:opacity-40">
                <span className="min-w-0"><span className="block truncate font-semibold">{card.name}</span><span className="block truncate text-slate-500">{card.set_name} · #{card.number}</span></span>
                <span className="shrink-0 font-mono">{formatPrice(card.market_price, { showPending: true })}</span>
              </button>
            </li>)}
          </ul>}
        </div>}
      </section>

      <section aria-label="Price comparison chart" className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div role="group" aria-label="Scale" className="flex gap-1.5">
            {([["index", "% change"], ["price", "Price"]] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)}
              className={`rounded-lg border px-2.5 py-1 font-semibold ${mode === value ? "border-slate-900 bg-slate-900 text-white" : "border-stone-200 bg-white text-slate-600"}`}>{label}</button>)}
          </div>
          <div role="group" aria-label="Range" className="flex gap-1.5">
            {RANGES.map((range) => <button key={range.days} type="button" aria-pressed={days === range.days} onClick={() => setDays(range.days)}
              className={`rounded-lg px-2.5 py-1 font-semibold ${days === range.days ? "bg-slate-950 text-white" : "border border-stone-200 bg-white text-slate-600"}`}>{range.label}</button>)}
          </div>
        </div>
        {ids.length === 0 ? <EmptyState title="Pick cards to compare" description="Search above, or use Compare on any card page." className="min-h-[240px]" />
          : plotted.length === 0 ? <p className="py-16 text-center text-sm text-slate-500">{ids.some((id) => !entries[id] || (!entries[id].card && !entries[id].failed)) ? "Loading price history…" : "None of these cards has market price history yet."}</p>
          : <>
            <PriceHistoryChart data={data} currency={currency} label="Compared cards" extraSeries={plotted.map((item) => ({ key: item.series.id, name: item.name, color: item.color }))}
              formatValue={mode === "index" ? indexFormat : undefined} />
            {mode === "index" && <p className="mt-2 text-[11px] text-slate-500">Each line starts at 0% on its first recorded day in this range.</p>}
            {plotted.length < ids.length && <p className="mt-1 text-[11px] text-amber-700">Some cards have no market price history and are not plotted.</p>}
          </>}
      </section>
    </div>
  );
}
