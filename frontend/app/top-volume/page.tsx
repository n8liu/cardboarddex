import type { Metadata } from "next";
import { getTrendingDashboard } from "@/lib/api";
import { TopVolumeDashboard } from "@/components/top-volume-dashboard";

export const metadata: Metadata = {
  title: "Top 50 Trending Cards & Pokémon | CardboardDex",
  description: "Live rankings across three core market pillars: trending & most clicked cards, most searched Pokémon characters, and market leaders by sales dollar volume.",
};

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function TopVolumePage() {
  const initialData = await getTrendingDashboard({ timeframe: "7d" });

  return (
    <main className="min-h-[calc(100vh-65px)] bg-white text-slate-950">
      <TopVolumeDashboard initialData={initialData} />
    </main>
  );
}
