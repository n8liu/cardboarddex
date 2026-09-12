"use client";

import { useMemo, useState } from "react";

type PaginationProps = {
  page: number;
  totalPages: number;
  onPageChange: (newPage: number) => void;
  disabled?: boolean;
  className?: string;
  totalItems?: number;
  itemName?: string;
};

/**
 * Computes window of visible page numbers with ellipsis.
 * e.g. [1, "...", 4, 5, 6, "...", 20]
 */
function getPageNumbers(currentPage: number, totalPages: number): (number | "...")[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages: (number | "...")[] = [];

  if (currentPage <= 4) {
    for (let i = 1; i <= 5; i++) pages.push(i);
    pages.push("...");
    pages.push(totalPages);
  } else if (currentPage >= totalPages - 3) {
    pages.push(1);
    pages.push("...");
    for (let i = totalPages - 4; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    pages.push("...");
    pages.push(currentPage - 1);
    pages.push(currentPage);
    pages.push(currentPage + 1);
    pages.push("...");
    pages.push(totalPages);
  }

  return pages;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  disabled = false,
  className = "",
  totalItems,
  itemName = "items",
}: PaginationProps) {
  const [jumpInput, setJumpInput] = useState("");

  const pageNumbers = useMemo(
    () => getPageNumbers(page, totalPages),
    [page, totalPages]
  );

  if (totalPages <= 1) return null;

  const handleJumpSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const target = parseInt(jumpInput, 10);
    if (!isNaN(target) && target >= 1 && target <= totalPages) {
      onPageChange(target);
      setJumpInput("");
    }
  };

  return (
    <div
      className={`mt-10 flex flex-col items-center justify-between gap-4 border-t border-slate-200/80 pt-6 sm:flex-row ${className}`}
    >
      {/* Left: Summary info */}
      <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-slate-500">
        <span>
          Showing page <strong className="font-bold text-slate-900">{page}</strong> of{" "}
          <strong className="font-bold text-slate-900">{totalPages}</strong>
        </span>
        {totalItems !== undefined && totalItems > 0 && (
          <span className="hidden sm:inline text-slate-400">
            · {totalItems.toLocaleString()} {itemName}
          </span>
        )}
      </div>

      {/* Center/Right: Numbered pagination controls */}
      <div className="flex flex-wrap items-center justify-center gap-1 sm:gap-1.5">
        {/* First page button */}
        <button
          type="button"
          onClick={() => onPageChange(1)}
          disabled={disabled || page <= 1}
          title="First page"
          className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white font-mono text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          «
        </button>

        {/* Previous page button */}
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={disabled || page <= 1}
          className="inline-flex h-9 items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 font-mono text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span>←</span>
          <span className="hidden md:inline">Prev</span>
        </button>

        {/* Numbered Page Pills */}
        <div className="flex items-center gap-1">
          {pageNumbers.map((p, idx) =>
            p === "..." ? (
              <span
                key={`ellipsis-${idx}`}
                className="flex h-9 w-6 items-center justify-center font-mono text-xs font-bold text-slate-400 select-none"
              >
                …
              </span>
            ) : (
              <button
                key={p}
                type="button"
                onClick={() => onPageChange(p)}
                disabled={disabled || p === page}
                className={`inline-flex h-9 min-w-9 items-center justify-center rounded-xl px-2.5 font-mono text-xs font-bold transition ${
                  p === page
                    ? "bg-slate-900 text-white shadow-xs"
                    : "border border-slate-200 bg-white text-slate-700 shadow-2xs hover:border-slate-300 hover:bg-slate-50"
                } disabled:cursor-default`}
              >
                {p}
              </button>
            )
          )}
        </div>

        {/* Next page button */}
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={disabled || page >= totalPages}
          className="inline-flex h-9 items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 font-mono text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span className="hidden md:inline">Next</span>
          <span>→</span>
        </button>

        {/* Last page button */}
        <button
          type="button"
          onClick={() => onPageChange(totalPages)}
          disabled={disabled || page >= totalPages}
          title="Last page"
          className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white font-mono text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          »
        </button>

        {/* Jump-to-page input for larger datasets */}
        {totalPages > 5 && (
          <form
            onSubmit={handleJumpSubmit}
            className="hidden lg:flex items-center gap-1.5 pl-2 border-l border-slate-200/80"
          >
            <span className="text-[11px] font-mono text-slate-400">Go to:</span>
            <input
              type="number"
              min={1}
              max={totalPages}
              value={jumpInput}
              onChange={(e) => setJumpInput(e.target.value)}
              placeholder="#"
              className="h-8 w-12 rounded-lg border border-slate-200 bg-white px-1.5 text-center font-mono text-xs text-slate-800 outline-none transition focus:border-slate-400 focus:ring-1 focus:ring-slate-400"
            />
          </form>
        )}
      </div>
    </div>
  );
}
