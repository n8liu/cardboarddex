"use client";
import { useEffect, useState } from "react";
import { getMarketHistory } from "@/lib/api";
import { useCurrency } from "@/context/currency-context";
import type { HistoryPoint, MarketHistory, PriceFreshness as Freshness } from "@/types/market-data";

export function PriceFreshness({ value }: { value: Freshness }) {
  return <p className={`text-xs ${value.price_freshness === "stale" ? "text-amber-800" : "text-slate-500"}`}>
    {value.market_price_as_of ? `Price dated ${value.market_price_as_of}${value.price_freshness === "stale" ? " · Stale price (over 7 days)" : ""}` : "Market price date unavailable"}
    {value.checked_at ? ` · Provider checked ${value.checked_at.slice(0, 10)}` : ""}
  </p>;
}

export function HistorySparkline({ points }: { points: HistoryPoint[] }) {
  const priced = points.filter((p) => p.market_price != null);
  if (priced.length < 2) return <p className="py-3 text-xs text-slate-500">Not enough price history for a chart.</p>;
  const values = priced.map((p) => p.market_price!);
  const min = Math.min(...values), max = Math.max(...values);
  const times = points.map((p) => Date.parse(p.date));
  const start = Math.min(...times), duration = Math.max(...times) - start || 1;
  const segments: string[] = [];
  let segment: string[] = [];
  for (const point of points) {
    if (point.market_price == null) { if (segment.length) segments.push(segment.join(" ")); segment = []; continue; }
    segment.push(`${4 + (Date.parse(point.date) - start) / duration * 292},${54 - (point.market_price - min) / (max - min || 1) * 44}`);
  }
  if (segment.length) segments.push(segment.join(" "));
  return <svg viewBox="0 0 300 64" role="img" aria-label={`Market price history from ${points[0].date} to ${points[points.length - 1].date}`} className="my-2 h-20 w-full text-emerald-700"><title>Observed market prices in USD; no prices are backfilled</title>{segments.map((line, index) => <polyline key={index} points={line} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />)}</svg>;
}

export function PurchaseReturn({ price }: { price: number | null | undefined }) {
  const [cost, setCost] = useState("");
  const paid = Number(cost);
  const gain = price != null && cost.trim() !== "" && Number.isFinite(paid) && paid > 0 ? (price / paid - 1) * 100 : null;
  return <div className="mt-3 rounded-xl bg-slate-50 p-3"><label className="text-xs text-slate-600">Your total purchase cost (USD)<input type="number" min="0.01" step="0.01" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} className="ml-2 w-28 rounded-lg border border-slate-300 p-2" placeholder="100.00" /></label><p aria-live="polite" className="mt-2 text-xs text-slate-600">{gain == null ? "Enter a positive cost to estimate your return." : `Estimated unrealized return: ${gain >= 0 ? "+" : ""}${gain.toFixed(1)}% before selling fees and taxes.`}</p></div>;
}

export function MarketHistoryPanel({ cardId }: { cardId: string }) {
  const [days, setDays] = useState<30 | 90 | 365>(30);
  const [data, setData] = useState<MarketHistory | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const { formatPrice } = useCurrency();
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError("");
    getMarketHistory(cardId, days, controller.signal).then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((err) => { if (!controller.signal.aborted) { console.error("Market history load failed:", err); setError("Price history could not be loaded."); } });
    return () => controller.abort();
  }, [cardId, days, retry]);
  return <section aria-label="Historical performance" className="my-5 rounded-2xl border border-slate-200 bg-white p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold text-slate-900">Historical performance</h2><label className="text-xs text-slate-600">Period <select value={days} onChange={(e) => setDays(Number(e.target.value) as 30 | 90 | 365)} className="rounded-lg border border-slate-300 p-2">{[30, 90, 365].map((n) => <option key={n} value={n}>{n} days</option>)}</select></label></div>
    {error ? <p role="alert" className="mt-3 text-sm text-rose-700">{error} <button onClick={() => setRetry((n) => n + 1)} className="underline">Retry</button></p> : !data ? <p role="status" className="py-6 text-sm text-slate-500">Loading history…</p> : <>
      <p className="mt-3 text-sm font-semibold">Market price {formatPrice(data.market_price)}</p><PriceFreshness value={data} />
      <p className="mt-3 text-sm text-slate-700">{data.return_percent == null ? `${days}-day return unavailable: an exact baseline and a recent ending price are required.` : `${days}-day price growth: ${data.return_percent > 0 ? "+" : ""}${data.return_percent.toFixed(1)}% · Ending ${data.return_end}`}</p>
      <HistorySparkline points={data.points} />
      <p className="text-xs text-slate-500">{data.coverage_start ? `Coverage: ${data.coverage_start} – ${data.coverage_end} · ${data.points.length} observations · ${data.printing}` : "History has not been synced or is unavailable for this product."}{data.status === "restricted" ? " Provider access is restricted by the current plan or credentials." : data.status === "error" ? " The last provider sync failed; any displayed history is from an earlier sync." : ""}</p>
      <p className="mt-1 text-xs text-slate-500">Historical price growth is before fees and does not predict future returns. Coverage depends on the provider plan.</p>
      <details className="mt-3 text-xs"><summary className="cursor-pointer font-semibold text-emerald-800">View observed prices and sales</summary><div className="max-h-64 overflow-auto"><table className="mt-2 w-full text-left"><thead><tr><th>Date (UTC)</th><th>Market price</th><th>Reported sales</th></tr></thead><tbody>{data.points.map((p) => <tr key={p.date}><td className="py-1">{p.date}</td><td>{p.market_price == null ? "Unavailable" : formatPrice(p.market_price)}</td><td>{p.sales_volume ?? "Not reported"}</td></tr>)}</tbody></table></div></details>
      <PurchaseReturn price={data.market_price} />
    </>}
  </section>;
}
