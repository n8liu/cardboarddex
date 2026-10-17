"use client";

import { useCurrency } from "@/context/currency-context";

type Comparison = {
  previous_price?: number | null;
  comparison_price?: number | null;
  price_change_amount?: number | null;
  comparison_source?: "history" | "estimated" | "pokemonpricetracker_history" | null;
};

export function PriceComparison({ value, period }: { value: Comparison; period: string }) {
  const { formatPrice } = useCurrency();
  const { previous_price: previous, comparison_price: current, price_change_amount: change } = value;
  if (previous == null || current == null || change == null) {
    return <div className="mt-1 text-[10px] font-normal text-slate-500">Previous price unavailable</div>;
  }
  return (
    <div className="mt-1 space-y-0.5 text-[10px] font-normal tabular-nums">
      <div className="text-slate-500">{value.comparison_source === "estimated" ? "Est. previous" : "Previous"}: {formatPrice(previous)} → {formatPrice(current)}</div>
      <div className={change > 0 ? "text-emerald-700" : change < 0 ? "text-rose-700" : "text-slate-500"}>
        {change > 0 ? "+" : ""}{formatPrice(change)} ({period})
        {(value.comparison_source === "history" || value.comparison_source === "pokemonpricetracker_history") && <span className="text-slate-500"> · Historical prices</span>}
      </div>
    </div>
  );
}
