"use client";

import Image from "@/components/card-image";
import Link from "next/link";
import { FEATURED_POKEMON } from "@/lib/featured-pokemon";
import { TYPE_THEMES, formatDexNumber } from "@/lib/pokeapi";
import { SearchAutocomplete } from "@/components/search-autocomplete";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { openCommandPalette } from "@/components/command-palette";
import type { PokemonType } from "@/types/pokemon";

const POPULAR_SEARCH_CHIPS = [
  "Charizard",
  "Pikachu",
  "Gengar",
  "Umbreon",
  "Mewtwo",
  "151",
  "Evolving Skies",
  "Crown Zenith",
];

interface PlatformStatItem {
  numericValue?: number;
  displaySuffix?: string;
  isText?: boolean;
  textValue?: string;
  label: string;
  detail: string;
}

const PLATFORM_STATS: PlatformStatItem[] = [
  {
    numericValue: 54682,
    displaySuffix: "+",
    label: "Cards Cataloged",
    detail: "English & Japanese expansions",
  },
  {
    numericValue: 484,
    displaySuffix: "",
    label: "Sets Synchronized",
    detail: "234 English · 250 Japanese",
  },
  {
    numericValue: 1025,
    displaySuffix: "",
    label: "Pokédex Species",
    detail: "Generations I through IX",
  },
  {
    numericValue: 66500,
    displaySuffix: "+",
    label: "Active Market Prices",
    detail: "Per-printing observations & comps",
  },
  {
    isText: true,
    textValue: "15-Min",
    label: "Refresh Cadence",
    detail: "Alternating TCG API & eBay cycles",
  },
];

const CORE_MODULES = [
  {
    badge: "POKÉDEX BROWSER",
    title: "National Pokédex",
    href: "/pokedex",
    description:
      "Official canonical reference for all 1,025 Pokémon across 9 generations. Includes high-res official artwork, BST base stat meters, authentic audio cries, and direct trading card market comps.",
    metrics: ["1,025 Species", "Gen I–IX", "Interactive Cries"],
    cta: "Explore Pokédex",
  },
  {
    badge: "EXPANSION CATALOG",
    title: "Card Catalog",
    href: "/catalog",
    description:
      "Comprehensive database of 54,680+ Pokémon cards across 484 expansions. Filter by English or Japanese printings, chronological release, price sorting, and view live buylist & shipping benchmarks.",
    metrics: ["484 Sets", "English & Japanese", "Live Set Totals"],
    cta: "Browse Catalog",
  },
  {
    badge: "MOMENTUM RADAR",
    title: "Market Movers",
    href: "/market-movers",
    description:
      "Identify the top gaining and losing cards across 24-hour, 7-day, and 30-day velocity windows. Powered by automated stale-while-revalidate caching and multi-pass database delta fallbacks.",
    metrics: ["24h / 7d / 30d", "Gainers & Losers", "Trader Table View"],
    cta: "Track Movers",
  },
  {
    badge: "ARBITRAGE CALCULATOR",
    title: "Grading Profitability",
    href: "/grading-profit",
    description:
      "Analyze spreads and expected net profits between raw cards and PSA 10 / PSA 9 slabs across 165+ verified pairs. Includes live custom grading fee slider and PSA Value tier presets.",
    metrics: ["PSA 10 & 9 Spreads", "Custom Fee Slider", "Spread Multipliers"],
    cta: "Calculate Arbitrage",
  },
  {
    badge: "INVESTMENT SIGNALS",
    title: "Sealed Signals",
    href: "/sealed-signals",
    description:
      "Invest with data, not opinions. Deterministic 4-factor scoring model assessing supply scarcity, buylist liquidity, price velocity, and out-of-print vintage age across booster boxes and packs.",
    metrics: ["4-Factor Algorithm", "Quantitative Signals", "Scarcity Scoring"],
    cta: "Analyze Sealed",
  },
  {
    badge: "VOLUME & TICKER",
    title: "Top 50 & Live Comps",
    href: "/top-volume",
    description:
      "Leaderboard ranking top Pokémon characters by aggregate observed market volume, paired with a real-time stream of verified eBay sales and PSA/BGS/CGC/SGC graded slab observations.",
    metrics: ["Top 50 Characters", "Real-Time Comps", "Side-by-Side View"],
    cta: "View Volume & Comps",
  },
];

const METHODOLOGY_ITEMS = [
  {
    source: "PokéAPI Canonical Reference",
    tag: "Species Intelligence",
    description:
      "Provides species identifiers, generational regions, canonical English and Japanese naming, BST combat distributions, and official Nintendo audio cries.",
  },
  {
    source: "TCG API Pricing Engine",
    tag: "Market Foundation",
    description:
      "Captures canonical sets, card numbers, and 10 real-time price attributes per printing (market, low, median, lowest w/ shipping, buylist, and momentum).",
  },
  {
    source: "eBay Verified Comp Ingestion",
    tag: "Secondary Market",
    description:
      "Applies conservative word-boundary matching in backend/parsers/title_matcher.py, strictly rejecting proxies, fakes, and lots to deliver authentic real-world sales.",
  },
];

