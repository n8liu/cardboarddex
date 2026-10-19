import type { Metadata } from "next";
import { LiveUpdatesDashboard } from "@/components/live-updates-dashboard";
import type { LiveFeedResponse } from "@/types/card";

export const metadata: Metadata = {
  title: "Live Updated Items & Market Comps | CardboardDex",
  description: "Streaming real-time feed of Pokémon card market updates, matched eBay asking listings, graded aggregates, and PPT market updates.",
};

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default function LiveUpdatesPage() {
  const initialData: LiveFeedResponse = {
    page: 1,
    per_page: 24,
    has_more: false,
    items: [],
    updated_at: new Date().toISOString(),
  };


  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <LiveUpdatesDashboard initialData={initialData} />
    </main>
  );
}
