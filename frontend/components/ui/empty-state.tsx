import type { ReactNode } from "react";

type EmptyStateProps = {
  title: string;
  description?: string;
  onReset?: () => void;
  resetText?: string;
  icon?: ReactNode;
  className?: string;
};

export function EmptyState({
  title,
  description,
  onReset,
  resetText = "Reset Filters",
  icon,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex min-h-[320px] flex-col items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-2xs ${className}`}
    >
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
        {icon ?? (
          <svg
            className="h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m21 21-4.35-4.35m2.35-5.65a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z"
            />
          </svg>
        )}
      </div>

      <h3 className="mt-3 text-base font-bold text-slate-900">{title}</h3>

      {description && (
        <p className="mt-1 max-w-sm text-xs leading-relaxed text-slate-500">
          {description}
        </p>
      )}

      {onReset && (
        <button
          type="button"
          onClick={onReset}
          className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold text-white shadow-2xs transition hover:bg-slate-800"
        >
          {resetText}
        </button>
      )}
    </div>
  );
}
