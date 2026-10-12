"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "@/components/card-image";
import { cardImageUrl } from "@/lib/api";
import { clearRecentCards, readRecentCards, rememberCard, RECENT_EVENT, RECENT_KEY } from "@/lib/recently-viewed";
import type { RecentCard } from "@/lib/recently-viewed";
import type { CardSummary } from "@/types/card";

export function RememberViewedCard({ card }: { card: Pick<CardSummary, "id" | "name" | "set_name" | "image_url"> }) {
  const { id, name, set_name, image_url } = card;
  useEffect(() => { rememberCard({ id, name, set_name, image_url }); }, [id, name, set_name, image_url]);
  return null;
}

export function RecentlyViewed() {
  const [cards, setCards] = useState<RecentCard[]>([]);
  const [error, setError] = useState(false);
  useEffect(() => {
    const refresh = () => setCards(readRecentCards());
    const storage = (event: StorageEvent) => { if (event.key === RECENT_KEY || event.key === null) refresh(); };
    refresh();
    window.addEventListener(RECENT_EVENT, refresh);
    window.addEventListener("storage", storage);
    window.addEventListener("pageshow", refresh);
    return () => {
      window.removeEventListener(RECENT_EVENT, refresh);
      window.removeEventListener("storage", storage);
      window.removeEventListener("pageshow", refresh);
    };
  }, []);
  if (!cards.length) return null;
  return <section aria-labelledby="recent-heading" className="py-10">
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Pick up where you left off</p><h2 id="recent-heading" className="mt-1 text-xl font-bold tracking-tight">Recently viewed</h2><p className="mt-1 text-xs text-slate-500">Views from the last 30 days · This browser only.</p></div>
      <button type="button" onClick={() => setError(!clearRecentCards())} className="min-h-10 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:bg-slate-50">Clear history</button>
    </div>
    {error && <p role="alert" className="mb-3 text-xs text-rose-700">Could not clear history. Browser storage may be restricted.</p>}
    <div className="flex snap-x gap-3 overflow-x-auto pb-3" aria-label="Recently viewed cards">
      {cards.map((card) => <Link key={card.id} href={`/cards/${encodeURIComponent(card.id)}`} prefetch={false} className="flex w-56 shrink-0 snap-start items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-emerald-400 focus-visible:outline-emerald-600">
        <Image src={cardImageUrl(card.image_url)} alt="" width={40} height={56} className="h-14 w-10 shrink-0 object-contain" />
        <div className="min-w-0"><h3 className="line-clamp-2 text-xs font-bold text-slate-900">{card.name}</h3><p className="mt-1 truncate text-[10px] text-slate-500">{card.set_name}</p></div>
      </Link>)}
    </div>
  </section>;
}
