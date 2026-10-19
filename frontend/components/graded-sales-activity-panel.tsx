"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Image from "@/components/card-image";
import { cardImageUrl, getGradedSalesActivity } from "@/lib/api";
import type { GradedSalesActivity } from "@/types/market-data";

const emptyMessages = {
  provider_disabled: "Graded sales rankings are not enabled yet.",
  not_synced: "No graded sales counts have been synced yet. Missing counts do not mean zero sales.",
  no_matches: "No synced graded sales counts match this search. Try another card or set.",
};

export function GradedSalesActivityPanel({ compact = false, query = "" }: { compact?: boolean; query?: string }) {
  const [data, setData] = useState<GradedSalesActivity | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    const timer = setTimeout(() => {
      getGradedSalesActivity(query, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setData(result); })
        .catch((err) => {
          if (!controller.signal.aborted) {
            console.error("Graded sales activity request failed:", err);
            setError("Graded sales activity could not be loaded.");
          }
        });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, retry]);

  return <section aria-label="Graded sales activity" className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50/50 p-4 font-mono">
    <h2 className="text-sm font-bold text-slate-900">Graded Sales Activity</h2>
    <p className="mt-2 text-xs leading-relaxed text-slate-500">{data?.coverage || "Graded sales reported by Pokémon Price Tracker. Provider-reported coverage; not a selected-period total."}</p>
    {error ? <p role="alert" className="mt-4 text-sm text-rose-700">{error} <button type="button" onClick={() => setRetry((n) => n + 1)} className="underline">Retry graded sales</button></p>
      : !data ? <p role="status" className="py-6 text-sm text-slate-500">Loading graded sales…</p>
      : data.status !== "ready" ? <p className="my-4 text-sm text-slate-700">{emptyMessages[data.status]}</p>
      : <>
        <p className="my-3 text-xs text-slate-500">{data.products_with_sales_data.toLocaleString()} synced cards with reported counts</p>
        <ol className="space-y-2">{data.items.slice(0, compact ? 15 : 50).map((item, index) => <li key={item.card_id}>
          <Link href={`/cards/${encodeURIComponent(item.card_id)}?ref=trending`} prefetch={false} className="block rounded-xl border border-slate-200 bg-white p-3 hover:border-emerald-500">
            <div className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 text-xs text-slate-500">{index + 1}.</span>
              {item.image_url && <Image src={cardImageUrl(item.image_url)} alt="" width={28} height={40} className="shrink-0 object-contain" />}
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-900">{item.name}</p><p className="truncate text-[11px] text-slate-500">{item.set_name}</p></div>
            </div>
            <p className="mt-2 text-sm font-bold text-emerald-800">{item.sales.toLocaleString()} reported graded sales</p>
            <p className="mt-1 break-words text-[11px] text-slate-600">{item.grades.map((grade) => `${grade.grade}: ${grade.sales.toLocaleString()}`).join(" · ")}</p>
            <p className="mt-1 text-[11px] text-slate-500">Latest sale {item.last_sale_date || "unknown"}</p>
            <p className={`mt-1 text-[11px] ${item.stale ? "text-amber-800" : "text-slate-500"}`}>{item.stale ? "Stale snapshot · " : ""}{item.synced_at ? `Last synced ${item.synced_at.slice(0, 10)}` : "Sync date unknown"}</p>
          </Link>
        </li>)}</ol>
      </>}
  </section>;
}
