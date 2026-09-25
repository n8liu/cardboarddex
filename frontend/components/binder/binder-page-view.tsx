"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Image from "@/components/card-image";
import Link from "next/link";
import { useBinder } from "@/context/binder-context";
import { useCurrency } from "@/context/currency-context";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { cardImageUrl } from "@/lib/api";
import { fetchPortfolioDataWithFallback } from "@/lib/portfolio";
import type { PortfolioCardItem, PortfolioValuationResponse } from "@/types/binder";
import { BinderSleeveSlot } from "./binder-sleeve-slot";
import { CardPickerModal } from "./card-picker-modal";
import { PortfolioValueChart } from "./portfolio-value-chart";

export function BinderPageView() {
  const {
    binder,
    activePageIndex,
    setActivePageIndex,
    addCardToSlot,
    removeCardFromSlot,
    moveCard,
    addPage,
    removePage,
    setBinderName,
    clearBinder,
    allCardIds,
    totalCardCount,
    isHydrated,
  } = useBinder();

  const { formatPrice, convertPrice, currency } = useCurrency();

  // Valuation state
  const [valuation, setValuation] = useState<PortfolioValuationResponse | null>(null);
  const [loadingValuation, setLoadingValuation] = useState(false);

  // Card picker modal state
  const [pickerTarget, setPickerTarget] = useState<{
    pageIndex: number;
    slotIndex: number;
  } | null>(null);

  // View options
  const [viewMode, setViewMode] = useState<"single" | "spread">("spread");
  const [showChart, setShowChart] = useState(true);

  // Name edit state
  const [isEditingName, setIsEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  // Fetch / update portfolio valuation whenever cards change
  useEffect(() => {
    if (!isHydrated) return;

    let cancelled = false;
    setLoadingValuation(true);

    fetchPortfolioDataWithFallback(allCardIds, 365)
      .then((data) => {
        if (!cancelled) {
          setValuation(data);
        }
      })
      .catch((err) => {
        console.error("[BinderPageView] Valuation fetch error:", err);
      })
      .finally(() => {
        if (!cancelled) setLoadingValuation(false);
      });

    return () => {
      cancelled = true;
    };
  }, [allCardIds, isHydrated]);

  // Card map by card ID for O(1) slot hydration
  const cardMap = useMemo(() => {
    const map = new Map<string, PortfolioCardItem>();
    if (valuation?.cards) {
      for (const card of valuation.cards) {
        map.set(card.id, card);
      }
    }
    return map;
  }, [valuation]);

  // Keyboard page navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || "").toLowerCase();
      if (activeTag === "input" || activeTag === "textarea" || activeTag === "select") {
        return;
      }

      if (e.key === "ArrowLeft" || e.key === "[") {
        if (activePageIndex > 0) {
          setActivePageIndex(activePageIndex - 1);
        }
      } else if (e.key === "ArrowRight" || e.key === "]") {
        if (activePageIndex < binder.pages.length - 1) {
          setActivePageIndex(activePageIndex + 1);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activePageIndex, binder.pages.length, setActivePageIndex]);

  // Current page cards
  const currentPage = binder.pages[activePageIndex] || binder.pages[0];
  const totalCapacity = binder.pages.length * 9;
  const fillPct = totalCapacity > 0 ? Math.round((totalCardCount / totalCapacity) * 100) : 0;

  // Spread mode right page (if applicable)
  const isSpreadPossible = activePageIndex % 2 === 0;
  const spreadLeftIdx = isSpreadPossible ? activePageIndex : activePageIndex - 1;
  const spreadRightIdx = spreadLeftIdx + 1;
  const leftPage = binder.pages[spreadLeftIdx] || binder.pages[0];
  const rightPage = binder.pages[spreadRightIdx] || null;

  const handleStartEditName = () => {
    setNameDraft(binder.name);
    setIsEditingName(true);
  };

  const handleSaveName = () => {
    if (nameDraft.trim()) {
      setBinderName(nameDraft.trim());
    }
    setIsEditingName(false);
  };

  return (
    <div className="mx-auto max-w-[1600px] px-3 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* 1. Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-2.5 py-0.5 font-mono text-[10px] font-bold text-emerald-800">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              LOCALSTORAGE PORTFOLIO BINDER
            </span>
            <span className="hidden sm:inline font-mono text-xs text-slate-400">
              Only Card IDs Stored Locally
            </span>
          </div>

          {/* Binder Title (Editable) */}
          <div className="mt-2 flex items-center gap-3">
            {isEditingName ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveName();
                    if (e.key === "Escape") setIsEditingName(false);
                  }}
                  autoFocus
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-mono text-xl sm:text-2xl font-bold text-slate-900 shadow-inner outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                />
                <button
                  type="button"
                  onClick={handleSaveName}
                  className="rounded-lg bg-slate-900 px-3 py-1.5 font-mono text-xs font-bold text-white hover:bg-slate-800 transition"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => setIsEditingName(false)}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 font-mono text-xs font-bold text-slate-600 hover:bg-slate-100 transition"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2.5">
                <h1 className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-slate-950">
                  {binder.name}
                </h1>
                <button
                  type="button"
                  onClick={handleStartEditName}
                  className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition"
                  title="Rename binder"
                  aria-label="Rename binder"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                    <path d="m15 5 4 4" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Chart Toggle */}
          <button
            type="button"
            onClick={() => setShowChart(!showChart)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 font-mono text-xs font-bold transition ${
              showChart
                ? "border-emerald-500 bg-emerald-50 text-emerald-900"
                : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3v18h18M18 9l-5 5-4-4-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>{showChart ? "Hide Chart" : "Valuation Chart"}</span>
          </button>

          {/* View Mode Toggle (Desktop only) */}
          <div className="hidden lg:flex items-center rounded-lg border border-slate-300 bg-white p-0.5 font-mono text-xs">
            <button
              type="button"
              onClick={() => setViewMode("spread")}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 font-bold transition ${
                viewMode === "spread"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-950"
              }`}
            >
              <span>2-Page Spread</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("single")}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 font-bold transition ${
                viewMode === "single"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-950"
              }`}
            >
              <span>Single Page</span>
            </button>
          </div>

          {/* Add Page Button */}
          <button
            type="button"
            onClick={addPage}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 font-mono text-xs font-bold text-white hover:bg-emerald-700 transition shadow-xs"
          >
            <span>+ Add Page</span>
          </button>
        </div>
      </div>

      {/* 2. Telemetry KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        {/* Total Binder Value */}
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <span className="font-mono text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Total Binder Value
          </span>
          <div className="mt-1 font-mono text-2xl sm:text-3xl font-bold tracking-tight text-slate-950 flex items-baseline gap-1">
            <span>{formatPrice(valuation?.total_current_value ?? 0)}</span>
          </div>
          <p className="mt-1 font-mono text-[10px] text-slate-400">
            Real-time market valuation
          </p>
        </div>

        {/* Trending Deltas */}
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <span className="font-mono text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            7-Day Movement
          </span>
          <div className="mt-1 flex items-baseline gap-2">
            {valuation?.delta_7d_amount !== null && valuation?.delta_7d_amount !== undefined ? (
              <span
                className={`font-mono text-2xl sm:text-3xl font-bold tracking-tight ${
                  valuation.delta_7d_amount >= 0 ? "text-emerald-600" : "text-rose-600"
                }`}
              >
                {valuation.delta_7d_amount >= 0 ? "+" : ""}
                {formatPrice(valuation.delta_7d_amount)}
              </span>
            ) : (
              <span className="font-mono text-2xl sm:text-3xl font-bold text-slate-400">—</span>
            )}
          </div>
          <p className="mt-1 font-mono text-[10px] text-slate-400">
            {valuation?.delta_7d_percent !== null && valuation?.delta_7d_percent !== undefined
              ? `${valuation.delta_7d_percent >= 0 ? "▲ +" : "▼ "}${valuation.delta_7d_percent.toFixed(1)}% vs last week`
              : "Historical change"}
          </p>
        </div>

        {/* Capacity / Filled Slots */}
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <span className="font-mono text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Binder Capacity
          </span>
          <div className="mt-1 font-mono text-2xl sm:text-3xl font-bold tracking-tight text-slate-950">
            {totalCardCount}{" "}
            <span className="text-base text-slate-400 font-normal">/ {totalCapacity}</span>
          </div>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${Math.min(100, fillPct)}%` }}
            />
          </div>
        </div>

        {/* Crown Jewel (Grail) */}
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <span className="font-mono text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Crown Jewel Card
          </span>
          {valuation?.highest_value_card ? (
            <div className="mt-1 flex items-center gap-2.5">
              <div className="relative h-10 w-7 flex-shrink-0 overflow-hidden rounded border border-slate-200 bg-slate-100">
                <Image
                  alt={valuation.highest_value_card.name}
                  src={cardImageUrl(valuation.highest_value_card.image_url)}
                  fill
                  className="object-contain"
                  sizes="30px"
                />
              </div>
              <div className="min-w-0">
                <p className="truncate font-mono text-xs font-bold text-slate-900">
                  {valuation.highest_value_card.name}
                </p>
                <p className="font-mono text-xs font-bold text-emerald-600">
                  {formatPrice(valuation.highest_value_card.market_price)}
                </p>
              </div>
            </div>
          ) : (
            <p className="mt-2 font-mono text-xs text-slate-400">No cards in binder</p>
          )}
        </div>
      </div>

      {/* 3. Portfolio Valuation Trend Chart (Collapsible) */}
      {showChart && (
        <PortfolioValueChart
          history={valuation?.history || []}
          currentValue={valuation?.total_current_value || 0}
        />
      )}

      {/* 4. The Pokémon Card Binder (The Physical Showcase) */}
      <div className="relative rounded-3xl p-4 sm:p-8 lg:p-10 binder-leather-cover">
        {/* Reinforced Metallic Corner Caps */}
        <div className="pointer-events-none absolute top-3 left-3 h-8 w-8 rounded-tl-xl border-t-2 border-l-2 border-slate-300/80 shadow-2xs" />
        <div className="pointer-events-none absolute top-3 right-3 h-8 w-8 rounded-tr-xl border-t-2 border-r-2 border-slate-300/80 shadow-2xs" />
        <div className="pointer-events-none absolute bottom-3 left-3 h-8 w-8 rounded-bl-xl border-b-2 border-l-2 border-slate-300/80 shadow-2xs" />
        <div className="pointer-events-none absolute bottom-3 right-3 h-8 w-8 rounded-br-xl border-b-2 border-r-2 border-slate-300/80 shadow-2xs" />

        {/* Binder Header Navigation Strip */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-200">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm font-bold text-slate-900 tracking-wide">
              {viewMode === "spread" && rightPage
                ? `Pages ${spreadLeftIdx + 1} & ${spreadRightIdx + 1} of ${binder.pages.length}`
                : `Page ${activePageIndex + 1} of ${binder.pages.length}`}
            </span>
            <span className="rounded bg-slate-100 border border-slate-200 px-2 py-0.5 font-mono text-[11px] text-slate-600">
              9 Pockets / Page
            </span>
          </div>

          {/* Page Selector Tabs */}
          <div className="flex flex-wrap items-center gap-1.5">
            {binder.pages.map((p, idx) => {
              const isActive =
                viewMode === "spread"
                  ? idx === spreadLeftIdx || idx === spreadRightIdx
                  : idx === activePageIndex;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setActivePageIndex(idx)}
                  className={`rounded-lg px-2.5 py-1 font-mono text-xs font-bold transition ${
                    isActive
                      ? "bg-slate-900 text-white shadow-xs"
                      : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:text-slate-950"
                  }`}
                >
                  P.{idx + 1}
                </button>
              );
            })}
            <button
              type="button"
              onClick={addPage}
              className="rounded-lg border border-dashed border-slate-300 bg-white px-2 py-1 font-mono text-xs font-bold text-slate-500 hover:border-emerald-500 hover:text-emerald-600 transition"
              title="Add new page"
            >
              +
            </button>
          </div>
        </div>

        {/* Binder Open Page Display */}
        {viewMode === "spread" && rightPage ? (
          /* TWO-PAGE SPREAD (Open Binder on Table) */
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_56px_1fr] gap-6 items-stretch">
            {/* Left Page (Slots 0..8) */}
            <div className="rounded-2xl border border-slate-200/90 bg-slate-50/70 p-4 sm:p-5 shadow-xs relative">
              <div className="mb-3 flex items-center justify-between text-xs font-mono text-slate-500 border-b border-slate-200 pb-2">
                <span className="font-bold text-slate-800">{leftPage.name || `Page ${spreadLeftIdx + 1}`}</span>
                <span>Slots 01 – 09</span>
              </div>
              <div className="grid grid-cols-3 gap-2.5 sm:gap-3.5">
                {Array.from({ length: 9 }).map((_, slotIdx) => {
                  const cardId = leftPage.slots[slotIdx];
                  const card = cardId ? cardMap.get(cardId) || null : null;
                  return (
                    <BinderSleeveSlot
                      key={`p${spreadLeftIdx}-s${slotIdx}`}
                      pageIndex={spreadLeftIdx}
                      slotIndex={slotIdx}
                      card={card}
                      onOpenPicker={(p, s) => setPickerTarget({ pageIndex: p, slotIndex: s })}
                      onRemove={removeCardFromSlot}
                      onMove={moveCard}
                      formatPrice={formatPrice}
                    />
                  );
                })}
              </div>
            </div>

            {/* Center Spine with 3 Heavy Metallic D-Rings */}
            <div className="hidden lg:flex flex-col justify-around items-center py-10 relative">
              {[0, 1, 2].map((ringIdx) => (
                <div key={ringIdx} className="flex flex-col items-center gap-2">
                  <div className="h-4 w-4 rounded-full binder-hole-punch" />
                  <div className="w-9 h-20 rounded-full binder-ring" />
                  <div className="h-4 w-4 rounded-full binder-hole-punch" />
                </div>
              ))}
            </div>

            {/* Right Page (Slots 0..8) */}
            <div className="rounded-2xl border border-slate-200/90 bg-slate-50/70 p-4 sm:p-5 shadow-xs relative">
              <div className="mb-3 flex items-center justify-between text-xs font-mono text-slate-500 border-b border-slate-200 pb-2">
                <span className="font-bold text-slate-800">{rightPage.name || `Page ${spreadRightIdx + 1}`}</span>
                <span>Slots 10 – 18</span>
              </div>
              <div className="grid grid-cols-3 gap-2.5 sm:gap-3.5">
                {Array.from({ length: 9 }).map((_, slotIdx) => {
                  const cardId = rightPage.slots[slotIdx];
                  const card = cardId ? cardMap.get(cardId) || null : null;
                  return (
                    <BinderSleeveSlot
                      key={`p${spreadRightIdx}-s${slotIdx}`}
                      pageIndex={spreadRightIdx}
                      slotIndex={slotIdx}
                      card={card}
                      onOpenPicker={(p, s) => setPickerTarget({ pageIndex: p, slotIndex: s })}
                      onRemove={removeCardFromSlot}
                      onMove={moveCard}
                      formatPrice={formatPrice}
                    />
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          /* SINGLE PAGE VIEW (9 Pockets with Left Ring Margin) */
          <div className="grid grid-cols-1 md:grid-cols-[40px_1fr] gap-4 items-stretch max-w-3xl mx-auto">
            {/* Left Binder Rings */}
            <div className="hidden md:flex flex-col justify-around items-center py-8">
              {[0, 1, 2].map((ringIdx) => (
                <div key={ringIdx} className="flex flex-col items-center gap-1.5">
                  <div className="h-3.5 w-3.5 rounded-full binder-hole-punch" />
                  <div className="w-7 h-16 rounded-full binder-ring" />
                  <div className="h-3.5 w-3.5 rounded-full binder-hole-punch" />
                </div>
              ))}
            </div>

            {/* 9 Pockets Grid */}
            <div className="rounded-2xl border border-slate-200/90 bg-slate-50/70 p-4 sm:p-6 shadow-xs">
              <div className="mb-4 flex items-center justify-between text-xs font-mono text-slate-500 border-b border-slate-200 pb-2.5">
                <span className="font-bold text-slate-800">{currentPage.name || `Page ${activePageIndex + 1}`}</span>
                <span>Slots 01 – 09</span>
              </div>
              <div className="grid grid-cols-3 gap-2.5 sm:gap-4">
                {Array.from({ length: 9 }).map((_, slotIdx) => {
                  const cardId = currentPage.slots[slotIdx];
                  const card = cardId ? cardMap.get(cardId) || null : null;
                  return (
                    <BinderSleeveSlot
                      key={`p${activePageIndex}-s${slotIdx}`}
                      pageIndex={activePageIndex}
                      slotIndex={slotIdx}
                      card={card}
                      onOpenPicker={(p, s) => setPickerTarget({ pageIndex: p, slotIndex: s })}
                      onRemove={removeCardFromSlot}
                      onMove={moveCard}
                      formatPrice={formatPrice}
                    />
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Binder Bottom Navigation Bar */}
        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 pt-4 border-t border-slate-200">
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={activePageIndex === 0}
              onClick={() => setActivePageIndex(Math.max(0, activePageIndex - (viewMode === "spread" ? 2 : 1)))}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-mono text-xs font-bold text-slate-700 hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40 disabled:pointer-events-none transition shadow-xs"
            >
              <span>← Previous</span>
            </button>
            <button
              type="button"
              disabled={activePageIndex >= binder.pages.length - (viewMode === "spread" ? 2 : 1)}
              onClick={() =>
                setActivePageIndex(
                  Math.min(binder.pages.length - 1, activePageIndex + (viewMode === "spread" ? 2 : 1))
                )
              }
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-mono text-xs font-bold text-slate-700 hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40 disabled:pointer-events-none transition shadow-xs"
            >
              <span>Next Page →</span>
            </button>
          </div>

          <div className="flex items-center gap-3 font-mono text-xs">
            {binder.pages.length > 1 && (
              <button
                type="button"
                onClick={() => {
                  if (confirm(`Are you sure you want to delete Page ${activePageIndex + 1}?`)) {
                    removePage(activePageIndex);
                  }
                }}
                className="text-rose-600 hover:text-rose-700 font-semibold transition"
              >
                Delete This Page
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                if (confirm("Reset entire portfolio binder? This clears all slots.")) {
                  clearBinder();
                }
              }}
              className="text-slate-400 hover:text-rose-600 font-semibold transition"
            >
              Clear All Slots
            </button>
          </div>
        </div>
      </div>

      {/* 5. Card Picker Modal */}
      {pickerTarget && (
        <CardPickerModal
          isOpen={Boolean(pickerTarget)}
          pageIndex={pickerTarget.pageIndex}
          slotIndex={pickerTarget.slotIndex}
          onClose={() => setPickerTarget(null)}
          onSelectCard={(cardId) => {
            addCardToSlot(pickerTarget.pageIndex, pickerTarget.slotIndex, cardId);
            setPickerTarget(null);
          }}
        />
      )}
    </div>
  );
}
