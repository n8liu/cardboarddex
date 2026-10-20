"use client";

import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useCurrency } from "@/context/currency-context";

/** Highest bounded price; the max thumb at the end of the track means "no upper limit". */
export const PRICE_RANGE_MAX = 5000;
const LOG_SPAN = Math.log(PRICE_RANGE_MAX + 1);
const KEY_STEP = 0.01;
const PAGE_STEP = 0.1;
const TICKS: { price: number; label: string }[] = [
  { price: 0, label: "$0" },
  { price: 10, label: "$10" },
  { price: 100, label: "$100" },
  { price: 1000, label: "$1k" },
  { price: PRICE_RANGE_MAX, label: "$5k+" },
];

export type PriceRangeValue = {
  min: number | null;
  max: number | null;
};

/**
 * Continuous logarithmic scale: track position 0–1 maps to $0–$5,000 in whole dollars,
 * giving the dense low-price range as much room as the sparse high end.
 */
export function positionToPrice(position: number): number {
  const clamped = Math.max(0, Math.min(1, position));
  return Math.round(Math.exp(clamped * LOG_SPAN) - 1);
}

export function priceToPosition(price: number | null | undefined, isMax: boolean): number {
  if (price === null || price === undefined) return isMax ? 1 : 0;
  if (price <= 0) return 0;
  if (price >= PRICE_RANGE_MAX) return 1;
  return Math.log(price + 1) / LOG_SPAN;
}

/** Filter value for a thumb position: the min floor is $0, and the max at the end is unbounded. */
export function positionToFilter(position: number, isMax: boolean): number | null {
  if (isMax && position >= 1) return null;
  return positionToPrice(position);
}

type PriceRangeSliderProps = {
  minPrice: number | null;
  maxPrice: number | null;
  onChange: (range: PriceRangeValue) => void;
  disabled?: boolean;
};

