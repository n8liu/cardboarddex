"use client";

import React, { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { HoloCard } from "@/components/ui/holo-card";
import { cardImageUrl } from "@/lib/api";
import { shimmerBlurDataUrl } from "@/lib/shimmer";
import type { PortfolioCardItem } from "@/types/binder";

interface BinderSleeveSlotProps {
  pageIndex: number;
  slotIndex: number;
  card: PortfolioCardItem | null;
  onOpenPicker: (pageIndex: number, slotIndex: number) => void;
  onRemove: (pageIndex: number, slotIndex: number) => void;
  onMove: (fromPage: number, fromSlot: number, toPage: number, toSlot: number) => void;
  formatPrice: (val: number | null | undefined) => string;
}

export function BinderSleeveSlot({
  pageIndex,
  slotIndex,
  card,
  onOpenPicker,
  onRemove,
  onMove,
  formatPrice,
}: BinderSleeveSlotProps) {
  const [isDragTarget, setIsDragTarget] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);

  const slotLabel = String(slotIndex + 1).padStart(2, "0");

  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData(
      "application/json",
      JSON.stringify({ pageIndex, slotIndex })
    );
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (!isDragTarget) setIsDragTarget(true);
  };

  const handleDragLeave = () => {
    setIsDragTarget(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragTarget(false);
    try {
      const dataStr = e.dataTransfer.getData("application/json");
      if (dataStr) {
        const source = JSON.parse(dataStr);
        if (
          typeof source.pageIndex === "number" &&
          typeof source.slotIndex === "number" &&
          (source.pageIndex !== pageIndex || source.slotIndex !== slotIndex)
        ) {
          onMove(source.pageIndex, source.slotIndex, pageIndex, slotIndex);
        }
      }
    } catch {}
  };

  // --- EMPTY SLOT ---
  if (!card) {
    return (
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => onOpenPicker(pageIndex, slotIndex)}
        className={`group relative flex aspect-[5/7] w-full cursor-pointer flex-col items-center justify-center rounded-xl border transition-all duration-200 ${
          isDragTarget
            ? "border-emerald-500 bg-emerald-50/70 scale-[1.02] shadow-[0_0_20px_rgba(16,185,129,0.25)]"
            : "border-slate-200/90 bg-slate-50/70 hover:border-emerald-500 hover:bg-emerald-50/40 hover:shadow-sm"
        }`}
      >
        {/* Top-loading sleeve edge simulation */}
        <div className="absolute top-0 inset-x-2 h-[2px] rounded-t-md bg-gradient-to-r from-slate-200 via-slate-300 to-slate-200" />

        {/* Slot Number watermark */}
        <span className="absolute top-2.5 left-2.5 font-mono text-[10px] font-bold text-slate-400 transition-colors group-hover:text-emerald-700">
          #{slotLabel}
        </span>

        {/* Insert Prompt */}
        <div className="flex flex-col items-center gap-2 text-center p-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-500 shadow-2xs transition-all duration-200 group-hover:scale-110 group-hover:border-emerald-500 group-hover:bg-emerald-600 group-hover:text-white group-hover:shadow-md">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 5v14M5 12h14" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span className="font-mono text-[11px] font-semibold text-slate-500 transition-colors group-hover:text-slate-900">
            Insert Card
          </span>
        </div>

        {/* Gloss overlay */}
        <div className="pointer-events-none absolute inset-0 rounded-xl bg-gradient-to-tr from-white/[0.2] to-white/[0.5] opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      </div>
    );
  }

  // --- FILLED SLOT ---
  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`group relative flex aspect-[5/7] w-full flex-col overflow-hidden rounded-xl border bg-white transition-all duration-200 binder-sleeve-gloss ${
        isDragTarget
          ? "border-emerald-500 scale-[1.02] shadow-[0_0_20px_rgba(16,185,129,0.3)]"
          : "border-slate-200/90 shadow-xs hover:border-slate-300 hover:shadow-md"
      }`}
    >
      {/* Top sleeve lip line */}
      <div className="absolute top-0 inset-x-0 h-[2px] z-20 bg-gradient-to-r from-slate-200 via-slate-300 to-slate-200" />

      {/* HoloCard Tilt Shader container */}
      <div className="relative h-full w-full p-2 flex items-center justify-center bg-white">
        <HoloCard
          maxTilt={12}
          rarity={card.rarity}
          className="h-full w-full flex items-center justify-center rounded-lg overflow-hidden"
        >
          {imageFailed ? (
            <div className="flex h-full w-full flex-col items-center justify-center bg-slate-50 text-center p-2">
              <span className="font-mono text-xs font-bold text-slate-700">{card.name}</span>
              <span className="font-mono text-[10px] text-slate-500">{card.set_name}</span>
            </div>
          ) : (
            <Image
              alt={`${card.name} from ${card.set_name}`}
              className="object-contain transition duration-300 group-hover:scale-[1.03]"
              fill
              onError={() => setImageFailed(true)}
              placeholder="blur"
              blurDataURL={shimmerBlurDataUrl(250, 350)}
              quality={75}
              sizes="(max-width: 640px) 45vw, (max-width: 1024px) 30vw, 200px"
              src={cardImageUrl(card.image_url)}
            />
          )}
        </HoloCard>
      </div>

      {/* Top badges (Slot number) */}
      <div className="absolute top-2.5 left-2.5 z-20 flex items-center gap-1">
        <span className="rounded bg-white/95 px-1.5 py-0.5 font-mono text-[9px] font-bold text-slate-700 backdrop-blur-sm border border-slate-200 shadow-2xs">
          #{slotLabel}
        </span>
      </div>

      {/* Bottom price badge */}
      <div className="absolute bottom-2.5 inset-x-2 z-20 flex items-center justify-between pointer-events-none">
        <span className="rounded-md bg-white/95 px-2 py-0.5 font-mono text-[11px] font-bold text-slate-950 backdrop-blur-sm border border-slate-200 shadow-xs">
          {formatPrice(card.market_price)}
        </span>
        {card.price_change_24h !== null && card.price_change_24h !== undefined && (
          <span
            className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold backdrop-blur-sm ${
              card.price_change_24h >= 0
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : "bg-rose-50 text-rose-700 border border-rose-200"
            }`}
          >
            {card.price_change_24h >= 0 ? "+" : ""}
            {card.price_change_24h.toFixed(2)}
          </span>
        )}
      </div>

      {/* Hover Quick Actions Overlay (Frosted White Glassmorphism) */}
      <div className="absolute inset-0 z-30 flex flex-col justify-between bg-white/95 p-3 opacity-0 transition-opacity duration-200 group-hover:opacity-100 backdrop-blur-sm border border-slate-200">
        <div className="flex items-start justify-between">
          <div className="min-w-0 pr-2">
            <p className="truncate font-mono text-xs font-bold text-slate-950" title={card.name}>
              {card.name}
            </p>
            <p className="truncate font-mono text-[10px] text-slate-500" title={card.set_name}>
              {card.set_name} • #{card.number}
            </p>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRemove(pageIndex, slotIndex);
            }}
            className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 transition"
            title="Remove from binder"
            aria-label="Remove card"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col gap-1.5 pt-2">
          <Link
            href={`/cards/${card.id}`}
            prefetch={false}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-slate-900 px-2.5 py-1.5 font-mono text-[11px] font-semibold text-white transition hover:bg-slate-800 shadow-xs"
          >
            <span>Inspect Profile</span>
            <span className="text-slate-300">→</span>
          </Link>
          <button
            type="button"
            onClick={() => onOpenPicker(pageIndex, slotIndex)}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 font-mono text-[11px] font-semibold text-slate-700 transition hover:bg-slate-50 hover:text-slate-950 shadow-2xs"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
            <span>Swap Card</span>
          </button>
        </div>
      </div>
    </div>
  );
}
