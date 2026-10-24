"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { AddToBinderButton } from "@/components/binder/add-to-binder-button";
import { ShopOnEbayButton } from "@/components/shop-ebay-button";
import { useCurrency } from "@/context/currency-context";
import type { CardDetail } from "@/types/card";

/**
 * Wraps the card hero's action row. On phones, once that row scrolls above the viewport a
 * bottom bar keeps the price and the same actions in reach.
 */
export function StickyCardActions({ card, children }: { card: CardDetail; children: ReactNode }) {
  const { formatPrice } = useCurrency();
  const anchor = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = anchor.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => {
      setVisible(!entry.isIntersecting && entry.boundingClientRect.top < 0);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return <>
    <div ref={anchor}>{children}</div>
    <div data-testid="sticky-card-actions" inert={!visible}
      className={`fixed inset-x-0 bottom-0 z-40 border-t border-stone-200 bg-white/95 px-4 pt-2.5 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur transition-transform duration-200 md:hidden ${visible ? "translate-y-0" : "pointer-events-none translate-y-full"}`}
      style={{ paddingBottom: "max(0.625rem, env(safe-area-inset-bottom))" }}>
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-slate-950">{card.name}</p>
          <p className="font-mono text-sm font-black text-slate-950">{formatPrice(card.market_price, { showPending: true })}</p>
        </div>
        <ShopOnEbayButton card={card} variant="compact" />
        <AddToBinderButton cardId={card.id} cardName={card.name} variant="compact" />
      </div>
    </div>
  </>;
}
