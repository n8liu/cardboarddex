"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { HoloCard } from "@/components/ui/holo-card";
import { useCurrency } from "@/context/currency-context";
import { cardImageUrl } from "@/lib/api";
import { shimmerBlurDataUrl } from "@/lib/shimmer";
import type { CardSummary } from "@/types/card";

type CardGridProps = {
  cards: CardSummary[];
  query: string;
};

function numberLabel(card: CardSummary): string {
  return card.printed_total ? `${card.number}/${card.printed_total}` : card.number;
}

function formatRelativeTime(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return null;
    const diffMs = Date.now() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 30) return `${diffDays}d ago`;
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(d);
  } catch {
    return null;
  }
}

function CardThumbnail({ card }: { card: CardSummary }) {
  const [failed, setFailed] = useState(false);
  const updatedLabel = formatRelativeTime(card.last_updated_at);

  return (
    <div className="relative aspect-[5/7] w-full overflow-hidden rounded-xl bg-slate-50">
      {updatedLabel && (
        <span
          className="absolute right-2 top-2 z-10 rounded-md border border-slate-200/80 bg-white/90 px-1.5 py-0.5 text-[9px] font-semibold text-slate-500 shadow-sm backdrop-blur-sm"
          title={`Last updated: ${card.last_updated_at}`}
        >
          {updatedLabel}
        </span>
      )}
      {failed ? (
        <div
          aria-label={`${card.name} image unavailable`}
          className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 text-center"
          role="img"
        >
          <span className="flex h-12 w-12 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-sm font-black text-emerald-700">
            {card.name.slice(0, 1).toUpperCase()}
          </span>
          <span className="mt-3 px-1 text-[9px] font-semibold uppercase tracking-wide text-slate-400">Image pending</span>
        </div>
      ) : (
        <Image
          alt={`${card.name} from ${card.set_name}`}
          className="object-contain p-3 transition duration-300 group-hover:scale-[1.02]"
          fill
          onError={() => setFailed(true)}
          placeholder="blur"
          blurDataURL={shimmerBlurDataUrl(250, 350)}
          quality={75}
          sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, (max-width: 1536px) 25vw, 220px"
          src={cardImageUrl(card.image_url)}
        />
      )}
    </div>
  );
}

export function CardGrid({ cards, query }: CardGridProps) {
  const { formatPrice } = useCurrency();

  if (cards.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <p className="text-sm font-semibold text-slate-900">No cards found</p>
        <p className="mt-1 text-sm text-slate-500">
          {query ? "Try a different card or set name." : "Run a catalog sync to add cards."}
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
      {cards.map((card, idx) => (
        <Link
          className="card-cv animate-card-cascade group flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-3 transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-[0_16px_40px_rgba(15,23,42,0.08)] focus:outline-none focus:ring-2 focus:ring-emerald-500"
          style={{ animationDelay: `${Math.min(idx * 25, 350)}ms` }}
          href={`/cards/${encodeURIComponent(card.id)}`}
          key={card.id}
          prefetch={false}
        >
          <HoloCard maxTilt={8} rarity={card.rarity} className="w-full">
            <CardThumbnail card={card} />
          </HoloCard>

          <div className="flex min-w-0 flex-1 flex-col px-1 pb-1 pt-4">
            <h2 className="line-clamp-2 text-sm font-bold leading-5 text-slate-950 sm:text-base">{card.name}</h2>
            <p className="mt-1 truncate text-xs text-slate-500 sm:text-sm">{card.set_name}</p>
            <p className="mt-1 truncate text-xs text-slate-400">{card.rarity || "None"} · {numberLabel(card)}</p>

            <div className="mt-auto flex items-end justify-between gap-3 pt-5">
              <div className="min-w-0">
                <p className={`truncate text-base font-bold sm:text-lg ${card.market_price === null ? "text-slate-400" : "text-slate-950"}`}>
                  {formatPrice(card.market_price, { showPending: true })}
                </p>
                <p className="mt-0.5 truncate text-[10px] text-slate-400">TCG market value</p>
              </div>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-slate-200 text-base text-slate-400 transition group-hover:border-emerald-600 group-hover:bg-emerald-600 group-hover:text-white" aria-label="View card details">
                →
              </span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
