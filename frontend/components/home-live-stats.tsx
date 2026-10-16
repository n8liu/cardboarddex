"use client";

import Link from "next/link";
import { useLiveCollectionStats } from "@/lib/use-live-collection-stats";
import { AnimatedNumber } from "@/components/ui/animated-number";

export function HomeLiveStats() {
  const { data, error, retry } = useLiveCollectionStats();
  return <section aria-label="Collection totals" className="mt-5">
    <dl className="grid gap-4 sm:grid-cols-3">
      {([["Catalog products", data?.products], ["Sets", data?.sets], ["Live comps", data?.price_observations]] as const).map(([label, value]) => <div key={label} className="rounded-xl border border-slate-200 bg-white/60 p-4">
        <dt className="text-[10px] uppercase tracking-wider text-slate-500">{label === "Live comps" ? <Link href="/live-updates" className="hover:underline">{label}</Link> : label}</dt>
        <dd className="mt-2 text-lg font-bold tabular-nums sm:text-2xl">{value != null ? <AnimatedNumber value={value} /> : error ? "Unavailable" : "…"}</dd>
      </div>)}
    </dl>
    <p className="mt-3 text-[10px] text-slate-500">{error ? <>{data ? "Showing last available totals." : "Totals could not be loaded."} <button type="button" onClick={retry} className="underline">Retry totals</button></> : "Refreshes every minute · Price records, not completed sales"}</p>
  </section>;
}
