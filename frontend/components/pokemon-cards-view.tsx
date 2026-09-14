"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { CardSort, CardSummary, GameLanguage } from "@/types/card";
import type { PokemonSetCount } from "@/types/pokemon";
import { cardImageUrl, getPokemonCards } from "@/lib/api";
import { EmptyState } from "@/components/ui/empty-state";
import { SearchInput } from "@/components/ui/search-input";

type Props = {
  pokemonName: string;
  initialCards: CardSummary[];
  availableSets: PokemonSetCount[];
  totalCards: number;
  highestPrice: number | null;
  lowestPrice: number | null;
};

export function PokemonCardsView({
  pokemonName,
  initialCards,
  availableSets,
  totalCards,
  highestPrice,
  lowestPrice,
}: Props) {
  const searchParams = useSearchParams();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const s = params.get("set")?.trim() ?? "";
    const sortRaw = params.get("sort") as CardSort;
    const validSorts: CardSort[] = ["price_desc", "price_asc", "number_asc", "number_desc"];
    const sort = validSorts.includes(sortRaw) ? sortRaw : "price_desc";
    const g = (params.get("game") as GameLanguage) || "all";
    const game: GameLanguage = ["all", "pokemon", "pokemon-japan"].includes(g) ? g : "all";
    const q = params.get("q")?.trim() ?? "";
    return { s, sort, game, q };
  }, [searchParams]);

  const initialParams = getUrlParams();
  const [cards, setCards] = useState<CardSummary[]>(initialCards);
  const [selectedSet, setSelectedSet] = useState<string>(initialParams.s);
  const [sortBy, setSortBy] = useState<CardSort>(initialParams.sort);
  const [game, setGame] = useState<GameLanguage>(initialParams.game);
  const [searchFilter, setSearchFilter] = useState(initialParams.q);
  const [isLoading, setIsLoading] = useState(false);
  const isFirstMount = useRef(true);

  // Sync browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const params = getUrlParams();
      setSelectedSet(params.s);
      setSortBy(params.sort);
      setGame(params.game);
      setSearchFilter(params.q);
      void handleFilterChange(params.s, params.sort, params.game);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [getUrlParams]);

  // Keep URL in sync with active filters
  useEffect(() => {
    if (isFirstMount.current) {
      isFirstMount.current = false;
      if (initialParams.s !== "" || initialParams.sort !== "price_desc" || initialParams.game !== "all" || initialCards.length === 0) {
        void handleFilterChange(initialParams.s, initialParams.sort, initialParams.game);
      }
      return;
    }

    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href);
      selectedSet ? url.searchParams.set("set", selectedSet) : url.searchParams.delete("set");
      sortBy !== "price_desc" ? url.searchParams.set("sort", sortBy) : url.searchParams.delete("sort");
      game !== "all" ? url.searchParams.set("game", game) : url.searchParams.delete("game");
      searchFilter.trim() ? url.searchParams.set("q", searchFilter.trim()) : url.searchParams.delete("q");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }, 150);

    return () => window.clearTimeout(timer);
  }, [selectedSet, sortBy, game, searchFilter]);

  // Fetch updated cards when set, sort, or game changes
  const handleFilterChange = async (newSet: string, newSort: CardSort, newGame: GameLanguage) => {
    setIsLoading(true);
    try {
      const res = await getPokemonCards(pokemonName, {
        setId: newSet || undefined,
        sortBy: newSort,
        game: newGame,
        limit: 100,
      });
      setCards(res.cards);
    } catch (err) {
      console.error("[PokemonCardsView] Error loading cards:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const filteredCards = useMemo(() => {
    if (!searchFilter.trim()) return cards;
    const q = searchFilter.trim().toLowerCase();
    return cards.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.set_name.toLowerCase().includes(q) ||
        c.number.toLowerCase().includes(q) ||
        (c.rarity && c.rarity.toLowerCase().includes(q))
    );
  }, [cards, searchFilter]);

  const formatPrice = (val: number | null) => {
    if (val === null || val === undefined || isNaN(val)) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: val < 10 ? 2 : 0,
      maximumFractionDigits: 2,
    }).format(val);
  };

  return (
    <div>
      {/* Market Intelligence Bar */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:gap-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Total Cards Found
          </div>
          <div className="mt-1 font-mono text-2xl font-black text-slate-900">
            {totalCards}
          </div>
          <div className="mt-1 text-xs text-slate-500">Indexed in database</div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Highest Value Card
          </div>
          <div className="mt-1 font-mono text-2xl font-black text-emerald-600">
            {formatPrice(highestPrice)}
          </div>
          <div className="mt-1 text-xs text-slate-500">Top market price</div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Lowest Entry Price
          </div>
          <div className="mt-1 font-mono text-2xl font-black text-slate-700">
            {formatPrice(lowestPrice)}
          </div>
          <div className="mt-1 text-xs text-slate-500">Accessible copy</div>
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

          {/* Set Filter Dropdown */}
          <div className="flex flex-wrap items-center gap-2.5">
            <select
              value={selectedSet}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedSet(val);
                handleFilterChange(val, sortBy, game);
              }}
              className="max-w-[220px] truncate rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 transition hover:bg-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="">All Sets ({totalCards} cards)</option>
              {availableSets.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.count})
                </option>
              ))}
            </select>

            {/* Sort Dropdown */}
            <select
              value={sortBy}
              onChange={(e) => {
                const val = e.target.value as CardSort;
                setSortBy(val);
                handleFilterChange(selectedSet, val, game);
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
            <div className="inline-flex rounded-xl bg-slate-100 p-0.5 text-xs font-bold">
              {(["all", "pokemon", "pokemon-japan"] as GameLanguage[]).map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => {
                    setGame(g);
                    handleFilterChange(selectedSet, sortBy, g);
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

      {/* Cards Grid */}
      {isLoading ? (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-200 bg-white">
          <div className="flex flex-col items-center gap-2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-emerald-600" />
            <span className="text-xs font-bold text-slate-500">Loading {pokemonName} cards...</span>
          </div>
        </div>
      ) : filteredCards.length === 0 ? (
        <EmptyState
          title="No Trading Cards Found"
          description="No cards found matching your current set and search filter."
          onReset={() => {
            setSelectedSet("");
            setSearchFilter("");
            setGame("all");
            handleFilterChange("", "price_desc", "all");
          }}
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {filteredCards.map((card) => (
            <CardItem
              key={card.id}
              card={card}
              formatPrice={formatPrice}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CardItem({
  card,
  formatPrice,
}: {
  card: CardSummary;
  formatPrice: (val: number | null) => string;
}) {
  return (
    <Link
      href={`/cards/${card.id}`}
      prefetch={false}
      className="group relative flex flex-col justify-between overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-3 shadow-xs transition-all duration-300 hover:-translate-y-1 hover:border-emerald-300 hover:shadow-lg"
    >
      <div>
        {/* Card Image */}
        <div className="relative aspect-[2.5/3.5] w-full overflow-hidden rounded-xl bg-slate-100 p-1">
          <Image
            src={cardImageUrl(card.image_url)}
            alt={card.name}
            fill
            sizes="(max-width: 640px) 150px, (max-width: 1024px) 200px, 250px"
            className="object-contain transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        </div>

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

      {/* Price Badge */}
      <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between">
        <div className="text-[10px] text-slate-400 font-medium">Market</div>
        <div className="font-mono text-xs font-black text-emerald-600">
          {formatPrice(card.market_price)}
        </div>
      </div>
    </Link>
  );
}