export function LandingPage() {
  const featuredPokemon = FEATURED_POKEMON;

  return (
    <div className="min-h-screen bg-[#f7f8f6] text-slate-950 font-mono">
      {/* 1. HERO SECTION */}
      <section className="relative overflow-hidden border-b border-slate-200/80 bg-white px-4 pt-12 pb-16 sm:px-6 lg:px-8">
        {/* Subtle Ambient Radial Mesh Glow */}
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-[550px] w-[550px] rounded-full opacity-20 blur-3xl animate-pulse-slow"
          style={{
            background:
              "radial-gradient(circle, rgba(16, 185, 129, 0.45) 0%, rgba(56, 189, 248, 0.25) 50%, transparent 80%)",
          }}
          aria-hidden="true"
        />

        <div className="relative mx-auto max-w-[1400px]">
          {/* Status Badge */}
          <div className="flex items-center gap-2 mb-6">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>LIVE DATA ENGINE ACTIVE</span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-500">TCG API + EBAY COMPS</span>
            </span>
          </div>

          {/* Headline */}
          <h1 className="text-3xl font-black tracking-tight text-slate-950 sm:text-5xl lg:text-6xl leading-[1.1]">
            CARD MARKET INTELLIGENCE &amp; NATIONAL POKÉDEX
          </h1>

          {/* Subtitle */}
          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-slate-600 sm:text-base">
            The high-precision Pokémon trading card price tracker. Tracking{" "}
            <span className="font-semibold text-slate-900">54,680+ cards</span> across{" "}
            <span className="font-semibold text-slate-900">484 English &amp; Japanese expansions</span>
            , real-time TCG market pricing, PSA 10/9 grading spreads, and verified eBay comps.
          </p>

          {/* Search Bar with Live Autocomplete Dropdown */}
          <div className="mt-8 max-w-2xl">
            <SearchAutocomplete />

            {/* Popular Search Chips */}
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Popular:
              </span>
              {POPULAR_SEARCH_CHIPS.map((chip) => (
                <Link
                  key={chip}
                  href={`/catalog?q=${encodeURIComponent(chip)}`}
                  className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
                >
                  {chip}
                </Link>
              ))}
            </div>
          </div>

          {/* Hero Quick Action Buttons */}
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/pokedex"
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-xs font-bold text-white shadow-xs transition hover:bg-slate-800 hover:shadow-md active:scale-95"
            >
              <span>EXPLORE POKÉDEX</span>
              <span>→</span>
            </Link>
            <Link
              href="/catalog"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 active:scale-95"
            >
              <span>BROWSE CARD CATALOG</span>
              <span>→</span>
            </Link>
            <button
              type="button"
              onClick={() => openCommandPalette()}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs font-bold text-slate-600 shadow-2xs transition hover:border-slate-300 hover:bg-white hover:text-slate-900 active:scale-95"
            >
              <svg className="h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span>COMMAND PALETTE</span>
              <kbd className="rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[10px] font-bold text-slate-500 shadow-xs">
                ⌘K
              </kbd>
            </button>
          </div>
        </div>
      </section>

      {/* 2. TELEMETRY & SYSTEM METRICS BAR WITH ROLLING NUMBERS */}
      <section className="border-b border-slate-200/80 bg-slate-50/70 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1400px]">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {PLATFORM_STATS.map((stat) => (
              <div
                key={stat.label}
                className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs transition hover:border-slate-300"
              >
                <div className="text-xl sm:text-2xl font-black tracking-tight text-slate-950 font-mono">
                  {stat.numericValue !== undefined ? (
                    <>
                      <AnimatedNumber
                        value={stat.numericValue}
                        duration={600}
                        format={(v) => Math.round(v).toLocaleString()}
                      />
                      {stat.displaySuffix}
                    </>
                  ) : (
                    stat.textValue
                  )}
                </div>
                <div className="mt-1 text-xs font-bold text-slate-800 uppercase tracking-wider">
                  {stat.label}
                </div>
                <div className="mt-0.5 text-[11px] text-slate-500">
                  {stat.detail}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3. CORE INTELLIGENCE SUITE (FEATURE MODULES) */}
      <section className="px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1400px]">
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between mb-8 pb-4 border-b border-slate-200">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                PLATFORM MODULES
              </p>
              <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">
                Comprehensive Market Intelligence
              </h2>
            </div>
            <p className="mt-2 sm:mt-0 text-xs text-slate-500 max-w-md">
              Six specialized analytics tools designed for collectors, investors, and Pokédex explorers.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {CORE_MODULES.map((module) => (
              <Link
                key={module.title}
                href={module.href}
                className="group flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-6 shadow-2xs transition-all duration-300 hover:-translate-y-1 hover:border-slate-300 hover:shadow-lg"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-bold tracking-wider text-slate-700">
                      {module.badge}
                    </span>
                    <span className="text-slate-400 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-slate-900">
                      →
                    </span>
                  </div>

                  <h3 className="mt-4 text-lg font-black tracking-tight text-slate-950 group-hover:text-slate-900">
                    {module.title}
                  </h3>

                  <p className="mt-2 text-xs leading-relaxed text-slate-600">
                    {module.description}
                  </p>
                </div>

                <div className="mt-6 pt-4 border-t border-slate-100">
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {module.metrics.map((m) => (
                      <span
                        key={m}
                        className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600"
                      >
                        {m}
                      </span>
                    ))}
                  </div>

                  <span className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-900 group-hover:underline">
                    <span>{module.cta}</span>
                    <span>→</span>
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* 4. CANONICAL POKÉDEX SHOWCASE WITH AMBIENT GLOW PODIUMS */}
      <section className="border-t border-slate-200/80 bg-white px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1400px]">
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between mb-8 pb-4 border-b border-slate-200">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                POKÉDEX EXPLORATION
              </p>
              <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">
                Featured Species Profiles
              </h2>
            </div>
            <Link
              href="/pokedex"
              className="mt-3 sm:mt-0 inline-flex items-center gap-1.5 text-xs font-bold text-slate-700 hover:text-slate-950"
            >
              <span>View All 1,025 Pokémon</span>
              <span>→</span>
            </Link>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            {featuredPokemon.map((pokemon) => {
              if (!pokemon) return null;
              const primaryType = pokemon.types[0] as PokemonType;
              const typeTheme = TYPE_THEMES[primaryType] ?? TYPE_THEMES.normal;

              return (
                <Link
                  key={pokemon.id}
                  href={`/pokemon/${pokemon.id}`}
                  prefetch={false}
                  className="group flex flex-col items-center rounded-2xl border border-slate-200/90 bg-white p-3.5 text-center shadow-xs transition-all duration-300 hover:-translate-y-1 hover:border-slate-300 hover:shadow-md"
                >
                  <div
                    className="relative flex h-20 w-20 items-center justify-center rounded-xl p-1.5 transition-transform duration-300 group-hover:scale-110"
                    style={{
                      background: `radial-gradient(circle, ${typeTheme.glow} 0%, rgba(255,255,255,0) 70%)`,
                    }}
                  >
                    <Image
                      src={pokemon.artwork}
                      alt={pokemon.name}
                      width={76}
                      height={76}
                      className="object-contain drop-shadow-sm"
                      unoptimized
                    />
                  </div>
                  <span className="mt-2 text-[10px] font-mono font-bold text-slate-400">
                    {formatDexNumber(pokemon.id)}
                  </span>
                  <span className="text-xs font-black text-slate-950 truncate max-w-full group-hover:text-emerald-700 transition">
                    {pokemon.name}
                  </span>
                  <div className="mt-1 flex gap-1">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${typeTheme.badge}`}
                    >
                      {primaryType}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      {/* 5. METHODOLOGY & DATA INTEGRITY */}
      <section className="border-t border-slate-200/80 bg-[#f7f8f6] px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1400px]">
          <div className="mb-8 pb-4 border-b border-slate-200">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
              DATA ARCHITECTURE
            </p>
            <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">
              Engineered for Accuracy
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              How CardboardDex integrates canonical species data with real-time market trading benchmarks.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {METHODOLOGY_ITEMS.map((item) => (
              <div
                key={item.source}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black text-slate-950">
                    {item.source}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                    {item.tag}
                  </span>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-slate-600">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 6. CALL TO ACTION STRIP */}
      <section className="border-t border-slate-200/80 bg-slate-900 px-4 py-12 sm:px-6 lg:px-8 text-white">
        <div className="mx-auto max-w-[1400px] flex flex-col md:flex-row items-center justify-between gap-6">
          <div>
            <h3 className="text-xl font-black tracking-tight">
              Ready to explore CardboardDex?
            </h3>
            <p className="mt-1 text-xs text-slate-300">
              Start browsing 1,025 species or jump straight into 54,680+ trading card market comps.
            </p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Link
              href="/pokedex"
              className="rounded-xl bg-white px-5 py-3 text-xs font-bold text-slate-900 shadow-xs transition hover:bg-slate-100 active:scale-95"
            >
              OPEN POKÉDEX
            </Link>
            <Link
              href="/catalog"
              className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-3 text-xs font-bold text-white shadow-xs transition hover:bg-slate-700 active:scale-95"
            >
              SEARCH CATALOG
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
