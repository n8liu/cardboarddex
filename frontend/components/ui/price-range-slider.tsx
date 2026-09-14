"use client";

import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useCurrency } from "@/context/currency-context";

export const PRICE_RANGE_STEPS = [1, 10, 25, 50, 100, 150, 200, 250, 500, 1000, 2500, 5000] as const;

export type PriceRangeValue = {
  min: number | null;
  max: number | null;
};

export function priceToStepIndex(price: number | null | undefined, isMax: boolean): number {
  if (price === null || price === undefined) {
    return isMax ? PRICE_RANGE_STEPS.length - 1 : 0;
  }
  if (price <= 1) return 0;
  if (price >= PRICE_RANGE_STEPS[PRICE_RANGE_STEPS.length - 1]) {
    return PRICE_RANGE_STEPS.length - 1;
  }
  // Find closest step
  let closestIndex = 0;
  let minDiff = Infinity;
  for (let i = 0; i < PRICE_RANGE_STEPS.length; i++) {
    const diff = Math.abs(PRICE_RANGE_STEPS[i] - price);
    if (diff < minDiff) {
      minDiff = diff;
      closestIndex = i;
    }
  }
  return closestIndex;
}

export function stepIndexToPrice(index: number, isMax: boolean): number | null {
  if (isMax) {
    if (index >= PRICE_RANGE_STEPS.length - 1) return null; // unbounded 5000+
    return PRICE_RANGE_STEPS[index];
  }
  if (index <= 0) return 0; // index 0 includes cards down to 0
  return PRICE_RANGE_STEPS[index];
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

  // Internal step indices (0 to PRICE_RANGE_STEPS.length - 1)
  const [minStep, setMinStep] = useState(() => priceToStepIndex(minPrice, false));
  const [maxStep, setMaxStep] = useState(() => priceToStepIndex(maxPrice, true));
  const [activeThumb, setActiveThumb] = useState<"min" | "max" | null>(null);

  // Synchronize when external props change
  useEffect(() => {
    const nextMin = priceToStepIndex(minPrice, false);
    const nextMax = priceToStepIndex(maxPrice, true);
    setMinStep(nextMin);
    setMaxStep(nextMax);
  }, [minPrice, maxPrice]);

  const totalSteps = PRICE_RANGE_STEPS.length - 1;
  const leftPercent = (minStep / totalSteps) * 100;
  const rightPercent = (maxStep / totalSteps) * 100;

  const isFiltered = minStep > 0 || maxStep < totalSteps;

  const handleStepCommit = useCallback(
    (newMin: number, newMax: number) => {
      const minVal = stepIndexToPrice(newMin, false);
      const maxVal = stepIndexToPrice(newMax, true);
      onChange({ min: minVal, max: maxVal });
    },
    [onChange]
  );

  const updateThumbFromPointer = useCallback(
    (clientX: number, thumb: "min" | "max") => {
      if (!trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      const rawFrac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const stepIndex = Math.round(rawFrac * totalSteps);

      if (thumb === "min") {
        const clampedMin = Math.min(stepIndex, maxStep);
        setMinStep(clampedMin);
        handleStepCommit(clampedMin, maxStep);
      } else {
        const clampedMax = Math.max(stepIndex, minStep);
        setMaxStep(clampedMax);
        handleStepCommit(minStep, clampedMax);
      }
    },
    [handleStepCommit, maxStep, minStep, totalSteps]
  );

  const handlePointerDown = (thumb: "min" | "max") => (e: React.PointerEvent) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    setActiveThumb(thumb);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (thumb: "min" | "max") => (e: React.PointerEvent) => {
    if (activeThumb !== thumb || disabled) return;
    updateThumbFromPointer(e.clientX, thumb);
  };

  const handlePointerUp = (thumb: "min" | "max") => (e: React.PointerEvent) => {
    if (activeThumb === thumb) {
      setActiveThumb(null);
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {}
    }
  };

  const handleTrackClick = (e: React.MouseEvent) => {
    if (disabled || !trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const rawFrac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const stepIndex = Math.round(rawFrac * totalSteps);

    // Determine which thumb is closer
    const distToMin = Math.abs(stepIndex - minStep);
    const distToMax = Math.abs(stepIndex - maxStep);

    if (distToMin <= distToMax) {
      const newMin = Math.min(stepIndex, maxStep);
      setMinStep(newMin);
      handleStepCommit(newMin, maxStep);
    } else {
      const newMax = Math.max(stepIndex, minStep);
      setMaxStep(newMax);
      handleStepCommit(minStep, newMax);
    }
  };

  const handleKeyDown = (thumb: "min" | "max") => (e: React.KeyboardEvent) => {
    if (disabled) return;
    let delta = 0;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") delta = 1;
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") delta = -1;
    else if (e.key === "Home") {
      if (thumb === "min") {
        setMinStep(0);
        handleStepCommit(0, maxStep);
      }
      return;
    } else if (e.key === "End") {
      if (thumb === "max") {
        setMaxStep(totalSteps);
        handleStepCommit(minStep, totalSteps);
      }
      return;
    }

    if (delta !== 0) {
      e.preventDefault();
      if (thumb === "min") {
        const nextMin = Math.max(0, Math.min(minStep + delta, maxStep));
        setMinStep(nextMin);
        handleStepCommit(nextMin, maxStep);
      } else {
        const nextMax = Math.min(totalSteps, Math.max(maxStep + delta, minStep));
        setMaxStep(nextMax);
        handleStepCommit(minStep, nextMax);
      }
    }
  };

  const handleReset = () => {
    setMinStep(0);
    setMaxStep(totalSteps);
    onChange({ min: 0, max: null });
  };

  // Human-readable range display
  const rangeDisplay = useMemo(() => {
    if (minStep === 0 && maxStep === totalSteps) {
      return "All Prices";
    }
    const minVal = PRICE_RANGE_STEPS[minStep];
    const maxVal = PRICE_RANGE_STEPS[maxStep];

    if (minStep === 0) {
      return `${formatPrice(maxVal)}`;
    }
    if (maxStep === totalSteps) {
      return `${formatPrice(minVal)}+`;
    }
    if (minStep === maxStep) {
      return formatPrice(minVal);
    }
    return `${formatPrice(minVal)} – ${formatPrice(maxVal)}`;
  }, [formatPrice, maxStep, minStep, totalSteps]);

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
            className="absolute top-0 h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 shadow-xs transition-all duration-75"
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
            aria-valuemax={PRICE_RANGE_STEPS[maxStep]}
            aria-valuenow={PRICE_RANGE_STEPS[minStep]}
            aria-valuetext={formatPrice(PRICE_RANGE_STEPS[minStep])}
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
            aria-valuemin={PRICE_RANGE_STEPS[minStep]}
            aria-valuemax={PRICE_RANGE_STEPS[totalSteps]}
            aria-valuenow={PRICE_RANGE_STEPS[maxStep]}
            aria-valuetext={
              maxStep === totalSteps
                ? "Highest / Any price"
                : formatPrice(PRICE_RANGE_STEPS[maxStep])
            }
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

        {/* Milestone Tick Marks & Labels */}
        <div className="mt-2.5 flex justify-between text-[10px] font-mono text-slate-400 font-semibold px-0.5">
          <span className={minStep === 0 ? "text-emerald-700 font-bold" : ""}>$1</span>
          <span className={minStep <= 2 && maxStep >= 2 ? "text-slate-700 font-bold" : ""}>$25</span>
          <span className={minStep <= 4 && maxStep >= 4 ? "text-slate-700 font-bold" : ""}>$100</span>
          <span className={minStep <= 7 && maxStep >= 7 ? "text-slate-700 font-bold" : ""}>$250</span>
          <span className={minStep <= 9 && maxStep >= 9 ? "text-slate-700 font-bold" : ""}>$1k</span>
          <span className={maxStep === totalSteps ? "text-emerald-700 font-bold" : ""}>$5k+</span>
        </div>
      </div>
    </div>
  );
}
