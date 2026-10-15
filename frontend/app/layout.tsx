import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { AnalyticsTracker, AnalyticsPreference } from "@/components/analytics-tracker";

import { CommandPalette } from "@/components/command-palette-lazy";
import { NavHeader } from "@/components/nav-header";
import { CurrencyProvider } from "@/context/currency-context";
import { BinderProvider } from "@/context/binder-context";
import { MobileSearchFocus } from "@/components/mobile-search-focus";
import "./globals.css";


export const metadata: Metadata = {
  title: "CardboardDex - Pokémon Card Price Tracker & Market Analytics",
  description: "Pokémon card catalog and market analytics powered by TCG API and matched eBay listings.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,100;0,200;0,300;0,400;0,500;0,600;0,700;1,100;1,200;1,300;1,400;1,500;1,600;1,700&display=swap"
          rel="stylesheet"
        />
        {/* Performance Resource Hints */}
        <link rel="preconnect" href="https://api.cardboarddex.app" />
        <link rel="dns-prefetch" href="https://api.cardboarddex.app" />
        <link rel="preconnect" href="https://product-images.tcgplayer.com" />
        <link rel="dns-prefetch" href="https://product-images.tcgplayer.com" />
        <link rel="preconnect" href="https://raw.githubusercontent.com" />
        <link rel="dns-prefetch" href="https://raw.githubusercontent.com" />
      </head>
      <body suppressHydrationWarning>
        <Suspense fallback={null}><AnalyticsTracker /></Suspense>
        <CurrencyProvider>
          <BinderProvider>
            <CommandPalette />
            <NavHeader />
            <MobileSearchFocus />
            {children}
            <footer className="border-t border-slate-200 bg-white">
              <div className="mx-auto max-w-[1600px] px-5 py-8 text-xs text-slate-500 sm:px-8">
                <nav aria-label="Resources" className="mb-4 flex flex-wrap gap-5 font-semibold text-slate-700">
                  <Link href="/faq" className="hover:underline">FAQ & Guides</Link>
                  <Link href="/faq#calendar" className="hover:underline">Release calendar</Link>
                  <Link href="/faq/guides/pokemon-tcg-history" className="hover:underline">Pokémon TCG history</Link>
                </nav>
                Pokémon catalog and market pricing via TCG API. eBay comparisons use active listing prices, not completed sales.
                <AnalyticsPreference />
              </div>
            </footer>
          </BinderProvider>
        </CurrencyProvider>
      </body>
    </html>
  );
}
