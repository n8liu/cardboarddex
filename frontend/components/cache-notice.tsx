"use client";
import { useState } from "react";
import type { CacheMetadata } from "@/lib/api";

export function useCacheNotice() {
  return useState<CacheMetadata | null>(null);
}

export function CacheNotice({ metadata }: { metadata: CacheMetadata | null }) {
  if (!metadata?.status.startsWith("stale")) return null;
  return <p role="status" className="my-2 text-xs text-amber-800">
    {metadata.status === "stale" ? "Cached results; refreshing." : "Cached results; refresh unavailable."}
    {metadata.generatedAt !== null && <> Snapshot generated {new Date(metadata.generatedAt).toLocaleString()}.</>}
    {" "}Price observation dates may be older.
  </p>;
}

/** Worker-published snapshot served past its fresh window (worker stopped or behind). */
export function SnapshotNotice({ generatedAt }: { generatedAt: string }) {
  return <p role="status" className="my-2 text-xs text-amber-800">
    Prices as of {new Date(generatedAt).toLocaleString()}; updates are paused and will resume automatically.
  </p>;
}
