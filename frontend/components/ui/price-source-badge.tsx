/** Prices older than this are "last known", matching the backend stale rule (ppt_prices.py). */
export const STALE_PRICE_DAYS = 7;

export function isStalePriceDate(date: string | null | undefined, now = Date.now()): boolean {
  if (!date) return false;
  const time = Date.parse(date);
  return Number.isFinite(time) && now - time > STALE_PRICE_DAYS * 86_400_000;
}

/** Where a price came from and how current it is, so sold and asking prices are never confused. */
export function PriceSourceBadge({ label, stale = false, title, className = "" }: {
  label: string;
  stale?: boolean;
  title?: string;
  className?: string;
}) {
  return <span title={title}
    className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${stale
      ? "border-amber-300 bg-amber-50 text-amber-800"
      : "border-slate-200 bg-white text-slate-600"} ${className}`}>
    {stale && <span aria-hidden="true">●</span>}
    {label}
  </span>;
}
