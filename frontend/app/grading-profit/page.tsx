import type { Metadata } from "next";
import { Suspense } from "react";

import { GradingProfitDashboard } from "@/components/grading-profit-dashboard";
import { getGradingProfit } from "@/lib/api";
import type { GradingProfitResponse } from "@/types/card";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export const metadata: Metadata = {
  title: "Grading Profitability - Pokémon Card Arbitrage & Spreads | CardboardDex",
  description: "Find the most profitable Pokémon cards to grade. Track real-time dollar spreads and ROI between raw market prices and PSA 10/PSA 9 comps.",
};

export default async function GradingProfitPage() {
  let initialData: GradingProfitResponse = {
    page: 1,
    per_page: 24,
    total_cards: 0,
    total_pages: 1,
    grading_fee: 24.99,
    sort_by: "psa10_profit_desc",
    items: [],
    updated_at: new Date().toISOString(),
  };

  try {
    initialData = await getGradingProfit({
      page: 1,
      perPage: 24,
      sortBy: "psa10_profit_desc",
    });
  } catch (err) {
    console.error("Failed fetching initial grading profit data:", err);
  }

  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <Suspense fallback={null}>
        <GradingProfitDashboard initialData={initialData} />
      </Suspense>
    </main>
  );
}
