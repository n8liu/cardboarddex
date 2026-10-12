import type { Metadata } from "next";
import { LandingPage } from "@/components/landing-page";

export const metadata: Metadata = {
  title: "CardboardDex - Pokémon Card Price Tracker & Market Analytics",
  description:
    "Discover English and Japanese Pokémon cards, compare market prices, explore new sets, and organize your collection with CardboardDex.",
};

export default function HomePage() {
  return (
    <main>
      <LandingPage />
    </main>
  );
}

