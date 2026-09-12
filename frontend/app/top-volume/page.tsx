import type { Metadata } from "next";
import { getTrendingDashboard } from "@/lib/api";
import { TopVolumeDashboard } from "@/components/top-volume-dashboard";
import type { TrendingDashboardResponse } from "@/types/card";

export const metadata: Metadata = {
  title: "Top 50 Trending Cards & Pokémon | CardboardDex",
  description: "Live rankings across three core market pillars: trending & most clicked cards, most searched Pokémon characters, and market leaders by sales dollar volume.",
};

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function TopVolumePage() {
  let initialData: TrendingDashboardResponse = {
    timeframe: "7d",
    trending_cards: [],
    trending_pokemon: [],
    volume_pokemon: [],
    total_volume_usd: 0,
    total_sales_count: 0,
    updated_at: new Date().toISOString(),
  };

  try {
    initialData = await getTrendingDashboard({ timeframe: "7d" });
  } catch (err) {
    console.error("Failed fetching initial trending dashboard:", err);
  }

  return (
    <main className="min-h-[calc(100vh-65px)] bg-white text-slate-950">
      <TopVolumeDashboard initialData={initialData} />
    </main>
  );
}
