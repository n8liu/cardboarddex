"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getHomeStats } from "@/lib/api";
import type { HomeStats } from "@/types/home";
import { AnimatedNumber } from "@/components/ui/animated-number";

export function HomeLiveStats() {
  const [data, setData] = useState<HomeStats | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    async function refresh() {
      if (document.hidden || controller) return;
      const request = new AbortController();
      controller = request;
      try {
        const result = await getHomeStats(request.signal);
        if (!disposed && !request.signal.aborted) { setData(result); setError(false); }
      } catch (err) {
        if (!disposed && !request.signal.aborted) { console.error("Homepage totals failed:", err); setError(true); }
      } finally {
        if (controller === request) controller = null;
      }
    }
    function visibility() {
      if (document.hidden) { controller?.abort(); controller = null; }
      else void refresh();
    }
    void refresh();
    const timer = window.setInterval(refresh, 60_000);
    document.addEventListener("visibilitychange", visibility);
    return () => { disposed = true; controller?.abort(); clearInterval(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [attempt]);
  return <section aria-label="Collection totals" className="mt-5">
    <dl className="grid gap-4 sm:grid-cols-3">
      {([["Catalog products", data?.products], ["Sets", data?.sets], ["Live comps", data?.price_observations]] as const).map(([label, value]) => <div key={label} className="rounded-xl border border-slate-200 bg-white/60 p-4">
        <dt className="text-[10px] uppercase tracking-wider text-slate-500">{label === "Live comps" ? <Link href="/live-updates" className="hover:underline">{label}</Link> : label}</dt>
        <dd className="mt-2 text-lg font-bold tabular-nums sm:text-2xl">{value != null ? <AnimatedNumber value={value} /> : error ? "Unavailable" : "…"}</dd>
      </div>)}
    </dl>
    <p className="mt-3 text-[10px] text-slate-500">{error ? <>{data ? "Showing last available totals." : "Totals could not be loaded."} <button type="button" onClick={() => setAttempt((n) => n + 1)} className="underline">Retry totals</button></> : "Refreshes every minute · Price records, not completed sales"}</p>
  </section>;
}
