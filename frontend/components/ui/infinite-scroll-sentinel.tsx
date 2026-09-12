"use client";

import { useEffect, useRef } from "react";

export interface InfiniteScrollSentinelProps {
  hasMore: boolean;
  isLoading: boolean;
  onLoadMore: () => void;
  itemName?: string;
  totalLoaded?: number;
  totalItems?: number;
}

export function InfiniteScrollSentinel({
  hasMore,
  isLoading,
  onLoadMore,
  itemName = "items",
  totalLoaded,
  totalItems,
}: InfiniteScrollSentinelProps) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const loadingRef = useRef(isLoading);
  const hasMoreRef = useRef(hasMore);
  const onLoadMoreRef = useRef(onLoadMore);

  loadingRef.current = isLoading;
  hasMoreRef.current = hasMore;
  onLoadMoreRef.current = onLoadMore;

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries[0];
        if (first?.isIntersecting && hasMoreRef.current && !loadingRef.current) {
          onLoadMoreRef.current();
        }
      },
      { rootMargin: "320px 0px" }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={sentinelRef}
      className="mt-10 flex min-h-24 flex-col items-center justify-center gap-2 border-t border-slate-100 py-8"
      aria-live="polite"
    >
      {hasMore ? (
        <button
          type="button"
          onClick={() => {
            if (!isLoading) onLoadMore();
          }}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-2.5 font-mono text-xs font-bold text-slate-700 shadow-sm transition hover:border-emerald-500 hover:bg-slate-50 hover:text-emerald-800 disabled:cursor-wait disabled:opacity-60"
        >
          {isLoading ? (
            <>
              <svg
                className="h-3.5 w-3.5 animate-spin text-emerald-600"
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>Loading more {itemName}…</span>
            </>
          ) : (
            <>
              <span>Load more {itemName}</span>
              <span className="text-[10px] text-slate-400">↓</span>
            </>
          )}
        </button>
      ) : (totalLoaded !== undefined && totalLoaded > 0) || (totalItems !== undefined && totalItems > 0) ? (
        <div className="flex items-center gap-2 text-slate-400">
          <span className="h-1 w-1 rounded-full bg-slate-300" />
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em]">
            {totalItems !== undefined
              ? `All ${totalItems.toLocaleString()} ${itemName} loaded · End of results`
              : `End of results`}
          </p>
          <span className="h-1 w-1 rounded-full bg-slate-300" />
        </div>
      ) : null}

      {totalLoaded !== undefined && totalItems !== undefined && totalItems > 0 && hasMore ? (
        <p className="font-mono text-[10px] text-slate-400">
          Showing {totalLoaded.toLocaleString()} of {totalItems.toLocaleString()} {itemName}
        </p>
      ) : null}
    </div>
  );
}
