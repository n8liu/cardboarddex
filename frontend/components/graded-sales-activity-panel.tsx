"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Image from "@/components/card-image";
import { cardImageUrl, getGradedSalesActivity } from "@/lib/api";
import type { GradedSalesActivity } from "@/types/market-data";
import { IMAGE_HOVER, TILE_HOVER } from "@/lib/card-hover";
import { EmptyState } from "@/components/ui/empty-state";

const emptyMessages = {
  provider_disabled: "Graded sales rankings are not enabled yet.",
  not_synced: "No graded sales counts have been synced yet. Missing counts do not mean zero sales.",
  no_matches: "No synced graded sales counts match this search. Try another card or set.",
};

/** Full-view grid shared with the Trending Cards and Popular Pokémon tabs. */
export const TILE_GRID_CLASS = "grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6";

function SalesDetails({ item }: { item: GradedSalesActivity["items"][number] }) {
  return <>
    <p className="mt-1.5 text-sm font-bold text-emerald-800">{item.sales.toLocaleString()} reported graded sales</p>
    <p className="mt-0.5 text-[11px] text-slate-500">Latest sale {item.last_sale_date || "unknown"}</p>
    <p className={`text-[11px] ${item.stale ? "text-amber-800" : "text-slate-500"}`}>{item.stale ? "Stale snapshot · " : ""}{item.synced_at ? `Last synced ${item.synced_at.slice(0, 10)}` : "Sync date unknown"}</p>
  </>;
}

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
      : data.status !== "ready" ? <EmptyState compact className="my-4" variant={data.status === "no_matches" ? "empty" : "collecting"}
        title={data.status === "no_matches" ? "No matching graded sales" : "Graded sales not available yet"} description={emptyMessages[data.status]} />
      : <>
        <p className="my-3 text-xs text-slate-500">{data.products_with_sales_data.toLocaleString()} synced cards with reported counts</p>
        {compact ? <ol className="space-y-2">{data.items.slice(0, 15).map((item, index) => <li key={item.card_id}>
          <Link href={`/cards/${encodeURIComponent(item.card_id)}?ref=trending`} prefetch={false} className="flex min-w-0 items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 hover:border-emerald-500">
            <span className="w-5 shrink-0 text-xs text-slate-500">{index + 1}.</span>
            {item.image_url && <Image src={cardImageUrl(item.image_url)} alt="" width={56} height={78} className="h-[78px] w-14 shrink-0 object-contain" />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-slate-900">{item.name}</p>
              <p className="truncate text-[11px] text-slate-500">{item.set_name}</p>
              <SalesDetails item={item} />
            </div>
          </Link>
        </li>)}</ol>
        : <ol className={TILE_GRID_CLASS}>{data.items.slice(0, 50).map((item, index) => <li key={item.card_id} className="min-w-0">
          <Link href={`/cards/${encodeURIComponent(item.card_id)}?ref=trending`} prefetch={false} className={`group flex h-full min-w-0 flex-col rounded-xl border border-slate-200 bg-white p-3 ${TILE_HOVER}`}>
            <span className="text-xs text-slate-500">{index + 1}.</span>
            <div className="relative mt-2 aspect-[5/7] w-full">
              {item.image_url && <Image src={cardImageUrl(item.image_url)} alt="" fill sizes="(min-width: 1536px) 16vw, (min-width: 1280px) 20vw, (min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw" className={`object-contain p-1.5 ${IMAGE_HOVER}`} />}
            </div>
            <p className="mt-3 truncate text-sm font-semibold text-slate-900">{item.name}</p>
            <p className="truncate text-[11px] text-slate-500">{item.set_name}</p>
            <SalesDetails item={item} />
          </Link>
        </li>)}</ol>}
      </>}
  </section>;
}
