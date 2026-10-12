"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "@/components/card-image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { CardSort, CardSummary, GameLanguage } from "@/types/card";
import type { PokemonSetCount } from "@/types/pokemon";
import { cardImageUrl, getPokemonCards } from "@/lib/api";
import { EmptyState } from "@/components/ui/empty-state";
import { SearchInput } from "@/components/ui/search-input";
import { HoloCard } from "@/components/ui/holo-card";
import { useCurrency } from "@/context/currency-context";
import { isSealedProduct, summarizeDisplayedCards } from "@/lib/pokemon-card-summary";
import { shimmerBlurDataUrl } from "@/lib/shimmer";

type Props = {
  pokemonName: string;
  initialCards: CardSummary[];
  availableSets: PokemonSetCount[];
};

export function PokemonCardsView({
  pokemonName,
  initialCards,
  availableSets,
}: Props) {
  const searchParams = useSearchParams();
  const { formatPrice } = useCurrency();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const s = params.get("set")?.trim() ?? "";
    const sortRaw = params.get("sort") as CardSort;
    const validSorts: CardSort[] = ["price_desc", "price_asc", "number_asc", "number_desc", "name", "set"];
    const sort = validSorts.includes(sortRaw) ? sortRaw : "price_desc";
    const g = (params.get("game") as GameLanguage) || "all";
    const game: GameLanguage = ["all", "pokemon", "pokemon-japan"].includes(g) ? g : "all";
    const q = params.get("q")?.trim() ?? "";
    return { s, sort, game, q, hideSealed: params.get("hide_sealed") !== "false" };
  }, [searchParams]);

  const initialParams = getUrlParams();
  const [cards, setCards] = useState<CardSummary[]>(initialCards);
  const [sets, setSets] = useState(availableSets);
  const [hideSealed, setHideSealed] = useState(initialParams.hideSealed);
  const [selectedSet, setSelectedSet] = useState<string>(initialParams.s);
  const [sortBy, setSortBy] = useState<CardSort>(initialParams.sort);
  const [game, setGame] = useState<GameLanguage>(initialParams.game);
  const [searchFilter, setSearchFilter] = useState(initialParams.q);
  const [isLoading, setIsLoading] = useState(false);
  const firstFetch = useRef(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  // Sync browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const params = getUrlParams();
      setSelectedSet(params.s);
      setSortBy(params.sort);
      setGame(params.game);
      setSearchFilter(params.q);
      setHideSealed(params.hideSealed);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [getUrlParams]);

  // Keep local-only search and sealed visibility shareable, including browser navigation.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href);
      selectedSet ? url.searchParams.set("set", selectedSet) : url.searchParams.delete("set");
      sortBy !== "price_desc" ? url.searchParams.set("sort", sortBy) : url.searchParams.delete("sort");
      game !== "all" ? url.searchParams.set("game", game) : url.searchParams.delete("game");
      searchFilter.trim() ? url.searchParams.set("q", searchFilter.trim()) : url.searchParams.delete("q");
      hideSealed ? url.searchParams.delete("hide_sealed") : url.searchParams.set("hide_sealed", "false");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }, 150);
    return () => window.clearTimeout(timer);
  }, [selectedSet, sortBy, game, searchFilter, hideSealed]);

  // Fetch only for server-backed filters; summary/search/sealed changes stay local.
  useEffect(() => {
    if (firstFetch.current) {
      firstFetch.current = false;
      if (!selectedSet && sortBy === "price_desc" && game === "all" && initialCards.length > 0) return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError("");
    getPokemonCards(pokemonName, {
      setId: selectedSet || undefined, sortBy, game, limit: 100,
    }).then((result) => {
      if (!cancelled) { setCards(result.cards); setSets(result.available_sets); }
    }).catch((err) => {
      console.error("[PokemonCardsView] Error loading cards:", err);
      if (!cancelled) setError("Could not update cards. Showing the previous results.");
    }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [pokemonName, selectedSet, sortBy, game, retry, initialCards.length]);

  const filteredCards = useMemo(() => {
    const query = searchFilter.trim().toLowerCase();
    return cards.filter((card) => (!hideSealed || !isSealedProduct(card)) && (
      !query || card.name.toLowerCase().includes(query) || card.set_name.toLowerCase().includes(query)
      || card.number.toLowerCase().includes(query) || card.rarity?.toLowerCase().includes(query)
    ));
  }, [cards, searchFilter, hideSealed]);
  const summary = useMemo(() => summarizeDisplayedCards(filteredCards), [filteredCards]);
  const sealedCount = cards.filter(isSealedProduct).length;

  return (
    <div>
      {/* Market Intelligence Bar */}
      <div role="region" aria-label="Displayed card summary" aria-live="polite" aria-busy={isLoading} className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:gap-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            {hideSealed ? "Cards shown" : "Products shown"}
          </div>
          <div className="mt-1 font-mono text-2xl font-black text-slate-900">
            {isLoading ? "…" : summary.count}
          </div>
          <div className="mt-1 text-xs text-slate-500">{isLoading ? "Updating results…" : "In the list below"}</div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Highest Value Card
          </div>
          <div className="mt-1 font-mono text-2xl font-black text-emerald-600">
            {isLoading ? "…" : summary.highestCard ? formatPrice(summary.highestCard.market_price) : "Unavailable"}
          </div>
          <div className="mt-1 text-xs text-slate-500">{isLoading ? "Updating results…" : summary.highestCard ? <Link href={`/cards/${encodeURIComponent(summary.highestCard.id)}`} className="hover:text-emerald-700 hover:underline">{summary.highestCard.name}</Link> : "No priced individual cards shown"}</div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Total displayed price
          </div>
          <div className="mt-1 font-mono text-2xl font-black text-slate-700">
            {isLoading ? "…" : summary.totalPrice == null ? "Unavailable" : formatPrice(summary.totalPrice)}
          </div>
          <div className="mt-1 text-xs text-slate-500">{isLoading ? "Updating results…" : `${summary.pricedCount} of ${summary.count} displayed products priced${summary.missingCount ? ` · ${summary.missingCount} price${summary.missingCount === 1 ? "" : "s"} unavailable` : ""}`}</div>
        </div>

        <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50/50 p-4 shadow-sm flex flex-col justify-between">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-emerald-800">
              Full Catalog
            </div>
            <div className="text-xs text-emerald-700 mt-1">
              Browse with advanced multi-set and sealed filters
            </div>
          </div>
          <Link
            href={`/catalog?q=${encodeURIComponent(pokemonName)}`}
            className="mt-2 inline-flex items-center justify-between rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-emerald-700 shadow-xs"
          >
            <span>Open in Catalog</span>
            <span>→</span>
          </Link>
        </div>
      </div>

      {/* Filter & Sort Bar */}
      <div className="mb-6 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          {/* Search within cards */}
          <SearchInput
            value={searchFilter}
            onChange={setSearchFilter}
            placeholder={`Filter ${cards.length} ${pokemonName} cards (e.g. VMAX, Promo, Shadowless)...`}
          />

          <button type="button" aria-pressed={!hideSealed} onClick={() => setHideSealed((hidden) => !hidden)} className="shrink-0 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 aria-pressed:border-slate-900 aria-pressed:bg-slate-900 aria-pressed:text-white">
            {hideSealed ? "Show sealed products" : "Hide sealed products"}{sealedCount > 0 ? ` (${sealedCount})` : ""}
          </button>

          {/* Set Filter Dropdown */}
          <div className="flex flex-wrap items-center gap-2.5">
            <select
              aria-label="Set"
              value={selectedSet}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedSet(val);
              }}
              className="max-w-[220px] truncate rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 transition hover:bg-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="">All Sets</option>
              {sets.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>

            {/* Sort Dropdown */}
            <select
              aria-label="Sort cards"
              value={sortBy}
              onChange={(e) => {
                const val = e.target.value as CardSort;
                setSortBy(val);
              }}
              className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 transition hover:bg-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="price_desc">Price (High → Low)</option>
              <option value="price_asc">Price (Low → High)</option>
              <option value="number_asc">Card # (Low → High)</option>
              <option value="number_desc">Card # (High → Low)</option>
              <option value="name">Card Name (A → Z)</option>
              <option value="set">Set Release Date</option>
            </select>

            {/* Language Pill Selector */}
            <div role="group" aria-label="Card language" className="inline-flex rounded-xl bg-slate-100 p-0.5 text-xs font-bold">
              {(["all", "pokemon", "pokemon-japan"] as GameLanguage[]).map((g) => (
                <button
                  key={g}
                  type="button"
                  aria-pressed={game === g}
                  onClick={() => {
                    setGame(g);
                  }}
                  className={`rounded-lg px-2.5 py-1 transition ${
                    game === g
                      ? "bg-white text-slate-950 shadow-2xs font-bold"
                      : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {g === "all" ? "All" : g === "pokemon" ? "EN" : "JP"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {error && <p role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-700">{error} <button type="button" onClick={() => setRetry((n) => n + 1)} className="font-bold underline">Retry</button></p>}

      {/* Cards Grid with Staggered Cascading Skeletons */}
      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="animate-card-cascade flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white p-3 shadow-xs"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <div className="aspect-[5/7] w-full animate-pulse rounded-xl bg-slate-100" />
              <div className="mt-3 space-y-2">
                <div className="h-3 w-16 animate-pulse rounded bg-slate-100" />
                <div className="h-4 w-3/4 animate-pulse rounded bg-slate-200" />
                <div className="h-3 w-12 animate-pulse rounded bg-slate-100" />
              </div>
              <div className="mt-4 pt-2 border-t border-slate-100 flex items-center justify-between">
                <div className="h-3 w-10 animate-pulse rounded bg-slate-100" />
                <div className="h-4 w-14 animate-pulse rounded bg-emerald-100/70" />
              </div>
            </div>
          ))}
        </div>
      ) : filteredCards.length === 0 ? (
        <EmptyState
          title="No Trading Cards Found"
          description="No cards found matching your current set and search filter."
          onReset={() => {
            setSelectedSet("");
            setSearchFilter("");
            setGame("all");
            setSortBy("price_desc");
            setHideSealed(true);
          }}
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {filteredCards.map((card, idx) => (
            <CardItem
              key={card.id}
              card={card}
              idx={idx}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CardItem({
  card,
  idx,
}: {
  card: CardSummary;
  idx: number;
}) {
  const { formatPrice } = useCurrency();
  const [failed, setFailed] = useState(false);

  return (
    <Link
      href={`/cards/${encodeURIComponent(card.id)}`}
      prefetch={false}
      style={{ animationDelay: `${Math.min(idx * 25, 300)}ms` }}
      className="card-cv animate-card-cascade group relative flex flex-col justify-between overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-3 shadow-xs transition-all duration-300 hover:-translate-y-1 hover:border-emerald-300 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
    >
      <div>
        {/* 3D Holo Card Tilt with Rarity Shader */}
        <HoloCard maxTilt={8} rarity={card.rarity} className="w-full">
          <div className="relative aspect-[5/7] w-full overflow-hidden rounded-xl bg-slate-100 p-1">
            {failed ? (
              <div className="flex h-full w-full flex-col items-center justify-center bg-slate-100 text-center">
                <span className="flex h-10 w-10 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-xs font-black text-emerald-700">
                  {card.name.slice(0, 1).toUpperCase()}
                </span>
                <span className="mt-2 text-[9px] font-semibold text-slate-400 uppercase">Image pending</span>
              </div>
            ) : (
              <Image
                src={cardImageUrl(card.image_url)}
                alt={card.name}
                fill
                sizes="(max-width: 640px) 150px, (max-width: 1024px) 200px, 250px"
                className="object-contain transition-transform duration-300 group-hover:scale-105"
                placeholder="blur"
                blurDataURL={shimmerBlurDataUrl(150, 210)}
                onError={() => setFailed(true)}
                loading="lazy"
              />
            )}
          </div>
        </HoloCard>

        {/* Set & Number */}
        <div className="mt-2.5 flex items-center justify-between text-[10px] font-semibold text-slate-400">
          <span className="truncate text-slate-500 max-w-[110px]" title={card.set_name}>
            {card.set_name}
          </span>
          <span className="font-mono">#{card.number}</span>
        </div>

        {/* Name */}
        <h4
          className="mt-1 line-clamp-2 text-xs font-bold text-slate-900 transition group-hover:text-emerald-700 leading-snug"
          title={card.name}
        >
          {card.name}
        </h4>

        {/* Rarity */}
        {card.rarity && (
          <div className="mt-1">
            <span className="inline-block rounded-md bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-600 truncate max-w-full">
              {card.rarity}
            </span>
          </div>
        )}
      </div>

      {/* Price Badge with Multi-Currency formatting */}
      <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between">
        <div className="text-[10px] text-slate-400 font-medium">Market</div>
        <div className="font-mono text-xs font-black text-emerald-600">
          {formatPrice(card.market_price, { showPending: true })}
        </div>
      </div>
    </Link>
  );
}
