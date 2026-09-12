"use client";

interface PageLoadingStatusProps {
  title: string;
  description?: string;
  className?: string;
}

export function PageLoadingStatus({
  title,
  description = "Connecting to real-time market data engine...",
  className = "",
}: PageLoadingStatusProps) {
  return (
    <div
      className={`flex items-center gap-3 rounded-2xl border border-slate-200/90 bg-white/95 px-4 py-3 shadow-xs backdrop-blur-xs ${className}`}
    >
      <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-emerald-400">
        <svg
          className="h-4 w-4 animate-spin text-emerald-400"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
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
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          <p className="truncate font-mono text-xs font-bold uppercase tracking-wider text-slate-950 sm:text-sm">
            {title}
          </p>
        </div>
        {description && (
          <p className="mt-0.5 truncate font-mono text-[11px] text-slate-500">
            {description}
          </p>
        )}
      </div>

      <div className="hidden shrink-0 items-center gap-1.5 font-mono text-[11px] font-semibold text-slate-400 sm:flex">
        <span>INSTANT SHELL</span>
        <span className="text-slate-300">·</span>
        <span className="text-emerald-700">STREAMING API</span>
      </div>
    </div>
  );
}
