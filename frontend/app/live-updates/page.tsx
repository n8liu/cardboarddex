import type { Metadata } from "next";
import { getLiveUpdates } from "@/lib/api";
import { LiveUpdatesDashboard } from "@/components/live-updates-dashboard";
import type { LiveUpdatesResponse } from "@/types/card";

export const metadata: Metadata = {
  title: "Live Updated Items & Market Comps | CardboardDex",
  description: "Streaming real-time feed of verified Pokémon card market comps, eBay sold listings, graded slab submissions, and TCG API price syncs.",
};

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function LiveUpdatesPage() {
  let initialData: LiveUpdatesResponse = {
    page: 1,
    per_page: 24,
    total_items: 0,
    total_pages: 1,
    provider_filter: "all",
    grade_filter: "all",
    total_ebay_updates: 0,
    total_tcg_updates: 0,
    graded_updates_count: 0,
    items: [],
    updated_at: new Date().toISOString(),
  };

  try {
    initialData = await getLiveUpdates({ page: 1, perPage: 24 });
  } catch (err) {
    console.error("Failed fetching initial live updates:", err);
  }

  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <LiveUpdatesDashboard initialData={initialData} />
    </main>
  );
}
