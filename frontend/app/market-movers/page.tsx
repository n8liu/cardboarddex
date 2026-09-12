import type { Metadata } from "next";
import { Suspense } from "react";

import { MarketMoversDashboard } from "@/components/market-movers-dashboard";
import { getMarketMovers } from "@/lib/api";
import type { MarketMoversResponse } from "@/types/card";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export const metadata: Metadata = {
  title: "Market Movers - Pokémon Card Price Gainers & Drops | CardboardDex",
  description: "Track live Pokémon card price gainers and price drops across 24-hour, 7-day, and 30-day timeframes.",
};

export default async function MarketMoversPage() {
  let initialData: MarketMoversResponse = {
    period: "24h",
    direction: "all",
    page: 1,
    per_page: 24,
    total_gainers: 0,
    total_losers: 0,
    total_pages: 1,
    gainers: [],
    losers: [],
    updated_at: new Date().toISOString(),
  };

  try {
    initialData = await getMarketMovers({
      direction: "all",
      period: "24h",
      page: 1,
      perPage: 24,
    });
  } catch (err) {
    console.error("Failed fetching initial market movers:", err);
  }

  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <Suspense fallback={null}>
        <MarketMoversDashboard initialData={initialData} />
      </Suspense>
    </main>
  );
}
