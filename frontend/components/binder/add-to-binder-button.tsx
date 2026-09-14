"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useBinder } from "@/context/binder-context";

interface AddToBinderButtonProps {
  cardId: string;
  cardName: string;
  variant?: "hero" | "compact";
}

export function AddToBinderButton({
  cardId,
  cardName,
  variant = "hero",
}: AddToBinderButtonProps) {
  const { isCardInBinder, findCardSlot, quickAddCard, removeCardFromSlot, isHydrated } =
    useBinder();
  const [justAdded, setJustAdded] = useState(false);

  if (!isHydrated) {
    return (
      <button
        type="button"
        disabled
        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 font-mono text-xs font-bold text-slate-400 opacity-60"
      >
        <span>＋ Add to Binder</span>
      </button>
    );
  }

  const inBinder = isCardInBinder(cardId);
  const slotInfo = inBinder ? findCardSlot(cardId) : null;

  const handleToggle = (e: React.MouseEvent) => {
    e.preventDefault();
    if (inBinder && slotInfo) {
      removeCardFromSlot(slotInfo.pageIndex, slotInfo.slotIndex);
      setJustAdded(false);
    } else {
      quickAddCard(cardId);
      setJustAdded(true);
      setTimeout(() => setJustAdded(false), 2500);
    }
  };

  if (inBinder && slotInfo) {
    return (
      <div className="inline-flex items-center gap-1.5">
        <Link
          href="/binder"
          prefetch={false}
          className="group inline-flex items-center gap-2 rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2.5 font-mono text-xs font-bold text-emerald-900 shadow-xs hover:bg-emerald-100 transition"
          title={`Card is in Page ${slotInfo.pageIndex + 1}, Slot ${slotInfo.slotIndex + 1}. Click to open binder.`}
        >
          <svg className="h-4 w-4 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <span>
            In Binder • P.{slotInfo.pageIndex + 1}, Slot #{slotInfo.slotIndex + 1}
          </span>
          <span className="text-emerald-600 group-hover:translate-x-0.5 transition-transform">→</span>
        </Link>
        <button
          type="button"
          onClick={handleToggle}
          className="rounded-xl border border-slate-200 bg-white p-2 text-slate-400 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-600 transition shadow-2xs"
          title="Remove from binder"
          aria-label="Remove card from binder"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={handleToggle}
      className={`inline-flex items-center gap-2 rounded-xl border font-mono text-xs font-bold transition shadow-xs ${
        variant === "hero"
          ? "border-slate-300 bg-white px-4 py-2.5 text-slate-800 hover:border-slate-900 hover:bg-slate-900 hover:text-white"
          : "border-slate-200 bg-slate-50 px-3 py-1.5 text-slate-700 hover:bg-slate-100"
      }`}
      title={`Add ${cardName} to next open slot in binder`}
    >
      <svg
        className="h-4 w-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
        <path d="M6 2v20" strokeDasharray="1 2" />
        <path d="M10 7h7" />
        <path d="M10 12h7" />
        <path d="M10 17h7" />
      </svg>
      <span>{justAdded ? "Added to Binder!" : "＋ Add to Binder"}</span>
    </button>
  );
}
