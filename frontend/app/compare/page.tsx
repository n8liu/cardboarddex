import type { Metadata } from "next";
import { Suspense } from "react";

import { CompareDashboard } from "@/components/compare-dashboard";
import { SectionLoadingBar } from "@/components/section-loading-bar";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export const metadata: Metadata = {
  title: "Compare Pokémon Card Prices | CardboardDex",
  description: "Compare the market price history of up to four Pokémon cards on one chart.",
};

export default function ComparePage() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <Suspense fallback={<div className="mx-auto max-w-[1200px] px-4 pt-8"><SectionLoadingBar label="Loading comparison…" /></div>}>
        <CompareDashboard />
      </Suspense>
    </main>
  );
}
