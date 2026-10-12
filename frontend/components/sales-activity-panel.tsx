"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getSalesActivity } from "@/lib/api";
import type { SalesActivity } from "@/types/market-data";

export function SalesActivityPanel({ compact = false, query = "" }: { compact?: boolean; query?: string }) {
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [data, setData] = useState<SalesActivity | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError("");
    const timer = setTimeout(() => {
      getSalesActivity(days, query, controller.signal).then((result) => { if (!controller.signal.aborted) setData(result); })
        .catch((err) => { if (!controller.signal.aborted) { console.error("Sales activity request failed:", err); setError("Provider sales activity could not be loaded."); } });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [days, query, retry]);
  return <section aria-label="Provider sales activity" className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-bold text-slate-900">Provider sales activity</h2><label className="text-xs text-slate-500">Sales period <select value={days} onChange={(e) => setDays(Number(e.target.value) as 7 | 30 | 90)} className="rounded-lg border border-slate-200 bg-white p-2">{[7, 30, 90].map((n) => <option key={n} value={n}>{n} days</option>)}</select></label></div>
    <p className="mt-2 text-xs leading-relaxed text-slate-500">TCG API reported sales across synced products and printings. Missing days are unknown; the newest 1–3 days may be incomplete.</p>
    {error ? <p role="alert" className="mt-4 text-sm text-rose-700">{error} <button onClick={() => setRetry((n) => n + 1)} className="underline">Retry</button></p> : !data ? <p role="status" className="py-6 text-sm text-slate-500">Loading reported sales…</p> : <>
      <p className="my-4 text-sm text-slate-700">{data.total_sales == null ? "Sales data unavailable for this selection." : `${data.total_sales.toLocaleString()} reported sales · ${data.products_with_sales_data} products with data`}</p>
      {data.synced_at && <p className="mb-3 text-[11px] text-slate-500">Last history sync {data.synced_at.slice(0, 10)} · Window {data.start} – {data.end}</p>}
      <ol className="space-y-2">{data.items.slice(0, compact ? 15 : 50).map((item, index) => <li key={item.card_id}><Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 hover:border-emerald-500"><div className="min-w-0"><p className="text-sm font-semibold text-slate-900">{index + 1}. {item.name}</p><p className="mt-1 text-[11px] text-slate-500">{item.set_name} · Latest reported day {item.last_reported_day}</p></div><span className="shrink-0 text-sm font-bold text-emerald-800">{item.sales.toLocaleString()} sales</span></Link></li>)}</ol>
    </>}
  </section>;
}