export function PriceRangeSlider({
  minPrice,
  maxPrice,
  onChange,
  disabled = false,
}: PriceRangeSliderProps) {
  const { formatPrice } = useCurrency();
  const trackRef = useRef<HTMLDivElement | null>(null);
  const minThumbId = useId();
  const maxThumbId = useId();

  // Track positions (0–1). Dragging updates these locally and commits once on release.
  const [minPos, setMinPos] = useState(() => priceToPosition(minPrice, false));
  const [maxPos, setMaxPos] = useState(() => priceToPosition(maxPrice, true));
  const [activeThumb, setActiveThumb] = useState<"min" | "max" | null>(null);

  // Synchronize when external props change, but never fight an in-progress drag.
  useEffect(() => {
    if (activeThumb) return;
    setMinPos(priceToPosition(minPrice, false));
    setMaxPos(priceToPosition(maxPrice, true));
  }, [minPrice, maxPrice, activeThumb]);

  const minValue = positionToPrice(minPos);
  const maxValue = positionToFilter(maxPos, true);
  const isFiltered = minValue > 0 || maxValue !== null;

  const commit = useCallback(
    (nextMin: number, nextMax: number) => {
      onChange({ min: positionToFilter(nextMin, false), max: positionToFilter(nextMax, true) });
    },
    [onChange]
  );

  const positionFromClientX = (clientX: number): number | null => {
    if (!trackRef.current) return null;
    const rect = trackRef.current.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  };

  const handlePointerDown = (thumb: "min" | "max") => (e: React.PointerEvent) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    setActiveThumb(thumb);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (thumb: "min" | "max") => (e: React.PointerEvent) => {
    if (activeThumb !== thumb || disabled) return;
    const position = positionFromClientX(e.clientX);
    if (position === null) return;
    if (thumb === "min") setMinPos(Math.min(position, maxPos));
    else setMaxPos(Math.max(position, minPos));
  };

  const handlePointerUp = (thumb: "min" | "max") => (e: React.PointerEvent) => {
    if (activeThumb !== thumb) return;
    setActiveThumb(null);
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch (err) {
      // Capture may already be released (e.g. pointercancel); nothing to undo.
      console.debug("Price slider pointer capture release skipped:", err);
    }
    commit(minPos, maxPos);
  };

  const handleTrackClick = (e: React.MouseEvent) => {
    if (disabled) return;
    const position = positionFromClientX(e.clientX);
    if (position === null) return;
    // Move whichever thumb is closer.
    if (Math.abs(position - minPos) <= Math.abs(position - maxPos)) {
      const nextMin = Math.min(position, maxPos);
      setMinPos(nextMin);
      commit(nextMin, maxPos);
    } else {
      const nextMax = Math.max(position, minPos);
      setMaxPos(nextMax);
      commit(minPos, nextMax);
    }
  };

  const handleKeyDown = (thumb: "min" | "max") => (e: React.KeyboardEvent) => {
    if (disabled) return;
    const step = e.shiftKey ? PAGE_STEP : KEY_STEP;
    let target: number | null = null;
    const current = thumb === "min" ? minPos : maxPos;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") target = current + step;
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") target = current - step;
    else if (e.key === "PageUp") target = current + PAGE_STEP;
    else if (e.key === "PageDown") target = current - PAGE_STEP;
    else if (e.key === "Home") target = thumb === "min" ? 0 : minPos;
    else if (e.key === "End") target = thumb === "max" ? 1 : maxPos;
    if (target === null) return;
    e.preventDefault();
    if (thumb === "min") {
      const nextMin = Math.max(0, Math.min(target, maxPos));
      setMinPos(nextMin);
      commit(nextMin, maxPos);
    } else {
      const nextMax = Math.min(1, Math.max(target, minPos));
      setMaxPos(nextMax);
      commit(minPos, nextMax);
    }
  };

  const handleReset = () => {
    setMinPos(0);
    setMaxPos(1);
    onChange({ min: 0, max: null });
  };

  // Human-readable range display
  const rangeDisplay = useMemo(() => {
    if (!isFiltered) return "All Prices";
    if (maxValue === null) return `${formatPrice(minValue)}+`;
    if (minValue === 0) return `Up to ${formatPrice(maxValue)}`;
    if (minValue === maxValue) return formatPrice(minValue);
    return `${formatPrice(minValue)} – ${formatPrice(maxValue)}`;
  }, [formatPrice, isFiltered, maxValue, minValue]);

  const leftPercent = minPos * 100;
  const rightPercent = maxPos * 100;

  return (
    <div className="w-full select-none">
      {/* Header Row: Label, Active Range Badge, and Reset Button */}
      <div className="flex items-center justify-between gap-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
            Price Range
          </span>
          {isFiltered && (
            <span
              className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"
              title="Price filter active"
            />
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <span
            className={`font-mono text-[11px] font-bold px-2 py-0.5 rounded-md border transition ${
              isFiltered
                ? "bg-emerald-50 text-emerald-800 border-emerald-200/80 shadow-2xs font-black"
                : "bg-slate-50 text-slate-500 border-slate-200/60"
            }`}
          >
            {rangeDisplay}
          </span>
          {isFiltered && (
            <button
              type="button"
              onClick={handleReset}
              className="text-[10px] font-bold text-slate-400 hover:text-slate-700 transition"
              title="Reset price range"
              aria-label="Reset price filter"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Slider Interactive Track Area */}
      <div className="relative mt-3.5 pb-5 pt-2">
        <div
          ref={trackRef}
          onClick={handleTrackClick}
          className="relative h-2 w-full cursor-pointer rounded-full bg-slate-200"
          role="presentation"
        >
          {/* Active Highlighted Range Bar */}
          <div
            className="absolute top-0 h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 shadow-xs"
            style={{
              left: `${leftPercent}%`,
              width: `${Math.max(0, rightPercent - leftPercent)}%`,
            }}
          />

          {/* Draggable Min Thumb (Left Dot) */}
          <div
            id={minThumbId}
            role="slider"
            tabIndex={disabled ? -1 : 0}
            aria-label="Minimum price range handle"
            aria-valuemin={0}
            aria-valuemax={maxValue ?? PRICE_RANGE_MAX}
            aria-valuenow={minValue}
            aria-valuetext={formatPrice(minValue)}
            onPointerDown={handlePointerDown("min")}
            onPointerMove={handlePointerMove("min")}
            onPointerUp={handlePointerUp("min")}
            onPointerCancel={handlePointerUp("min")}
            onKeyDown={handleKeyDown("min")}
            className={`absolute top-1/2 -ml-2.5 -mt-2.5 h-5 w-5 rounded-full border-2 border-emerald-600 bg-white shadow-md transition-transform touch-none cursor-grab active:cursor-grabbing focus:outline-none focus:ring-2 focus:ring-emerald-500/40 ${
              activeThumb === "min" ? "scale-125 z-20 ring-2 ring-emerald-500/40" : "z-10 hover:scale-110"
            }`}
            style={{ left: `${leftPercent}%` }}
          >
            <div className="absolute inset-1 rounded-full bg-emerald-500/20" />
          </div>

          {/* Draggable Max Thumb (Right Dot) */}
          <div
            id={maxThumbId}
            role="slider"
            tabIndex={disabled ? -1 : 0}
            aria-label="Maximum price range handle"
            aria-valuemin={minValue}
            aria-valuemax={PRICE_RANGE_MAX}
            aria-valuenow={maxValue ?? PRICE_RANGE_MAX}
            aria-valuetext={maxValue === null ? "Highest / Any price" : formatPrice(maxValue)}
            onPointerDown={handlePointerDown("max")}
            onPointerMove={handlePointerMove("max")}
            onPointerUp={handlePointerUp("max")}
            onPointerCancel={handlePointerUp("max")}
            onKeyDown={handleKeyDown("max")}
            className={`absolute top-1/2 -ml-2.5 -mt-2.5 h-5 w-5 rounded-full border-2 border-emerald-600 bg-white shadow-md transition-transform touch-none cursor-grab active:cursor-grabbing focus:outline-none focus:ring-2 focus:ring-emerald-500/40 ${
              activeThumb === "max" ? "scale-125 z-20 ring-2 ring-emerald-500/40" : "z-10 hover:scale-110"
            }`}
            style={{ left: `${rightPercent}%` }}
          >
            <div className="absolute inset-1 rounded-full bg-emerald-500/20" />
          </div>
        </div>

        {/* Scale labels at their true positions on the log track */}
        <div className="relative mt-2.5 h-3 text-[10px] font-mono text-slate-400 font-semibold">
          {TICKS.map((tick, index) => {
            const position = priceToPosition(tick.price, false);
            const inRange = position >= minPos && position <= maxPos;
            const align = index === 0 ? "" : index === TICKS.length - 1 ? "-translate-x-full" : "-translate-x-1/2";
            return (
              <span
                key={tick.label}
                className={`absolute top-0 ${align} ${inRange && isFiltered ? "text-slate-700 font-bold" : ""}`}
                style={{ left: `${position * 100}%` }}
              >
                {tick.label}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
