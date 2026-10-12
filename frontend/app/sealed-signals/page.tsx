import type { Metadata } from "next";
import { Suspense } from "react";
import { SealedSignalsDashboard } from "@/components/sealed-signals-dashboard";
import { getSealedSignals } from "@/lib/api";
import type { SealedSignalsResponse } from "@/types/card";
import SealedSignalsLoading from "./loading";

export const dynamic = "force-dynamic";
export const runtime = "edge";
export const metadata: Metadata = {
  title: "Sealed Product Returns — Newer & Vintage | CardboardDex",
  description: "Compare sealed Pokémon products by 30-day price growth, with separate rankings for newer releases and older or vintage sets.",
};

export default async function SealedSignalsPage() {
  const eras = ["newer", "older"] as const;
  const results = await Promise.allSettled(eras.map((era) => getSealedSignals({ era, sortBy: "momentum_desc", perPage: 12 })));
  const initialData: Record<typeof eras[number], SealedSignalsResponse | null> = { newer: null, older: null };
  results.forEach((result, index) => {
    if (result.status === "fulfilled") initialData[eras[index]] = result.value;
    else console.error(`Failed fetching initial ${eras[index]} sealed rankings:`, result.reason);
  });
  return (
    <main className="min-h-[calc(100vh-65px)] bg-white text-slate-950">
      <Suspense fallback={<SealedSignalsLoading />}>
        <SealedSignalsDashboard initialData={initialData} />
      </Suspense>
    </main>
  );
}
