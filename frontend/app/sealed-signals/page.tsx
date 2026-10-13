import type { Metadata } from "next";
import { Suspense } from "react";
import { SealedSignalsDashboard } from "@/components/sealed-signals-dashboard";
import SealedSignalsLoading from "./loading";

export const dynamic = "force-dynamic";
export const runtime = "edge";
export const metadata: Metadata = {
  title: "Sealed Product Returns — Newer & Vintage | CardboardDex",
  description: "Compare sealed Pokémon products by 30-day price growth, with separate rankings for newer releases and older or vintage sets.",
};

export default function SealedSignalsPage() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-white text-slate-950">
      <Suspense fallback={<SealedSignalsLoading />}>
        <SealedSignalsDashboard initialData={{ newer: null, older: null }} />
      </Suspense>
    </main>
  );
}
