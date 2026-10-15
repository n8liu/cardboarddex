"use client";

import { useEffect, useState } from "react";
import Image from "@/components/card-image";
import { HoloCard } from "@/components/ui/holo-card";
import { cardImageUrl, getTrendingDashboard } from "@/lib/api";
import type { TrendingCardItem } from "@/types/card";

export function HomeTrendingCard() {
  const [card, setCard] = useState<TrendingCardItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setFailed(false);
    getTrendingDashboard({ abortSignal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return;
      const cards = result.trending_cards.slice(0, 50);
      setCard(cards.length ? cards[Math.floor(Math.random() * cards.length)] : null);
    }).catch((error) => {
      if (!controller.signal.aborted) { console.error("Homepage trending card failed:", error); setFailed(true); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt]);

  return <aside aria-label="Featured trending card" className="mx-auto flex w-full max-w-[280px] items-center justify-center sm:max-w-[340px] lg:max-w-[420px] lg:-translate-x-20">
    {card ? <HoloCard maxTilt={8} rarity={card.rarity} className="w-full rounded-xl"><Image src={cardImageUrl(card.image_url)} alt={card.name} width={420} height={588} sizes="(min-width: 1024px) 420px, (min-width: 640px) 340px, (max-width: 311px) calc(100vw - 32px), 280px" className="h-auto w-full object-contain drop-shadow-2xl" /></HoloCard>
      : loading ? <div role="status" aria-label="Loading trending card artwork" className="aspect-[5/7] w-full rounded-xl bg-slate-100 motion-safe:animate-pulse" />
      : failed ? <button type="button" onClick={() => setAttempt((n) => n + 1)} className="text-xs text-slate-500 underline">Retry artwork</button> : null}
  </aside>;
}
