"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { adminRequest } from "@/lib/admin-api";
import type { CatalogHealth as Health } from "@/types/market-data";

export function CatalogHealth() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setData(null); setError("");
    adminRequest<Health>("/catalog-health", { signal: controller.signal }).then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((err) => { if (!controller.signal.aborted) { console.error("Catalog health failed:", err); setError("Catalog health is unavailable. Your session may have expired."); } });
    return () => controller.abort();
  }, [open, retry]);
  return <section className="rounded-2xl border border-slate-200 bg-white p-5">
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="text-lg font-semibold text-slate-900">Catalog coverage & new sets {open ? "−" : "+"}</button>
    {open && <div className="mt-4 space-y-5">
      {error ? <p role="alert" className="text-sm text-rose-700">{error} <button onClick={() => setRetry((n) => n + 1)} className="underline">Retry</button></p> : !data ? <p role="status">Loading catalog coverage…</p> : !data.games.length ? <p className="text-sm text-slate-600">No provider catalog snapshot has been synced yet.</p> : data.games.map((game) => <div key={game.game} className="rounded-xl bg-slate-50 p-4">
        <h3 className="font-semibold">{game.game}</h3><p className="mt-1 text-sm text-slate-600">{game.local_set_count} / {game.discovered_set_count} discovered sets present locally · {game.local_card_count.toLocaleString()} local products / {game.provider_card_count?.toLocaleString() ?? "unknown"} reported by provider</p>
        <p className="mt-1 text-xs text-slate-500">Snapshot fetched {game.fetched_at.slice(0, 10)} · Provider synced {game.provider_synced_at?.slice(0, 10) ?? "unknown"}. Counts may differ because of variants and ingestion scope.</p>
        <h4 className="mt-4 text-sm font-semibold">Latest releases</h4><ul className="mt-2 space-y-2 text-sm">{game.latest_sets.map((set) => <li key={set.id} className="flex flex-wrap justify-between gap-2">{set.present_locally ? <Link href={`/catalog?set=${encodeURIComponent(set.id)}`} className="text-emerald-800 underline">{set.name}</Link> : <span>{set.name} · Not yet imported</span>}<span className="text-xs text-slate-500">{set.release_date?.slice(0, 10) ?? "Date unknown"} · {set.local_card_count}/{set.provider_card_count ?? "?"} products</span></li>)}</ul>
        <details className="mt-4 text-sm"><summary className="cursor-pointer">Missing sets ({game.discovered_set_count - game.local_set_count}; newest 30 shown)</summary><ul className="mt-2 space-y-1">{game.missing_sets.map((set) => <li key={set.id}>{set.name} · {set.release_date?.slice(0, 10) ?? "Date unknown"}</li>)}</ul></details>
      </div>)}
    </div>}
  </section>;
}
