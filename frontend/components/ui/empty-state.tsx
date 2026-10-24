import type { ReactNode } from "react";

type EmptyStateVariant = "empty" | "unavailable" | "collecting";

type EmptyStateProps = {
  title: string;
  description?: ReactNode;
  /** empty: nothing matches; unavailable: data could not load; collecting: not enough history yet. */
  variant?: EmptyStateVariant;
  onReset?: () => void;
  resetText?: string;
  onRetry?: () => void;
  retryText?: string;
  icon?: ReactNode;
  /** Smaller box for columns and panels inside a page. */
  compact?: boolean;
  role?: "alert" | "status";
  className?: string;
};

const ICON_PATHS: Record<EmptyStateVariant, string> = {
  empty: "m21 21-4.35-4.35m2.35-5.65a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  unavailable: "M12 9v3.75m0 3.75h.008M10.29 3.86 1.82 18a1.5 1.5 0 0 0 1.29 2.25h16.94A1.5 1.5 0 0 0 21.34 18L12.87 3.86a1.5 1.5 0 0 0-2.58 0Z",
  collecting: "M12 6v6l4 2m5-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
};

const ICON_TONE: Record<EmptyStateVariant, string> = {
  empty: "bg-slate-100 text-slate-500",
  unavailable: "bg-rose-50 text-rose-600",
  collecting: "bg-amber-50 text-amber-600",
};

export function EmptyState({
  title,
  description,
  variant = "empty",
  onReset,
  resetText = "Reset Filters",
  onRetry,
  retryText = "Retry",
  icon,
  compact = false,
  role,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      role={role}
      className={`flex flex-col items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white text-center shadow-2xs ${
        compact ? "px-6 py-10" : "min-h-[320px] p-12"
      } ${className}`}
    >
      <div className={`mx-auto flex items-center justify-center rounded-2xl ${ICON_TONE[variant]} ${compact ? "h-10 w-10" : "h-12 w-12"}`}>
        {icon ?? (
          <svg aria-hidden="true" className={compact ? "h-5 w-5" : "h-6 w-6"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d={ICON_PATHS[variant]} />
          </svg>
        )}
      </div>

      <h3 className={`mt-3 font-bold text-slate-900 ${compact ? "text-sm" : "text-base"}`}>{title}</h3>

      {description && (
        <p className="mt-1 max-w-sm text-xs leading-relaxed text-slate-500">
          {description}
        </p>
      )}

      {(onRetry || onReset) && (
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-800 shadow-2xs transition hover:border-slate-400"
            >
              {retryText}
            </button>
          )}
          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold text-white shadow-2xs transition hover:bg-slate-800"
            >
              {resetText}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
