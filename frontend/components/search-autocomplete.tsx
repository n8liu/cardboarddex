"use client";

import { useState, useEffect, useRef, useMemo, type FormEvent, type KeyboardEvent } from "react";
import Image from "@/components/card-image";
import { useRouter } from "next/navigation";
import { POKEDEX_DATA } from "@/lib/pokedex-data";
import { getCardSets, searchCards, cardImageUrl } from "@/lib/api";
import { TYPE_THEMES, formatDexNumber } from "@/lib/pokeapi";
import type { CardSetOption, CardSummary } from "@/types/card";
import type { PokedexEntry, PokemonType } from "@/types/pokemon";

interface AutocompleteItem {
  id: string;
  type: "pokemon" | "set" | "card" | "full_search";
  title: string;
  subtitle?: string;
  badge?: string;
  image?: string;
  types?: PokemonType[];
  href: string;
}

export function SearchAutocomplete() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);

  // Data states
  const [allSets, setAllSets] = useState<CardSetOption[]>([]);
  const [cardsResults, setCardsResults] = useState<CardSummary[]>([]);
  const [isLoadingCards, setIsLoadingCards] = useState(false);

  // 1. Fetch set list on mount (cached for instant set matching)
  useEffect(() => {
    let isMounted = true;
    getCardSets()
      .then((sets) => {
        if (isMounted) setAllSets(sets);
      })
      .catch((err) => {
        console.error("Failed to load sets for autocomplete:", err);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Debounced API search for cards/products
  useEffect(() => {
    const cleanQuery = query.trim();
    if (!cleanQuery || cleanQuery.length < 2) {
      setCardsResults([]);
      setIsLoadingCards(false);
      return;
    }

    setIsLoadingCards(true);
    const timer = setTimeout(() => {
      searchCards(cleanQuery, { limit: 5, hideSealed: false })
        .then((cards) => {
          setCardsResults(cards);
          setIsLoadingCards(false);
        })
        .catch((err) => {
          console.error("Failed to search cards for autocomplete:", err);
          setIsLoadingCards(false);
        });
    }, 180);

    return () => clearTimeout(timer);
  }, [query]);

  // 3. Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 4. Compute matching Pokémon species (Instant client-side from 1,025 Pokédex entries)
  const matchedPokemon = useMemo<PokedexEntry[]>(() => {
    const clean = query.trim().toLowerCase();
    if (!clean) return [];

    // Dex number check (#0025, 25, etc.)
    const numClean = clean.replace("#", "");
    if (/^\d+$/.test(numClean)) {
      const dex = parseInt(numClean, 10);
      const exact = POKEDEX_DATA.find((p) => p.id === dex);
      if (exact) return [exact];
    }

    // Name prefix matches first, then contains
    const prefixMatches: PokedexEntry[] = [];
    const containsMatches: PokedexEntry[] = [];

    for (const p of POKEDEX_DATA) {
      const lower = p.name.toLowerCase();
      if (lower.startsWith(clean)) {
        prefixMatches.push(p);
        if (prefixMatches.length >= 4) break;
      } else if (lower.includes(clean)) {
        containsMatches.push(p);
      }
    }

    return [...prefixMatches, ...containsMatches].slice(0, 4);
  }, [query]);

  // 5. Compute matching Sets (Instant client-side from cached set list)
  const matchedSets = useMemo<CardSetOption[]>(() => {
    const clean = query.trim().toLowerCase();
    if (!clean || allSets.length === 0) return [];

    const matches = allSets.filter(
      (s) =>
        s.name.toLowerCase().includes(clean) ||
        (s.series && s.series.toLowerCase().includes(clean)) ||
        s.id.toLowerCase().includes(clean)
    );

    return matches.slice(0, 3);
  }, [query, allSets]);

  // 6. Flatten all actionable results into unified list for keyboard navigation
  const flatItems = useMemo<AutocompleteItem[]>(() => {
    const clean = query.trim();
    if (!clean) return [];

    const items: AutocompleteItem[] = [];

    // Pokémon items
    for (const p of matchedPokemon) {
      items.push({
        id: `poke-${p.id}`,
        type: "pokemon",
        title: p.name,
        subtitle: `Gen ${p.generation} · ${p.region}`,
        badge: formatDexNumber(p.id),
        image: p.sprite || p.artwork,
        types: p.types,
        href: `/pokemon/${p.id}`,
      });
    }

    // Set items
    for (const s of matchedSets) {
      items.push({
        id: `set-${s.id}`,
        type: "set",
        title: s.name,
        subtitle: s.series ? `${s.series}${s.release_date ? ` · ${s.release_date.slice(0, 4)}` : ""}` : "Expansion Set",
        badge: s.series || "Set",
        image: s.image_url ? cardImageUrl(s.image_url) : undefined,
        href: `/catalog?set=${encodeURIComponent(s.id)}`,
      });
    }

    // Card items
    for (const c of cardsResults) {
      items.push({
        id: `card-${c.id}`,
        type: "card",
        title: c.name,
        subtitle: `${c.set_name}${c.number ? ` · #${c.number}` : ""}`,
        badge: c.market_price ? `$${c.market_price.toFixed(2)}` : undefined,
        image: c.image_url ? cardImageUrl(c.image_url) : undefined,
        href: `/cards/${c.id}`,
      });
    }

    // Full catalog search item
    items.push({
      id: "full-search",
      type: "full_search",
      title: `Search all cards & products for “${clean}”`,
      subtitle: "View full expansion catalog results with filters",
      href: `/catalog?q=${encodeURIComponent(clean)}`,
    });

    return items;
  }, [query, matchedPokemon, matchedSets, cardsResults]);

  // Reset selected index when results change
  useEffect(() => {
    setSelectedIndex(-1);
  }, [flatItems]);

  const handleSelect = (item: AutocompleteItem) => {
    setIsOpen(false);
    router.push(item.href);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const clean = query.trim();
    if (!clean) return;

    if (selectedIndex >= 0 && selectedIndex < flatItems.length) {
      handleSelect(flatItems[selectedIndex]);
      return;
    }

    // Check if query is exact dex number
    const numClean = clean.replace("#", "");
    if (/^\d+$/.test(numClean)) {
      const id = parseInt(numClean, 10);
      if (id >= 1 && id <= 1025) {
        setIsOpen(false);
        router.push(`/pokemon/${id}`);
        return;
      }
    }

    // If exact single pokemon match, navigate to it
    if (matchedPokemon.length === 1 && matchedPokemon[0].name.toLowerCase() === clean.toLowerCase()) {
      setIsOpen(false);
      router.push(`/pokemon/${matchedPokemon[0].id}`);
      return;
    }

    setIsOpen(false);
    router.push(`/catalog?q=${encodeURIComponent(clean)}`);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || flatItems.length === 0) {
      if (e.key === "ArrowDown" && query.trim()) {
        setIsOpen(true);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < flatItems.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : flatItems.length - 1));
    } else if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
    }
  };

  const hasAnyResults = matchedPokemon.length > 0 || matchedSets.length > 0 || cardsResults.length > 0;

  return (
    <div ref={containerRef} className="relative w-full max-w-2xl font-mono">
      <form onSubmit={handleSubmit} className="relative flex items-center">
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute left-4 h-5 w-5 text-slate-400"
          fill="none"
          viewBox="0 0 24 24"
        >
          <path
            d="m21 21-4.35-4.35m2.35-5.65a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="2"
          />
        </svg>

        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!isOpen) setIsOpen(true);
          }}
          onFocus={() => {
            if (query.trim()) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search any card, set, or Pokémon (e.g. Zekrom, 151, #0025)..."
          className="h-13 w-full rounded-xl border border-slate-300 bg-white pl-12 pr-28 text-xs text-slate-950 shadow-xs outline-none transition placeholder:text-slate-400 focus:border-slate-900 focus:ring-4 focus:ring-slate-900/10 sm:text-sm"
          autoComplete="off"
          spellCheck={false}
        />

        {query.trim() && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setIsOpen(false);
              inputRef.current?.focus();
            }}
            className="absolute right-24 h-7 w-7 rounded-full text-xs font-bold text-slate-400 hover:bg-slate-100 hover:text-slate-700 flex items-center justify-center transition"
            title="Clear search"
          >
            ✕
          </button>
        )}

        <button
          type="submit"
          className="absolute right-2 h-9 rounded-lg bg-slate-900 px-4 text-xs font-bold text-white transition hover:bg-slate-800"
        >
          SEARCH
        </button>
      </form>

      {/* AUTOCOMPLETE DROPDOWN MENU */}
      {isOpen && query.trim().length >= 1 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 max-h-[480px] overflow-y-auto rounded-2xl border border-slate-200/90 bg-white/95 p-2 shadow-2xl backdrop-blur-md">
          {/* 1. Pokémon Species Section */}
          {matchedPokemon.length > 0 && (
            <div className="mb-2">
              <div className="flex items-center justify-between px-3 py-1 text-[10px] font-black uppercase tracking-wider text-slate-400">
                <span>Pokémon Species</span>
                <span className="text-[9px] font-normal text-slate-400">Pokédex Profiles</span>
              </div>
              <div className="space-y-1">
                {matchedPokemon.map((poke) => {
                  const itemIndex = flatItems.findIndex((fi) => fi.id === `poke-${poke.id}`);
                  const isSelected = selectedIndex === itemIndex;

                  return (
                    <button
                      key={`drop-poke-${poke.id}`}
                      type="button"
                      onClick={() => handleSelect(flatItems[itemIndex])}
                      onMouseEnter={() => setSelectedIndex(itemIndex)}
                      className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition ${
                        isSelected ? "bg-slate-100 text-slate-950" : "hover:bg-slate-50 text-slate-800"
                      }`}
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <div className="relative h-9 w-9 shrink-0 overflow-hidden rounded-lg border border-slate-100 bg-slate-50 p-0.5">
                          {poke.artwork || poke.sprite ? (
                            <Image
                              src={poke.artwork || poke.sprite}
                              alt={poke.name}
                              fill
                              sizes="36px"
                              className="object-contain"
                              unoptimized
                            />
                          ) : (
                            <span className="flex h-full w-full items-center justify-center font-mono text-[10px] font-bold text-slate-400">
                              #{poke.id}
                            </span>
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs font-bold text-slate-950 sm:text-sm">
                            {poke.name}
                          </p>
                          <div className="flex items-center gap-1.5 font-mono text-[11px] text-slate-500">
                            <span>{formatDexNumber(poke.id)}</span>
                            <span className="text-slate-300">•</span>
                            <span>Gen {poke.generation} · {poke.region}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex shrink-0 items-center gap-1">
                        {poke.types.map((type: PokemonType) => {
                          const theme = TYPE_THEMES[type] || TYPE_THEMES.normal;
                          return (
                            <span
                              key={type}
                              className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${theme.badge}`}
                            >
                              {type}
                            </span>
                          );
                        })}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* 2. Expansions & Sets Section */}
          {matchedSets.length > 0 && (
            <div className="mb-2">
              <div className="flex items-center justify-between px-3 py-1 text-[10px] font-black uppercase tracking-wider text-slate-400">
                <span>Expansions &amp; Sets</span>
                <span className="text-[9px] font-normal text-slate-400">Card Catalogs</span>
              </div>
              <div className="space-y-1">
                {matchedSets.map((set) => {
                  const itemIndex = flatItems.findIndex((fi) => fi.id === `set-${set.id}`);
                  const isSelected = selectedIndex === itemIndex;

                  return (
                    <button
                      key={`drop-set-${set.id}`}
                      type="button"
                      onClick={() => handleSelect(flatItems[itemIndex])}
                      onMouseEnter={() => setSelectedIndex(itemIndex)}
                      className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition ${
                        isSelected ? "bg-slate-100 text-slate-950" : "hover:bg-slate-50 text-slate-800"
                      }`}
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <div className="relative h-10 w-10 shrink-0 overflow-hidden rounded-lg border border-slate-200/80 bg-slate-50 flex items-center justify-center p-0.5">
                          {set.image_url ? (
                            <Image
                              src={cardImageUrl(set.image_url)}
                              alt={set.name}
                              fill
                              sizes="40px"
                              className="object-contain"
                              unoptimized
                            />
                          ) : (
                            <span className="font-mono text-[9px] font-bold text-slate-500">SET</span>
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs font-bold text-slate-950 sm:text-sm">
                            {set.name}
                          </p>
                          <p className="truncate font-mono text-[11px] text-slate-500">
                            {set.series || "Pokémon TCG"}
                            {set.release_date && ` · ${set.release_date.slice(0, 4)}`}
                          </p>
                        </div>
                      </div>

                      {set.series ? (
                        <span className="shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-600">
                          {set.series}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* 3. Cards & Products Section */}
          {cardsResults.length > 0 && (
            <div className="mb-2">
              <div className="flex items-center justify-between px-3 py-1 text-[10px] font-black uppercase tracking-wider text-slate-400">
                <span>Cards &amp; Products</span>
                <span className="text-[9px] font-normal text-slate-400">Live Comps</span>
              </div>
              <div className="space-y-1">
                {cardsResults.map((card) => {
                  const itemIndex = flatItems.findIndex((fi) => fi.id === `card-${card.id}`);
                  const isSelected = selectedIndex === itemIndex;

                  return (
                    <button
                      key={`drop-card-${card.id}`}
                      type="button"
                      onClick={() => handleSelect(flatItems[itemIndex])}
                      onMouseEnter={() => setSelectedIndex(itemIndex)}
                      className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition ${
                        isSelected ? "bg-slate-100 text-slate-950" : "hover:bg-slate-50 text-slate-800"
                      }`}
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <div className="relative h-12 w-9 shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-50 flex items-center justify-center p-0.5">
                          {card.image_url ? (
                            <Image
                              src={cardImageUrl(card.image_url)}
                              alt={card.name}
                              fill
                              sizes="36px"
                              className="object-contain"
                              unoptimized
                            />
                          ) : (
                            <span className="flex h-full w-full items-center justify-center font-mono text-[8px] font-bold text-slate-400">
                              CARD
                            </span>
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs font-bold text-slate-950 sm:text-sm">
                            {card.name}
                          </p>
                          <p className="truncate font-mono text-[11px] text-slate-500">
                            {card.set_name}
                            {card.number && ` · #${card.number}`}
                          </p>
                        </div>
                      </div>

                      <div className="text-right">
                        {card.market_price ? (
                          <span className="font-mono text-xs font-bold text-emerald-600">
                            ${card.market_price.toFixed(2)}
                          </span>
                        ) : (
                          <span className="font-mono text-[10px] text-slate-400">—</span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Inline Loading Indicator */}
          {isLoadingCards && (
            <div className="flex items-center gap-2 px-3 py-2 font-mono text-[11px] text-slate-500">
              <span className="h-2 w-2 animate-ping rounded-full bg-emerald-500" />
              <span>Searching cards database...</span>
            </div>
          )}

          {/* No direct matches notice if nothing found */}
          {!hasAnyResults && !isLoadingCards && (
            <div className="px-3 py-4 text-center font-mono text-xs text-slate-500">
              No direct Pokémon or set matches found for “{query}”.
            </div>
          )}

          {/* 4. Full Search Footer Item */}
          <div className="border-t border-slate-200/80 pt-1 mt-1">
            {(() => {
              const fullSearchIndex = flatItems.length - 1;
              const isSelected = selectedIndex === fullSearchIndex;

              return (
                <button
                  type="button"
                  onClick={() => handleSelect(flatItems[fullSearchIndex])}
                  onMouseEnter={() => setSelectedIndex(fullSearchIndex)}
                  className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left font-mono text-xs font-bold transition ${
                    isSelected
                      ? "bg-slate-900 text-white"
                      : "bg-slate-50 text-slate-800 hover:bg-slate-100"
                  }`}
                >
                  <span className="truncate">
                    Search all cards &amp; products for “{query.trim()}”
                  </span>
                  <span className="shrink-0 text-[11px]">Catalog →</span>
                </button>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
