"use client";

import Image from "@/components/card-image";
import Link from "next/link";
import { useState } from "react";

import { useCurrency } from "@/context/currency-context";
import { cardImageUrl } from "@/lib/api";
import { shimmerBlurDataUrl } from "@/lib/shimmer";
import type { CardSummary } from "@/types/card";

type CardTableViewProps = {
  cards: CardSummary[];
  query?: string;
};

function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Pending";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "Pending";
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
    return "Pending";
  }
}

function TableRowThumbnail({ card }: { card: CardSummary }) {
  const [failed, setFailed] = useState(false);

  return (
    <div className="relative h-11 w-8 shrink-0 overflow-hidden rounded border border-slate-100 bg-slate-50">
      {failed ? (
        <div className="flex h-full w-full items-center justify-center bg-slate-100 text-[10px] font-bold text-slate-400">
          {card.name.slice(0, 1).toUpperCase()}
        </div>
      ) : (
        <Image
          alt={card.name}
          className="object-contain"
          fill
          onError={() => setFailed(true)}
          placeholder="blur"
          blurDataURL={shimmerBlurDataUrl(80, 110)}
          sizes="40px"
          src={cardImageUrl(card.image_url)}
        />
      )}
    </div>
  );
}

export function CardTableView({ cards, query }: CardTableViewProps) {
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
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-2xs">
      <table className="w-full text-left font-mono text-xs">
        <thead className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
          <tr>
            <th className="py-3 pl-4 pr-2 w-10">#</th>
            <th className="py-3 px-3">Card</th>
            <th className="hidden sm:table-cell py-3 px-3">Set</th>
            <th className="hidden md:table-cell py-3 px-3">Rarity</th>
            <th className="py-3 px-3 text-right">TCG Market</th>
            <th className="hidden lg:table-cell py-3 px-3 text-right">Updated</th>
            <th className="py-3 pr-4 pl-2 text-right w-16">Comps</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {cards.map((card, idx) => (
            <tr
              key={card.id}
              className="table-row-cv animate-card-cascade group transition hover:bg-slate-50/80 focus-within:bg-slate-50"
              style={{ animationDelay: `${Math.min(idx * 20, 300)}ms` }}
            >
              <td className="py-2.5 pl-4 pr-2 text-slate-400 font-medium">
                {card.number ? `#${card.number}` : idx + 1}
              </td>
              <td className="py-2.5 px-3">
                <Link
                  href={`/cards/${encodeURIComponent(card.id)}`}
                  prefetch={false}
                  className="flex items-center gap-2.5 focus:outline-none"
                >
                  <TableRowThumbnail card={card} />
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950 group-hover:text-emerald-700 transition truncate max-w-[200px] sm:max-w-xs md:max-w-sm">
                      {card.name}
                    </p>
                    <p className="sm:hidden text-[10px] text-slate-400 truncate max-w-[180px]">
                      {card.set_name} {card.rarity ? `· ${card.rarity}` : ""}
                    </p>
                  </div>
                </Link>
              </td>
              <td className="hidden sm:table-cell py-2.5 px-3 text-slate-600 truncate max-w-[180px]">
                {card.set_name}
              </td>
              <td className="hidden md:table-cell py-2.5 px-3">
                <span className="inline-block rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                  {card.rarity || "Standard"}
                </span>
              </td>
              <td className="py-2.5 px-3 text-right font-black tracking-tight text-slate-950 sm:text-sm">
                {formatPrice(card.market_price, { showPending: true })}
              </td>
              <td className="hidden lg:table-cell py-2.5 px-3 text-right text-[11px] text-slate-400">
                {formatRelativeTime(card.last_updated_at)}
              </td>
              <td className="py-2.5 pr-4 pl-2 text-right">
                <Link
                  href={`/cards/${encodeURIComponent(card.id)}`}
                  prefetch={false}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200 text-xs font-bold text-slate-400 transition group-hover:border-emerald-600 group-hover:bg-emerald-600 group-hover:text-white"
                  aria-label={`View comps for ${card.name}`}
                >
                  →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
