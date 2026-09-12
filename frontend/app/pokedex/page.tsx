import type { Metadata } from "next";
import { Suspense } from "react";
import { PokedexBrowser } from "@/components/pokedex-browser";

export const runtime = "edge";

export const metadata: Metadata = {
  title: "Pokédex | CardboardDex",
  description:
    "Explore all 1,025 Pokémon across 9 generations with official PokéAPI stats, artwork, and real-time Pokémon trading card market prices, PSA graded comps, and eBay sales.",
};

export default function PokedexPage() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <Suspense fallback={null}>
        <PokedexBrowser />
      </Suspense>
    </main>
  );
}
