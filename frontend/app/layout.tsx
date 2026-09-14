import type { Metadata } from "next";

import { CommandPalette } from "@/components/command-palette-lazy";
import { NavHeader } from "@/components/nav-header";
import { CurrencyProvider } from "@/context/currency-context";
import { BinderProvider } from "@/context/binder-context";
import "./globals.css";


export const metadata: Metadata = {
  title: "CardboardDex - Pokémon Card Price Tracker & Market Analytics",
  description: "Pokémon card catalog and market analytics powered by TCG API and verified eBay listings.",
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
        <link rel="preconnect" href="https://ca-72b07140e03c4335a2d28f0e1c81f161.ecs.us-west-2.on.aws" />
        <link rel="dns-prefetch" href="https://ca-72b07140e03c4335a2d28f0e1c81f161.ecs.us-west-2.on.aws" />
        <link rel="preconnect" href="https://product-images.tcgplayer.com" />
        <link rel="dns-prefetch" href="https://product-images.tcgplayer.com" />
        <link rel="preconnect" href="https://raw.githubusercontent.com" />
        <link rel="dns-prefetch" href="https://raw.githubusercontent.com" />
      </head>
      <body suppressHydrationWarning>
        <CurrencyProvider>
          <BinderProvider>
            <CommandPalette />
            <NavHeader />
            {children}
            <footer className="border-t border-slate-200 bg-white">
              <div className="mx-auto max-w-[1600px] px-5 py-8 text-xs text-slate-500 sm:px-8">
                Pokémon catalog and market pricing via TCG API. Sold-market analytics via verified eBay listings.
              </div>
            </footer>
          </BinderProvider>
        </CurrencyProvider>
      </body>
    </html>
  );
}
