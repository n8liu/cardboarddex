"use client";

import React, { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useCurrency } from "@/context/currency-context";
import { cardImageUrl, searchCards } from "@/lib/api";
import { shimmerBlurDataUrl } from "@/lib/shimmer";
import type { CardSummary, GameLanguage } from "@/types/card";

interface CardPickerModalProps {
  isOpen: boolean;
  pageIndex: number;
  slotIndex: number;
  onClose: () => void;
  onSelectCard: (cardId: string) => void;
}

const QUICK_CHIPS = [
  { label: "All", q: "" },
  { label: "Charizard", q: "Charizard" },
  { label: "Pikachu", q: "Pikachu" },
  { label: "Gengar", q: "Gengar" },
  { label: "Umbreon", q: "Umbreon" },
  { label: "Mewtwo", q: "Mewtwo" },
  { label: "151", q: "151" },
  { label: "Grails ($100+)", q: "", minPrice: 100 },
  { label: "Under $20", q: "", maxPrice: 20 },
];

export function CardPickerModal({
  isOpen,
  pageIndex,
  slotIndex,
  onClose,
  onSelectCard,
}: CardPickerModalProps) {
  const { formatPrice } = useCurrency();
  const [query, setQuery] = useState("");
  const [activeChip, setActiveChip] = useState("All");
  const [game, setGame] = useState<GameLanguage>("all");
  const [cards, setCards] = useState<CardSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [minPrice, setMinPrice] = useState<number | null>(null);
  const [maxPrice, setMaxPrice] = useState<number | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Handle ESC to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Debounced search
  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    setLoading(true);

    const timer = setTimeout(async () => {
      try {
        const results = await searchCards(query, {
          limit: 30,
          game,
          minPrice,
          maxPrice,
          sortBy: "price_desc",
        });
        if (!cancelled) {
          setCards(results);
        }
      } catch (err) {
        console.error("[CardPickerModal] Search error:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 220);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [isOpen, query, game, minPrice, maxPrice]);

  if (!isOpen) return null;

  const handleChipClick = (chip: (typeof QUICK_CHIPS)[0]) => {
    setActiveChip(chip.label);
    setQuery(chip.q);
    setMinPrice(chip.minPrice ?? null);
    setMaxPrice(chip.maxPrice ?? null);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-900/60 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="relative flex flex-col h-full max-h-[85vh] w-full max-w-4xl rounded-2xl border border-slate-200 bg-white shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 bg-slate-50/80">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 font-mono text-xs font-bold">
                +{slotIndex + 1}
              </span>
              <h2 className="font-mono text-sm sm:text-base font-bold text-slate-950 tracking-tight">
                Insert Card into Page {pageIndex + 1} • Slot #{String(slotIndex + 1).padStart(2, "0")}
              </h2>
            </div>
            <p className="mt-0.5 font-mono text-xs text-slate-500">
              Search the 54,680+ catalog by name, set, or character to assign this pocket.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-400 hover:border-slate-300 hover:text-slate-900 transition shadow-2xs"
            aria-label="Close dialog"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        {/* Search & Filter Bar */}
        <div className="border-b border-slate-100 bg-white p-4 space-y-3">
          <div className="relative">
            <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm">
              ⌕
            </span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search card name, set, or Pokémon species..."
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-10 font-mono text-xs sm:text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-emerald-500 focus:bg-white focus:ring-1 focus:ring-emerald-500 transition"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            )}
          </div>

          {/* Filter Chips & Language Switcher */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {QUICK_CHIPS.map((chip) => {
                const isActive = activeChip === chip.label;
                return (
                  <button
                    key={chip.label}
                    type="button"
                    onClick={() => handleChipClick(chip)}
                    className={`rounded-lg px-2.5 py-1 font-mono text-[11px] font-semibold transition ${
                      isActive
                        ? "bg-slate-900 text-white shadow-xs"
                        : "border border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-slate-100"
                    }`}
                  >
                    {chip.label}
                  </button>
                );
              })}
            </div>

            {/* Language Toggle */}
            <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5 font-mono text-[10px]">
              {(["all", "pokemon", "pokemon-japan"] as const).map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => setGame(lang)}
                  className={`rounded px-2 py-0.5 font-bold uppercase transition ${
                    game === lang
                      ? "bg-white text-slate-950 shadow-2xs"
                      : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {lang === "all" ? "All" : lang === "pokemon" ? "EN" : "JP"}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Results Grid */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 bg-slate-50/40 scrollbar-thin">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="h-7 w-7 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
              <p className="mt-3 font-mono text-xs text-slate-500">Searching card database...</p>
            </div>
          ) : cards.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
                ⌕
              </div>
              <p className="mt-3 font-mono text-sm font-semibold text-slate-800">No cards found</p>
              <p className="mt-1 font-mono text-xs text-slate-500">
                Try searching for a different Pokémon name, card number, or expansion set.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {cards.map((card) => (
                <button
                  key={card.id}
                  type="button"
                  onClick={() => {
                    onSelectCard(card.id);
                    onClose();
                  }}
                  className="group relative flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white p-2.5 text-left transition-all duration-200 hover:border-emerald-500 hover:shadow-md hover:scale-[1.02]"
                >
                  {/* Card Thumbnail */}
                  <div className="relative aspect-[5/7] w-full overflow-hidden rounded-lg bg-slate-50 mb-2">
                    <Image
                      alt={card.name}
                      src={cardImageUrl(card.image_url)}
                      fill
                      className="object-contain p-1 transition duration-200 group-hover:scale-105"
                      placeholder="blur"
                      blurDataURL={shimmerBlurDataUrl(160, 220)}
                      sizes="(max-width: 640px) 45vw, 160px"
                    />
                  </div>

                  {/* Card Info */}
                  <div className="flex-1 min-w-0">
                    <p className="truncate font-mono text-xs font-bold text-slate-900 group-hover:text-emerald-700 transition-colors">
                      {card.name}
                    </p>
                    <p className="truncate font-mono text-[10px] text-slate-500">
                      {card.set_name} • #{card.number}
                    </p>
                  </div>

                  {/* Price Tag & Action */}
                  <div className="mt-2 flex items-center justify-between pt-1.5 border-t border-slate-100">
                    <span className="font-mono text-xs font-bold text-slate-950">
                      {formatPrice(card.market_price)}
                    </span>
                    <span className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-[9px] font-bold text-white group-hover:bg-emerald-600 transition-colors shadow-2xs">
                      Select
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
