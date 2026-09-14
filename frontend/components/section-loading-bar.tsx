"use client";

interface SectionLoadingBarProps {
  label: string;
  detail?: string;
  className?: string;
  compact?: boolean;
}

export function SectionLoadingBar({
  label,
  detail,
  className = "",
  compact = false,
}: SectionLoadingBarProps) {
  return (
    <div
      className={`rounded-2xl border border-slate-200/90 bg-white/90 shadow-xs backdrop-blur-xs font-mono transition-all duration-300 ${
        compact ? "p-3 mb-4" : "p-4 mb-6"
      } ${className}`}
      role="status"
      aria-live="polite"
    >
      {/* Header Row: Label & Status Indicator */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          {/* Animated Pulsing Status Dot */}
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-xs" />
          </span>
          <span className="text-xs sm:text-sm font-bold tracking-tight text-slate-900 uppercase">
            {label}
          </span>
        </div>

        {/* Optional Streaming / Telemetry detail */}
        {detail && (
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
            <span className="hidden sm:inline text-slate-300">·</span>
            <span className="truncate">{detail}</span>
          </div>
        )}
      </div>

      {/* Animated Gradient Progress Track */}
      <div className="mt-3 relative h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="section-progress-indeterminate absolute inset-y-0 w-2/5 rounded-full bg-gradient-to-r from-emerald-600 via-teal-400 to-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
      </div>
    </div>
  );
}
