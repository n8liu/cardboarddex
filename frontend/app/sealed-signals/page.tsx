import type { Metadata } from "next";
import { Suspense } from "react";

import { SealedSignalsDashboard } from "@/components/sealed-signals-dashboard";
import { getSealedSignals } from "@/lib/api";
import type { SealedSignalsResponse } from "@/types/card";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export const metadata: Metadata = {
  title: "Sealed Investment Signals - 4-Factor Quantitative Model | CardboardDex",
  description: "Quantitative buy signals for sealed Pokémon TCG booster boxes, ETBs, bundles, and cases based on supply float, buylist liquidity, and momentum.",
};

export default async function SealedSignalsPage() {
  let initialData: SealedSignalsResponse = {
    page: 1,
    per_page: 24,
    total_items: 0,
    total_pages: 1,
    signal_filter: "all",
    product_type_filter: "all",
    sort_by: "score_desc",
    strong_buy_count: 0,
    buy_count: 0,
    hold_count: 0,
    underperform_count: 0,
    items: [],
    updated_at: new Date().toISOString(),
  };

  try {
    initialData = await getSealedSignals({
      signal: "all",
      productType: "all",
      sortBy: "score_desc",
      page: 1,
      perPage: 24,
    });
  } catch (err) {
    console.error("Failed fetching initial sealed investment signals:", err);
  }

  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <Suspense fallback={null}>
        <SealedSignalsDashboard initialData={initialData} />
      </Suspense>
    </main>
  );
}
