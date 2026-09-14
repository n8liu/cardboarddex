import type { Metadata } from "next";
import { Suspense } from "react";
import { BinderPageView } from "@/components/binder/binder-page-view";

export const runtime = "edge";

export const metadata: Metadata = {
  title: "Portfolio Binder | CardboardDex",
  description:
    "Personal Pokémon card collection portfolio binder stored locally with real-time market values, 9-pocket sleeves, and portfolio valuation trends over time.",
};

export default function BinderPage() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <Suspense fallback={null}>
        <BinderPageView />
      </Suspense>
    </main>
  );
}
