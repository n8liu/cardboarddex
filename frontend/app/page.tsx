import type { Metadata } from "next";
import { LandingPage } from "@/components/landing-page";

export const metadata: Metadata = {
  title: "CardboardDex - Pokémon Card Price Tracker & Market Analytics",
  description:
    "Track 54,480+ Pokémon cards across 482 English & Japanese sets, real-time TCG market pricing, PSA 10/9 grading spreads, and official 1,025 species National Pokédex.",
};

export default function HomePage() {
  return (
    <main>
      <LandingPage />
    </main>
  );
}

