"use client";

import { AnimatedNumber } from "@/components/ui/animated-number";
import { POKEDEX_DATA } from "@/lib/pokedex-data";
import { useLiveCollectionStats } from "@/lib/use-live-collection-stats";

export function PokedexLiveStats() {
  const { data, error, retry } = useLiveCollectionStats();
  const totals = [
    { label: "Pokémon", value: POKEDEX_DATA.length, color: "text-emerald-700" },
    { label: "Cards Tracked", value: data?.products, color: "text-cyan-700" },
    { label: "Sets Indexed", value: data?.sets, color: "text-amber-700" },
    { label: "Verified Comps", value: data?.price_observations, color: "text-indigo-700" },
  ];
  return <section aria-label="Pokédex live totals">
    <dl className="flex flex-wrap items-center gap-2.5 text-xs font-semibold">
      {totals.map(({ label, value, color }) => <div key={label} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
        <dt className="order-2 text-slate-600">{label}</dt>
        <dd className={`${color} order-1 font-mono text-sm font-bold`}>{value != null ? <AnimatedNumber value={value} /> : error ? "Unavailable" : "…"}</dd>
      </div>)}
    </dl>
    <p className="mt-2 text-[10px] text-slate-500">{error ? <>{data ? "Showing last available totals." : "Live totals could not be loaded."} <button type="button" onClick={retry} className="underline">Retry totals</button></> : "Refreshes every minute · Comps are price records, not completed sales"}</p>
  </section>;
}
