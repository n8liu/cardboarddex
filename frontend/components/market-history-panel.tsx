"use client";
import { useState } from "react";
import type { HistoryPoint, PriceFreshness as Freshness } from "@/types/market-data";

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
  const segment: string[] = [];
  for (const point of points) {
    if (point.market_price == null) continue;
    segment.push(`${4 + (Date.parse(point.date) - start) / duration * 292},${54 - (point.market_price - min) / (max - min || 1) * 44}`);
  }
  if (segment.length) segments.push(segment.join(" "));
  return <svg viewBox="0 0 300 64" role="img" aria-label={`Market price history from ${points[0].date} to ${points[points.length - 1].date}`} className="my-2 h-20 w-full text-emerald-700"><title>Recorded market prices in USD; lines connect observations, intervening prices are unknown</title>{segments.map((line, index) => <polyline key={index} points={line} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />)}</svg>;
}

export function PurchaseReturn({ price }: { price: number | null | undefined }) {
  const [cost, setCost] = useState("");
  const paid = Number(cost);
  const gain = price != null && cost.trim() !== "" && Number.isFinite(paid) && paid > 0 ? (price / paid - 1) * 100 : null;
  return <div className="mt-3 rounded-xl bg-slate-50 p-3"><label className="text-xs text-slate-600">Your total purchase cost (USD)<input type="number" min="0.01" step="0.01" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} className="ml-2 w-28 rounded-lg border border-slate-300 p-2" placeholder="100.00" /></label><p aria-live="polite" className="mt-2 text-xs text-slate-600">{gain == null ? "Enter a positive cost to estimate your return." : `Estimated unrealized return: ${gain >= 0 ? "+" : ""}${gain.toFixed(1)}% before selling fees and taxes.`}</p></div>;
}
