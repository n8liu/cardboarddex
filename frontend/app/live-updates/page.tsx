import type { Metadata } from "next";
import { getLiveUpdates } from "@/lib/api";
import { LiveUpdatesDashboard } from "@/components/live-updates-dashboard";

export const metadata: Metadata = {
  title: "Live Updated Items & Market Comps | CardboardDex",
  description: "Streaming real-time feed of verified Pokémon card market comps, eBay sold listings, graded slab submissions, and TCG API price syncs.",
};

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function LiveUpdatesPage() {
  const initialData = await getLiveUpdates({ page: 1, perPage: 24 });

  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <LiveUpdatesDashboard initialData={initialData} />
    </main>
  );
}
