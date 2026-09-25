"use client";

import Image from "@/components/card-image";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { useCurrency } from "@/context/currency-context";
import { cardImageUrl, getTrendingDashboard } from "@/lib/api";
import { shimmerBlurDataUrl } from "@/lib/shimmer";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { SearchInput } from "@/components/ui/search-input";
import { getPokemonByIdOrSlug } from "@/lib/pokedex-data";
import type {
  PokemonVolumeItem,
  TrendingCardItem,
  TrendingDashboardResponse,
  TrendingPokemonItem,
  VolumeTimeframe,
} from "@/types/card";

type TopVolumeDashboardProps = {
  initialData: TrendingDashboardResponse;
};

type ViewMode = "overview" | "cards" | "pokemon" | "volume";

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatRank(rank: number): string {
  return rank < 10 ? `#0${rank}` : `#${rank}`;
}

// ---------------------------------------------------------------------------
// Row Component: Trending Card
// ---------------------------------------------------------------------------
function CardRow({ item }: { item: TrendingCardItem }) {
  const { formatPrice } = useCurrency();
  const isRank1 = item.rank === 1;
  const isRank2 = item.rank === 2;
  const isRank3 = item.rank === 3;

  return (
    <Link
      href={`/cards/${encodeURIComponent(item.card_id)}?ref=trending`}
      prefetch={false}
      className="card-cv group flex h-[62px] items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-white px-3 transition duration-150 hover:border-slate-400 hover:bg-slate-50/70"
    >
      {/* Left: Rank, Thumbnail, Card Title & Set */}
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <span
          className={`w-7 shrink-0 font-mono text-xs font-bold text-center ${
            isRank1
              ? "text-amber-700 bg-amber-50 rounded px-1 py-0.5 border border-amber-200/60"
              : isRank2
              ? "text-slate-700 bg-slate-100 rounded px-1 py-0.5 border border-slate-200"
              : isRank3
              ? "text-amber-900 bg-amber-50/60 rounded px-1 py-0.5 border border-amber-200/40"
              : "text-slate-400"
          }`}
        >
          {formatRank(item.rank)}
        </span>

        {/* Card Thumbnail - standardized 40x40 container */}
        <div className="relative h-10 w-10 shrink-0 flex items-center justify-center rounded-lg border border-slate-100 bg-slate-50 overflow-hidden">
          <div className="relative h-9 w-6.5">
            <Image
              src={cardImageUrl(item.image_url)}
              alt={item.name}
              fill
              className="object-contain transition duration-150 group-hover:scale-105"
              placeholder="blur"
              blurDataURL={shimmerBlurDataUrl(64, 90)}
              sizes="32px"
            />
          </div>
        </div>

        {/* Card Title & Meta */}
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-slate-900 group-hover:text-slate-950 sm:text-sm">
            {item.name}
          </p>
          <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px] text-slate-500 truncate">
            <span className="truncate max-w-[140px] sm:max-w-[180px]">{item.set_name}</span>
            {item.number && (
              <>
                <span className="text-slate-300">•</span>
                <span className="shrink-0">#{item.number}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Right: Price & Heat */}
      <div className="w-28 shrink-0 text-right font-mono">
        <div className="truncate text-xs font-bold text-slate-950 sm:text-sm">
          {formatPrice(item.market_price)}
        </div>
        <div className="mt-0.5 truncate text-[10px] font-medium">
          {item.clicks_count > 0 ? (
            <span className="text-slate-700 font-semibold">{item.clicks_count} clicks</span>
          ) : item.price_change_7d !== null && item.price_change_7d !== undefined ? (
            <span className={item.price_change_7d >= 0 ? "text-emerald-700" : "text-rose-700"}>
              {item.price_change_7d >= 0 ? "+" : ""}
              {item.price_change_7d.toFixed(1)}% (7d)
            </span>
          ) : (
            <span className="text-slate-400">active comp</span>
          )}
        </div>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Row Component: Popular Pokémon
// ---------------------------------------------------------------------------
function PokemonRow({ item }: { item: TrendingPokemonItem }) {
  const isRank1 = item.rank === 1;
  const isRank2 = item.rank === 2;
  const isRank3 = item.rank === 3;
  const pokeData = getPokemonByIdOrSlug(item.dex_number > 0 ? item.dex_number : item.pokemon_name);
  const dexNumber = pokeData?.id ?? item.dex_number;
  const spriteUrl = pokeData?.artwork || pokeData?.sprite || (item.dex_number > 0 ? item.sprite_url : "");
  const pokemonHref = `/pokemon/${dexNumber || item.pokemon_name.toLowerCase()}?ref=trending`;

  return (
    <Link
      href={pokemonHref}
      prefetch={false}
      className="group flex h-[62px] items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-white px-3 transition duration-150 hover:border-slate-400 hover:bg-slate-50/70"
    >
      {/* Left: Rank, Sprite, Pokémon Name & Dex */}
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <span
          className={`w-7 shrink-0 font-mono text-xs font-bold text-center ${
            isRank1
              ? "text-amber-700 bg-amber-50 rounded px-1 py-0.5 border border-amber-200/60"
              : isRank2
              ? "text-slate-700 bg-slate-100 rounded px-1 py-0.5 border border-slate-200"
              : isRank3
              ? "text-amber-900 bg-amber-50/60 rounded px-1 py-0.5 border border-amber-200/40"
              : "text-slate-400"
          }`}
        >
          {formatRank(item.rank)}
        </span>

        {/* Artwork Sprite - standardized 40x40 container */}
        <div className="relative h-10 w-10 shrink-0 flex items-center justify-center rounded-lg border border-slate-100 bg-slate-50/60 overflow-hidden">
          {spriteUrl ? (
            <Image
              src={spriteUrl}
              alt={item.pokemon_name}
              fill
              className="object-contain p-0.5 transition duration-150 group-hover:scale-110"
              sizes="40px"
              unoptimized
            />
          ) : (
            <span className="font-mono text-xs font-bold text-slate-400">
              {item.pokemon_name.slice(0, 2).toUpperCase()}
            </span>
          )}
        </div>

        {/* Pokémon Name & Details */}
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-slate-950 group-hover:text-slate-900 sm:text-sm">
            {item.pokemon_name}
          </p>
          <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px] text-slate-500 truncate">
            <span className="shrink-0">#{String(dexNumber).padStart(4, "0")}</span>
            {item.cards_count > 0 && (
              <>
                <span className="text-slate-300">•</span>
                <span className="truncate">{item.cards_count} cards</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Right: Popularity Score & Top Comp */}
      <div className="w-28 shrink-0 text-right font-mono">
        <div className="truncate text-xs font-bold text-slate-950 sm:text-sm">
          {item.trend_score.toFixed(0)} <span className="text-[10px] text-slate-400 font-normal">pts</span>
        </div>
        <div className="mt-0.5 truncate text-[10px] text-slate-500">
          {item.clicks_count > 0 ? (
            <span className="text-slate-700 font-semibold">{item.clicks_count} clicks</span>
          ) : item.searches_count > 0 ? (
            <span>{item.searches_count} searches</span>
          ) : item.top_card_price ? (
            `Top: $${item.top_card_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
          ) : (
            `${item.cards_count} cards`
          )}
        </div>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Row Component: Volume Leader
// ---------------------------------------------------------------------------
function VolumeRow({ item }: { item: PokemonVolumeItem }) {
  const isRank1 = item.rank === 1;
  const isRank2 = item.rank === 2;
  const isRank3 = item.rank === 3;
  const isUp = item.momentum_trend === "up" || item.yoy_trend === "up";
  const isDown = item.momentum_trend === "down" || item.yoy_trend === "down";
  const pct = item.momentum_percentage || item.yoy_percentage || 0;
  const pokeData = getPokemonByIdOrSlug(item.dex_number > 0 ? item.dex_number : item.pokemon_name);
  const dexNumber = pokeData?.id ?? item.dex_number;
  const spriteUrl = pokeData?.artwork || pokeData?.sprite || (item.dex_number > 0 ? item.sprite_url : "");
  const pokemonHref = `/pokemon/${dexNumber || item.pokemon_name.toLowerCase()}?ref=trending`;

  return (
    <Link
      href={pokemonHref}
      prefetch={false}
      className="group flex h-[62px] items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-white px-3 transition duration-150 hover:border-slate-400 hover:bg-slate-50/70"
    >
      {/* Left: Rank, Sprite, Pokémon Name & Dex */}
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <span
          className={`w-7 shrink-0 font-mono text-xs font-bold text-center ${
            isRank1
              ? "text-amber-700 bg-amber-50 rounded px-1 py-0.5 border border-amber-200/60"
              : isRank2
              ? "text-slate-700 bg-slate-100 rounded px-1 py-0.5 border border-slate-200"
              : isRank3
              ? "text-amber-900 bg-amber-50/60 rounded px-1 py-0.5 border border-amber-200/40"
              : "text-slate-400"
          }`}
        >
          {formatRank(item.rank)}
        </span>

        {/* Artwork Sprite - standardized 40x40 container */}
        <div className="relative h-10 w-10 shrink-0 flex items-center justify-center rounded-lg border border-slate-100 bg-slate-50/60 overflow-hidden">
          {spriteUrl ? (
            <Image
              src={spriteUrl}
              alt={item.pokemon_name}
              fill
              className="object-contain p-0.5 transition duration-150 group-hover:scale-110"
              sizes="40px"
              unoptimized
            />
          ) : (
            <span className="font-mono text-xs font-bold text-slate-400">
              {item.pokemon_name.slice(0, 2).toUpperCase()}
            </span>
          )}
        </div>

        {/* Name & Dex */}
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-slate-950 group-hover:text-slate-900 sm:text-sm">
            {item.pokemon_name}
          </p>
          <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px] text-slate-500 truncate">
            <span className="shrink-0">#{String(dexNumber).padStart(4, "0")}</span>
            <span className="text-slate-300">•</span>
            <span className="truncate">{item.sales_count.toLocaleString()} comps</span>
          </div>
        </div>
      </div>

      {/* Right: Volume & Momentum/Comps */}
      <div className="w-28 shrink-0 text-right font-mono">
        <div className="truncate text-xs font-bold text-slate-950 sm:text-sm">
          {item.volume_formatted}
        </div>
        <div className="mt-0.5 flex items-center justify-end gap-1 text-[10px] font-medium truncate">
          <span
            className={
              isUp ? "text-emerald-700 font-semibold" : isDown ? "text-rose-700 font-semibold" : "text-slate-400"
            }
          >
            {isUp ? "▲" : isDown ? "▼" : "▬"}
            {pct !== 0 ? ` ${pct > 0 ? "+" : ""}${pct.toFixed(0)}%` : ""}
          </span>
          <span className="text-slate-300">·</span>
          <span className="text-slate-500 truncate">
            {item.sales_count >= 1000
              ? `${(item.sales_count / 1000).toFixed(1)}K`
              : item.sales_count}{" "}
            sales
          </span>
        </div>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------
export function TopVolumeDashboard({ initialData }: TopVolumeDashboardProps) {
  const { formatPrice, convertPrice, symbol } = useCurrency();
  const [data, setData] = useState<TrendingDashboardResponse>(initialData);
  const [timeframe, setTimeframe] = useState<VolumeTimeframe>("7d");
  const [viewMode, setViewMode] = useState<ViewMode>("overview");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const isInitialized = useRef(false);

  useEffect(() => {
    if (!isInitialized.current) {
      isInitialized.current = true;
      if (!initialData.trending_cards || initialData.trending_cards.length === 0) {
        setIsLoading(true);
        void getTrendingDashboard({ timeframe })
          .then(setData)
          .catch((err) => console.error("Failed fetching trending data on mount:", err))
          .finally(() => setIsLoading(false));
      }
    }
  }, [initialData.trending_cards, timeframe]);

  // Timeframe switch
  const handleTimeframeChange = async (newTf: VolumeTimeframe) => {
    setTimeframe(newTf);
    setIsLoading(true);
    try {
      const res = await getTrendingDashboard({
        timeframe: newTf,
        query: searchQuery.trim() || undefined,
      });
      setData(res);
    } catch (err) {
      console.error("Failed fetching trending data:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // Client search filtering
  const filteredCards = useMemo(() => {
    if (!searchQuery.trim()) return data.trending_cards;
    const q = searchQuery.toLowerCase().trim();
    return data.trending_cards.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.set_name.toLowerCase().includes(q) ||
        (c.number && c.number.toLowerCase().includes(q))
    );
  }, [data.trending_cards, searchQuery]);

  const filteredPokemon = useMemo(() => {
    if (!searchQuery.trim()) return data.trending_pokemon;
    const q = searchQuery.toLowerCase().trim();
    return data.trending_pokemon.filter(
      (p) =>
        p.pokemon_name.toLowerCase().includes(q) ||
        String(p.dex_number).includes(q)
    );
  }, [data.trending_pokemon, searchQuery]);

  const filteredVolume = useMemo(() => {
    if (!searchQuery.trim()) return data.volume_pokemon;
    const q = searchQuery.toLowerCase().trim();
    return data.volume_pokemon.filter(
      (v) =>
        v.pokemon_name.toLowerCase().includes(q) ||
        String(v.dex_number).includes(q)
    );
  }, [data.volume_pokemon, searchQuery]);

  // Dual column split helper
  const splitColumns = <T,>(items: T[]): [T[], T[]] => {
    const mid = Math.ceil(items.length / 2);
    return [items.slice(0, mid), items.slice(mid)];
  };

  const [cardsCol1, cardsCol2] = useMemo(() => splitColumns(filteredCards), [filteredCards]);
  const [pokeCol1, pokeCol2] = useMemo(() => splitColumns(filteredPokemon), [filteredPokemon]);
  const [volCol1, volCol2] = useMemo(() => splitColumns(filteredVolume), [filteredVolume]);

  // Top summary stats
  const topCard = data.trending_cards[0] || null;
  const topPokemon = data.trending_pokemon[0] || null;
  const topVolume = data.volume_pokemon[0] || null;

  const totalVolumeFormatted = useMemo(() => {
    const rawSum = data.total_volume_usd ?? 0;
    const sum = convertPrice(rawSum) ?? 0;
    if (sum >= 1_000_000_000) return `${symbol}${(sum / 1_000_000_000).toFixed(2)}B`;
    if (sum >= 1_000_000) return `${symbol}${(sum / 1_000_000).toFixed(2)}M`;
    if (sum >= 1_000) return `${symbol}${(sum / 1_000).toFixed(1)}K`;
    return `${symbol}${sum.toFixed(2)}`;
  }, [data.total_volume_usd, convertPrice, symbol]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-6 lg:px-8">
      {/* Header Section */}
      <section className="mb-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-mono font-medium text-slate-700">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              Live Market Activity · TCG &amp; eBay
            </div>

            <h1 className="text-3xl font-mono font-black tracking-tight text-slate-950 sm:text-4xl">
              Trending &amp; Top 50
            </h1>
            <p className="mt-1.5 max-w-2xl text-xs sm:text-sm font-mono text-slate-500 leading-relaxed">
              Track search velocity, click popularity, and market sales volume across cards and Pokémon species.
            </p>
          </div>

          {/* Header Stats Grid */}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 text-xs font-mono">
            {topCard && (
              <div className="rounded-xl border border-slate-200/80 bg-white p-3 shadow-2xs">
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Top Card</div>
                <div className="mt-0.5 truncate font-bold text-slate-950">{topCard.name}</div>
                <div className="text-[11px] text-slate-500">{formatPrice(topCard.market_price)}</div>
              </div>
            )}
            {topPokemon && (
              <div className="rounded-xl border border-slate-200/80 bg-white p-3 shadow-2xs">
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Top Pokémon</div>
                <div className="mt-0.5 truncate font-bold text-slate-950">{topPokemon.pokemon_name}</div>
                <div className="text-[11px] text-slate-500">#{topPokemon.dex_number}</div>
              </div>
            )}
            {topVolume && (
              <div className="rounded-xl border border-slate-200/80 bg-white p-3 shadow-2xs">
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Volume #1</div>
                <div className="mt-0.5 truncate font-bold text-slate-950">{topVolume.pokemon_name}</div>
                <div className="text-[11px] text-slate-500">{topVolume.volume_formatted}</div>
              </div>
            )}
            <div className="rounded-xl border border-slate-200/80 bg-white p-3 shadow-2xs">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Tracked ({timeframe})</div>
              <div className="mt-0.5 font-bold text-slate-950">
                <AnimatedNumber
                  value={convertPrice(data.total_volume_usd) ?? 0}
                  format={(val) => {
                    if (val >= 1_000_000_000) return `${symbol}${(val / 1_000_000_000).toFixed(2)}B`;
                    if (val >= 1_000_000) return `${symbol}${(val / 1_000_000).toFixed(2)}M`;
                    if (val >= 1_000) return `${symbol}${(val / 1_000).toFixed(1)}K`;
                    return `${symbol}${val.toFixed(2)}`;
                  }}
                />
              </div>
              <div className="text-[11px] text-slate-500">
                <AnimatedNumber value={data.total_sales_count || 0} /> comps
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Control Bar */}
      <div className="mb-6 rounded-2xl border border-slate-200/90 bg-white p-3 sm:p-3.5 shadow-2xs">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {/* Left: View Mode Category Switcher */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs font-mono">
              <button
                type="button"
                onClick={() => setViewMode("overview")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  viewMode === "overview"
                    ? "bg-slate-900 text-white shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950 hover:bg-slate-200/60"
                }`}
              >
                3-Column Overview
              </button>
              <button
                type="button"
                onClick={() => setViewMode("cards")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  viewMode === "cards"
                    ? "bg-slate-900 text-white shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950 hover:bg-slate-200/60"
                }`}
              >
                Trending Cards
              </button>
              <button
                type="button"
                onClick={() => setViewMode("pokemon")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  viewMode === "pokemon"
                    ? "bg-slate-900 text-white shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950 hover:bg-slate-200/60"
                }`}
              >
                Popular Pokémon
              </button>
              <button
                type="button"
                onClick={() => setViewMode("volume")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  viewMode === "volume"
                    ? "bg-slate-900 text-white shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950 hover:bg-slate-200/60"
                }`}
              >
                Volume Leaders
              </button>
            </div>

            {/* Timeframe selector */}
            <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs font-mono">
              <button
                type="button"
                onClick={() => handleTimeframeChange("24h")}
                className={`rounded-lg px-2.5 py-1.5 transition ${
                  timeframe === "24h"
                    ? "bg-white text-slate-950 shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950"
                }`}
              >
                24h
              </button>
              <button
                type="button"
                onClick={() => handleTimeframeChange("7d")}
                className={`rounded-lg px-2.5 py-1.5 transition ${
                  timeframe === "7d"
                    ? "bg-white text-slate-950 shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950"
                }`}
              >
                7d
              </button>
              <button
                type="button"
                onClick={() => handleTimeframeChange("30d")}
                className={`rounded-lg px-2.5 py-1.5 transition ${
                  timeframe === "30d"
                    ? "bg-white text-slate-950 shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950"
                }`}
              >
                30d
              </button>
              <button
                type="button"
                onClick={() => handleTimeframeChange("all_time")}
                className={`rounded-lg px-2.5 py-1.5 transition ${
                  timeframe === "all_time"
                    ? "bg-white text-slate-950 shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-950"
                }`}
              >
                All
              </button>
            </div>
          </div>

          {/* Right: Search Filter Input */}
          <div className="w-full sm:w-64">
            <SearchInput
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder="Filter list..."
            />
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, colIdx) => (
            <div key={colIdx} className="space-y-2">
              <div className="h-8 w-full animate-pulse rounded-xl bg-slate-100" />
              {Array.from({ length: 10 }).map((_, rowIdx) => (
                <div key={rowIdx} className="h-14 w-full animate-pulse rounded-xl bg-slate-100" />
              ))}
            </div>
          ))}
        </div>
      ) : viewMode === "overview" ? (
        /* ------------------------------------------------------------- */
        /* MODE 1: 3-Column Overview (Clean side-by-side leaderboard)     */
        /* ------------------------------------------------------------- */
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {/* Column 1: Trending Cards */}
          <div className="flex flex-col rounded-2xl border border-slate-200/90 bg-slate-50/50 p-3.5 sm:p-4 shadow-2xs">
            <div className="flex h-[42px] items-center justify-between border-b border-slate-200 pb-2.5 mb-3">
              <div>
                <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-slate-900 leading-tight">
                  Trending Cards
                </h2>
                <p className="font-mono text-[11px] text-slate-500 leading-tight">Most searched &amp; clicked</p>
              </div>
              <button
                type="button"
                onClick={() => setViewMode("cards")}
                className="shrink-0 font-mono text-[11px] font-semibold text-slate-600 hover:text-slate-950 hover:underline"
              >
                View 50 →
              </button>
            </div>

            <div className="space-y-2 flex-1">
              {filteredCards.slice(0, 15).map((card) => (
                <CardRow key={card.card_id} item={card} />
              ))}
              {filteredCards.length === 0 && (
                <div className="p-8 text-center font-mono text-xs text-slate-400">
                  No cards found matching “{searchQuery}”
                </div>
              )}
            </div>
          </div>

          {/* Column 2: Popular Pokémon */}
          <div className="flex flex-col rounded-2xl border border-slate-200/90 bg-slate-50/50 p-3.5 sm:p-4 shadow-2xs">
            <div className="flex h-[42px] items-center justify-between border-b border-slate-200 pb-2.5 mb-3">
              <div>
                <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-slate-900 leading-tight">
                  Popular Pokémon
                </h2>
                <p className="font-mono text-[11px] text-slate-500 leading-tight">Most viewed species</p>
              </div>
              <button
                type="button"
                onClick={() => setViewMode("pokemon")}
                className="shrink-0 font-mono text-[11px] font-semibold text-slate-600 hover:text-slate-950 hover:underline"
              >
                View 50 →
              </button>
            </div>

            <div className="space-y-2 flex-1">
              {filteredPokemon.slice(0, 15).map((poke) => (
                <PokemonRow key={poke.pokemon_name} item={poke} />
              ))}
              {filteredPokemon.length === 0 && (
                <div className="p-8 text-center font-mono text-xs text-slate-400">
                  No Pokémon found matching “{searchQuery}”
                </div>
              )}
            </div>
          </div>

          {/* Column 3: Volume Leaders */}
          <div className="flex flex-col rounded-2xl border border-slate-200/90 bg-slate-50/50 p-3.5 sm:p-4 shadow-2xs">
            <div className="flex h-[42px] items-center justify-between border-b border-slate-200 pb-2.5 mb-3">
              <div>
                <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-slate-900 leading-tight">
                  Volume Leaders
                </h2>
                <p className="font-mono text-[11px] text-slate-500 leading-tight">Sales volume ({timeframe.toUpperCase()})</p>
              </div>
              <button
                type="button"
                onClick={() => setViewMode("volume")}
                className="shrink-0 font-mono text-[11px] font-semibold text-slate-600 hover:text-slate-950 hover:underline"
              >
                View 50 →
              </button>
            </div>

            <div className="space-y-2 flex-1">
              {filteredVolume.slice(0, 15).map((item) => (
                <VolumeRow key={item.pokemon_name} item={item} />
              ))}
              {filteredVolume.length === 0 && (
                <div className="p-8 text-center font-mono text-xs text-slate-400">
                  No volume records found matching “{searchQuery}”
                </div>
              )}
            </div>
          </div>
        </div>
      ) : viewMode === "cards" ? (
        /* ------------------------------------------------------------- */
        /* MODE 2: Trending Cards (Dual Column: Rank 1-25 & 26-50)       */
        /* ------------------------------------------------------------- */
        <div className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-slate-600">
              Trending Cards ({filteredCards.length} Ranked)
            </span>
            <span className="font-mono text-[11px] text-slate-400">
              Ranked by search interest &amp; market comp liquidity
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              {cardsCol1.map((card) => (
                <CardRow key={card.card_id} item={card} />
              ))}
            </div>
            <div className="space-y-2">
              {cardsCol2.map((card) => (
                <CardRow key={card.card_id} item={card} />
              ))}
            </div>
          </div>
        </div>
      ) : viewMode === "pokemon" ? (
        /* ------------------------------------------------------------- */
        /* MODE 3: Popular Pokémon (Dual Column: Rank 1-25 & 26-50)      */
        /* ------------------------------------------------------------- */
        <div className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-slate-600">
              Popular Pokémon Species ({filteredPokemon.length} Ranked)
            </span>
            <span className="font-mono text-[11px] text-slate-400">
              Ranked by user search volume &amp; catalog views
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              {pokeCol1.map((poke) => (
                <PokemonRow key={poke.pokemon_name} item={poke} />
              ))}
            </div>
            <div className="space-y-2">
              {pokeCol2.map((poke) => (
                <PokemonRow key={poke.pokemon_name} item={poke} />
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* ------------------------------------------------------------- */
        /* MODE 4: Volume Leaders (Dual Column: Rank 1-25 & 26-50)       */
        /* ------------------------------------------------------------- */
        <div className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-slate-600">
              Top 50 Volume Leaders ({timeframe.toUpperCase()})
            </span>
            <span className="font-mono text-[11px] text-slate-400">
              Ranked by verified market sales volume
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              {volCol1.map((item) => (
                <VolumeRow key={item.pokemon_name} item={item} />
              ))}
            </div>
            <div className="space-y-2">
              {volCol2.map((item) => (
                <VolumeRow key={item.pokemon_name} item={item} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
