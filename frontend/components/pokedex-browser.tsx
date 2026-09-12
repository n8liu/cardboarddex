"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { BackToTop } from "@/components/ui/back-to-top";
import { POKEDEX_DATA, GENERATION_REGIONS } from "@/lib/pokedex-data";
import { TYPE_THEMES, formatDexNumber } from "@/lib/pokeapi";
import {
  getEvolutionFamilyIds,
  getEvolutionRelation,
  type EvolutionRelation,
} from "@/lib/pokemon-evolutions";
import type { PokedexEntry, PokemonType } from "@/types/pokemon";

const INITIAL_BATCH = 60;
const BATCH_SIZE = 48;

const ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"];

function getGenerationInfo(gen: number) {
  return GENERATION_REGIONS.find((g) => g.gen === gen);
}

type SortOption = "id_asc" | "id_desc" | "name_asc" | "name_desc";

export function PokedexBrowser() {
  const searchParams = useSearchParams();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const q = params.get("q")?.trim() ?? "";
    const genRaw = params.get("gen");
    const gen = genRaw && !isNaN(Number(genRaw)) ? Number(genRaw) : null;
    const typeRaw = params.get("type") as PokemonType;
    const type = typeRaw && typeRaw in TYPE_THEMES ? typeRaw : null;
    const sortRaw = params.get("sort") as SortOption;
    const validSorts: SortOption[] = ["id_asc", "id_desc", "name_asc", "name_desc"];
    const sort = validSorts.includes(sortRaw) ? sortRaw : "id_asc";
    const evoRaw = params.get("evo");
    const showEvolutions = evoRaw === "0" || evoRaw === "false" ? false : true;
    return { q, gen, type, sort, showEvolutions };
  }, [searchParams]);

  const initialParams = getUrlParams();
  const [query, setQuery] = useState(initialParams.q);
  const [selectedGen, setSelectedGen] = useState<number | null>(initialParams.gen);
  const [selectedType, setSelectedType] = useState<PokemonType | null>(initialParams.type);
  const [sortBy, setSortBy] = useState<SortOption>(initialParams.sort);
  const [showEvolutions, setShowEvolutions] = useState<boolean>(initialParams.showEvolutions);
  const [visibleCount, setVisibleCount] = useState(INITIAL_BATCH);
  const [restoredPokemonId, setRestoredPokemonId] = useState<number | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const isInitialized = useRef(false);
  const hasRestoredRef = useRef(false);
  const [, startTransition] = useTransition();

  const { filteredPokemon, directMatchIds, hasEvolutionsActive } = useMemo(() => {
    let list = POKEDEX_DATA;
    const isQueryActive = Boolean(query.trim());
    const directMatchedIds = new Set<number>();

    if (isQueryActive) {
      const q = query.trim().toLowerCase();
      const numQuery = q.replace("#", "").trim();
      const isNum = !isNaN(Number(numQuery)) && numQuery !== "";
      const targetId = isNum ? Number(numQuery) : null;
      const normQ = q.replace(/[\s-]+(shield|blade|normal|altered|land|incarnate|ordinary|aria|male|female|average|50|baile|midday|solo|meteor|disguised|amped|ice|belly|strike)$/i, "").trim();

      const directMatches = list.filter((p) => {
        if (targetId !== null && p.id === targetId) return true;
        const nameLower = p.name.toLowerCase();
        const slugLower = p.slug.toLowerCase();
        return (
          nameLower.includes(q) ||
          slugLower.includes(q) ||
          (normQ !== "" && (nameLower.includes(normQ) || slugLower.includes(normQ))) ||
          String(p.id).includes(q)
        );
      });

      directMatches.forEach((p) => directMatchedIds.add(p.id));

      if (showEvolutions && directMatches.length > 0) {
        // Group by evolution family based on the first occurrence of direct matches
        const familyGroups: { anchorId: number; members: number[] }[] = [];
        const seenFamilies = new Set<number>();
        const allFamilyIds = new Set<number>();

        for (const p of directMatches) {
          const fam = getEvolutionFamilyIds(p.id);
          const familyKey = fam[0];
          if (!seenFamilies.has(familyKey)) {
            seenFamilies.add(familyKey);
            familyGroups.push({ anchorId: p.id, members: fam });
            fam.forEach((id) => allFamilyIds.add(id));
          }
        }

        let expandedList: PokedexEntry[] = [];
        if (sortBy === "id_asc") {
          // Sort family groups by the lowest anchor ID in each family so groups stay sequential
          familyGroups.sort((a, b) => a.anchorId - b.anchorId);
          const added = new Set<number>();
          for (const group of familyGroups) {
            for (const memberId of group.members) {
              if (!added.has(memberId) && memberId >= 1 && memberId <= POKEDEX_DATA.length) {
                added.add(memberId);
                expandedList.push(POKEDEX_DATA[memberId - 1]);
              }
            }
          }
        } else {
          expandedList = Array.from(allFamilyIds)
            .filter((id) => id >= 1 && id <= POKEDEX_DATA.length)
            .map((id) => POKEDEX_DATA[id - 1]);
        }

        list = expandedList;
      } else {
        list = directMatches;
      }
    }

    if (selectedGen !== null) {
      list = list.filter((p) => p.generation === selectedGen);
    }

    if (selectedType !== null) {
      list = list.filter((p) => p.types.includes(selectedType));
    }

    if (!isQueryActive || !showEvolutions || sortBy !== "id_asc") {
      list = [...list].sort((a, b) => {
        switch (sortBy) {
          case "id_desc":
            return b.id - a.id;
          case "name_asc":
            return a.name.localeCompare(b.name);
          case "name_desc":
            return b.name.localeCompare(a.name);
          case "id_asc":
          default:
            return a.id - b.id;
        }
      });
    }

    return {
      filteredPokemon: list,
      directMatchIds: directMatchedIds,
      hasEvolutionsActive: isQueryActive && showEvolutions,
    };
  }, [query, showEvolutions, selectedGen, selectedType, sortBy]);

  // Helper to persist target Pokémon and batch size before navigating away
  const saveScrollState = useCallback((pokemonId?: number) => {
    if (!pokemonId) return;
    try {
      const targetIndex = filteredPokemon.findIndex((p) => p.id === pokemonId);
      const neededBatch = Math.min(
        filteredPokemon.length,
        Math.max(
          visibleCount,
          targetIndex >= 0 ? Math.ceil((targetIndex + 24) / BATCH_SIZE) * BATCH_SIZE : INITIAL_BATCH
        )
      );
      sessionStorage.setItem(
        "cardboarddex_pokedex_last_viewed",
        JSON.stringify({
          pokemonId,
          visibleCount: neededBatch,
          scrollY: window.scrollY,
          timestamp: Date.now(),
        })
      );
      sessionStorage.setItem("cardboarddex_pokedex_in_profile", "true");
    } catch {
      // Ignore quota or disabled storage
    }
  }, [filteredPokemon, visibleCount]);

  // Restore Pokédex batch and scroll position when returning from detail page
  useEffect(() => {
    if (hasRestoredRef.current) return;

    try {
      const navReset = sessionStorage.getItem("cardboarddex_pokedex_nav_reset");
      if (navReset) {
        sessionStorage.removeItem("cardboarddex_pokedex_nav_reset");
        sessionStorage.removeItem("cardboarddex_pokedex_last_viewed");
        sessionStorage.removeItem("cardboarddex_pokedex_in_profile");
        sessionStorage.removeItem("cardboarddex_pokedex_return_from_profile");
        hasRestoredRef.current = true;
        window.scrollTo({ top: 0, behavior: "instant" });
        return;
      }

      const inProfile = sessionStorage.getItem("cardboarddex_pokedex_in_profile");
      const returnFromProfile = sessionStorage.getItem("cardboarddex_pokedex_return_from_profile");
      const raw = sessionStorage.getItem("cardboarddex_pokedex_last_viewed");

      // Clean up navigation markers so subsequent interactions start clean
      sessionStorage.removeItem("cardboarddex_pokedex_in_profile");
      sessionStorage.removeItem("cardboarddex_pokedex_return_from_profile");

      if (!raw || (!inProfile && !returnFromProfile)) {
        if (raw) {
          sessionStorage.removeItem("cardboarddex_pokedex_last_viewed");
        }
        hasRestoredRef.current = true;
        window.scrollTo({ top: 0, behavior: "instant" });
        return;
      }

      const data = JSON.parse(raw);
      sessionStorage.removeItem("cardboarddex_pokedex_last_viewed");
      hasRestoredRef.current = true;

      if (!data || !data.pokemonId) return;

      // Only restore if within 1 hour
      if (Date.now() - data.timestamp > 60 * 60 * 1000) {
        return;
      }

      const { pokemonId, visibleCount: savedCount, scrollY } = data;

      const targetIndex = filteredPokemon.findIndex((p) => p.id === pokemonId);
      const needed = Math.min(
        filteredPokemon.length,
        Math.max(
          INITIAL_BATCH,
          savedCount || 0,
          targetIndex >= 0 ? Math.ceil((targetIndex + 24) / BATCH_SIZE) * BATCH_SIZE : INITIAL_BATCH
        )
      );

      if (needed > INITIAL_BATCH) {
        setVisibleCount(needed);
      }

      setRestoredPokemonId(pokemonId);

      const immediateCard = document.getElementById(`pokemon-card-${pokemonId}`);
      if (immediateCard) {
        immediateCard.scrollIntoView({ block: "center", behavior: "instant" });
      }

      let attempts = 0;
      const maxAttempts = 20;
      const scrollTimer = setInterval(() => {
        attempts++;
        const cardEl = document.getElementById(`pokemon-card-${pokemonId}`);
        if (cardEl) {
          cardEl.scrollIntoView({ block: "center", behavior: "instant" });
          clearInterval(scrollTimer);
        } else if (attempts >= maxAttempts) {
          if (typeof scrollY === "number" && scrollY > 0) {
            window.scrollTo({ top: scrollY, behavior: "instant" });
          }
          clearInterval(scrollTimer);
        }
      }, 30);

      return () => clearInterval(scrollTimer);
    } catch (err) {
      console.error("Failed to restore Pokédex position:", err);
    }
  }, [filteredPokemon]);

  // Clear restored highlight after 2.5 seconds
  useEffect(() => {
    if (restoredPokemonId !== null) {
      const timer = setTimeout(() => {
        setRestoredPokemonId(null);
      }, 2500);
      return () => clearTimeout(timer);
    }
  }, [restoredPokemonId]);

  // Sync back/forward browser navigation
  useEffect(() => {
    const onPopState = () => {
      const { q, gen, type, sort, showEvolutions: evo } = getUrlParams();
      setQuery(q);
      setSelectedGen(gen);
      setSelectedType(type);
      setSortBy(sort);
      setShowEvolutions(evo);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [getUrlParams]);

  // Keep URL in sync with active filters
  useEffect(() => {
    if (!isInitialized.current) {
      isInitialized.current = true;
      return;
    }

    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href);
      query.trim() ? url.searchParams.set("q", query.trim()) : url.searchParams.delete("q");
      selectedGen !== null ? url.searchParams.set("gen", String(selectedGen)) : url.searchParams.delete("gen");
      selectedType ? url.searchParams.set("type", selectedType) : url.searchParams.delete("type");
      sortBy !== "id_asc" ? url.searchParams.set("sort", sortBy) : url.searchParams.delete("sort");
      !showEvolutions ? url.searchParams.set("evo", "0") : url.searchParams.delete("evo");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }, 150);

    return () => window.clearTimeout(timer);
  }, [query, selectedGen, selectedType, sortBy, showEvolutions]);

  // Display continuous stream of Pokémon up to visibleCount
  const displayedPokemon = useMemo(() => {
    return filteredPokemon.slice(0, visibleCount);
  }, [filteredPokemon, visibleCount]);

  const hasMore = displayedPokemon.length < filteredPokemon.length;

  // Infinite scroll observer: auto-load next batch as user scrolls
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleCount((prev) => {
            if (prev < filteredPokemon.length) {
              return Math.min(filteredPokemon.length, prev + BATCH_SIZE);
            }
            return prev;
          });
        }
      },
      { rootMargin: "400px" }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [filteredPokemon.length]);

  const handleGenClick = (gen: number | null) => {
    startTransition(() => {
      setSelectedGen(gen);
      setVisibleCount(INITIAL_BATCH);
    });
  };

  const handleTypeClick = (type: PokemonType | null) => {
    startTransition(() => {
      setSelectedType((prev) => (prev === type ? null : type));
      setVisibleCount(INITIAL_BATCH);
    });
  };

  const handleSearchChange = (val: string) => {
    startTransition(() => {
      setQuery(val);
      setVisibleCount(INITIAL_BATCH);
    });
  };

  const resetAllFilters = () => {
    startTransition(() => {
      setQuery("");
      setSelectedGen(null);
      setSelectedType(null);
      setSortBy("id_asc");
      setShowEvolutions(true);
      setVisibleCount(INITIAL_BATCH);
    });
  };

  const loadMore = () => {
    setVisibleCount((prev) => Math.min(filteredPokemon.length, prev + BATCH_SIZE));
  };

  const loadAll = () => {
    setVisibleCount(filteredPokemon.length);
  };

  const hasActiveFilters = Boolean(
    query || selectedGen !== null || selectedType !== null || sortBy !== "id_asc" || !showEvolutions
  );

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-6 lg:px-8">
      {/* Header Section */}
      <section className="mb-8 pt-1">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-50/80 px-3.5 py-1 text-xs font-semibold text-emerald-800">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              Official National Pokédex · Generations I – IX
            </div>

            <h1 className="text-3xl font-black tracking-tight text-slate-950 sm:text-4xl lg:text-5xl">
              CardboardDex{" "}
              <span className="text-emerald-600">
                Pokédex
              </span>
            </h1>

            <p className="mt-2 text-sm leading-relaxed text-slate-600 sm:text-base">
              Explore all 1,025 Pokémon across 9 generations. Click any Pokémon to view official stats,
              high-resolution artwork, and all verified trading cards with real-time market prices,
              eBay sales, and PSA graded comps.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-xs font-semibold">
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
              <span className="text-emerald-700 font-mono text-sm font-bold">1,025</span>
              <span className="text-slate-600">Pokémon</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
              <span className="text-cyan-700 font-mono text-sm font-bold">54,480+</span>
              <span className="text-slate-600">Cards Tracked</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
              <span className="text-amber-700 font-mono text-sm font-bold">482</span>
              <span className="text-slate-600">Sets Indexed</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
              <span className="text-indigo-700 font-mono text-sm font-bold">17,400+</span>
              <span className="text-slate-600">Verified Comps</span>
            </div>
          </div>
        </div>
      </section>

      {/* Control Bar: Search, Filters & Sorting (Non-sticky) */}
      <div className="mb-8 rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          {/* Search Input & Evolution Toggle */}
          <div className="flex flex-1 items-center gap-2">
            <div className="relative flex-1">
              <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </span>
              <input
                type="text"
                value={query}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search by Pokémon name or #dex (e.g. Charizard, #0025, Gengar)..."
                className="w-full rounded-xl border border-slate-200 bg-slate-50/80 py-2.5 pl-10 pr-10 text-sm font-medium text-slate-900 placeholder:text-slate-400 transition focus:border-emerald-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => handleSearchChange("")}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-xs font-bold text-slate-400 hover:text-slate-700"
                  aria-label="Clear search"
                >
                  ✕
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => setShowEvolutions((prev) => !prev)}
              title={
                showEvolutions
                  ? "Evolutions enabled: Showing matched Pokémon and their full evolution lines"
                  : "Evolutions disabled: Showing direct name/dex matches only"
              }
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl border px-3 py-2.5 text-xs font-bold transition shadow-2xs active:scale-95 ${
                showEvolutions
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100/90 shadow-xs"
                  : "border-slate-200 bg-slate-50 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
              }`}
            >
              {/* <span className="text-sm"></span> */}
              <span className="hidden sm:inline">Evolutions</span>
              <span
                className={`inline-block h-2 w-2 rounded-full transition-colors ${
                  showEvolutions ? "bg-emerald-500 shadow-xs" : "bg-slate-300"
                }`}
              />
            </button>
          </div>

          {/* Sort Dropdown & Stats */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label htmlFor="pokedex-sort" className="text-xs font-semibold text-slate-500">
                Sort:
              </label>
              <select
                id="pokedex-sort"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortOption)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 transition hover:bg-white focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
              >
                <option value="id_asc">Dex # (Low → High)</option>
                <option value="id_desc">Dex # (High → Low)</option>
                <option value="name_asc">Name (A → Z)</option>
                <option value="name_desc">Name (Z → A)</option>
              </select>
            </div>

            <div className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold text-slate-700">
              Showing{" "}
              <span className="text-emerald-700 font-mono">{displayedPokemon.length}</span> of{" "}
              <span className="text-slate-900 font-mono">{filteredPokemon.length}</span>
              {hasEvolutionsActive && (
                <span className="ml-1 text-slate-500 font-normal hidden sm:inline">
                  (incl. evolutions)
                </span>
              )}
            </div>

            {hasActiveFilters && (
              <button
                type="button"
                onClick={resetAllFilters}
                className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700 transition hover:bg-rose-100"
              >
                Reset Filters
              </button>
            )}
          </div>
        </div>

        {/* Active Search & Evolution Mode Banner */}
        {query.trim() && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2.5 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 font-medium">Search mode:</span>
              {showEvolutions ? (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1 font-bold text-emerald-800 border border-emerald-200/80 shadow-2xs">
                  <span>Showing matches + full evolution lines</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 font-bold text-slate-600 border border-slate-200 shadow-2xs">
                  <span>Showing direct name matches only</span>
                </span>
              )}
            </div>
            {hasEvolutionsActive && directMatchIds.size > 0 && (
              <span className="text-[11px] font-medium text-slate-500">
                Matched <strong className="text-slate-700">{directMatchIds.size}</strong> {directMatchIds.size === 1 ? "family" : "families"}
              </span>
            )}
          </div>
        )}

        {/* Generation Filter Tabs */}
        <div className="mt-4 flex items-center gap-1.5 overflow-x-auto pb-1 text-xs font-semibold scrollbar-none">
          <button
            type="button"
            onClick={() => handleGenClick(null)}
            className={`whitespace-nowrap rounded-xl px-3.5 py-1.5 transition ${
              selectedGen === null
                ? "bg-slate-900 text-white shadow-sm font-bold"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-950"
            }`}
          >
            All Gens (1,025)
          </button>
          {GENERATION_REGIONS.map((g) => (
            <button
              key={g.gen}
              type="button"
              onClick={() => handleGenClick(g.gen)}
              className={`whitespace-nowrap rounded-xl px-3 py-1.5 transition ${
                selectedGen === g.gen
                  ? "bg-emerald-600 text-white shadow-sm font-bold"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-950"
              }`}
            >
              Gen {g.gen} ({g.region})
            </button>
          ))}
        </div>

        {/* Pokémon Type Filter Pills */}
        <div className="mt-3 flex flex-wrap items-center gap-1.5 pt-2 border-t border-slate-100">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mr-1">
            Types:
          </span>
          {(Object.keys(TYPE_THEMES) as PokemonType[]).map((typeKey) => {
            const theme = TYPE_THEMES[typeKey];
            const isSelected = selectedType === typeKey;
            return (
              <button
                key={typeKey}
                type="button"
                onClick={() => handleTypeClick(typeKey)}
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition ${
                  isSelected
                    ? `${theme.badge} ring-2 ring-offset-1 shadow-sm scale-105`
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                }`}
                style={isSelected ? { boxShadow: `0 0 12px ${theme.glow}` } : undefined}
              >
                <span>{theme.name}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Pokémon Grid */}
      {filteredPokemon.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-sm">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <h3 className="mt-3 text-lg font-bold text-slate-900">No Pokémon Found</h3>
          <p className="mt-1 text-sm text-slate-500">
            No Pokémon matches your search for &ldquo;{query}&rdquo; with the selected filters.
          </p>
          <button
            type="button"
            onClick={resetAllFilters}
            className="mt-4 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-emerald-700"
          >
            Clear All Filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {displayedPokemon.map((p, index) => {
            const isNewGen =
              !hasEvolutionsActive &&
              sortBy.startsWith("id") &&
              (index === 0 || p.generation !== displayedPokemon[index - 1].generation);
            const genInfo = isNewGen ? getGenerationInfo(p.generation) : null;
            const roman = genInfo ? ROMAN_NUMERALS[genInfo.gen - 1] || String(genInfo.gen) : "";

            const evoRelation = hasEvolutionsActive
              ? getEvolutionRelation(p.id, directMatchIds, (id) => POKEDEX_DATA[id - 1]?.name)
              : null;

            return (
              <Fragment key={p.id}>
                {isNewGen && genInfo && (
                  <div className="col-span-full mt-8 mb-2 first:mt-0">
                    <div className="flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-slate-50/90 px-4 py-2.5 sm:px-5 sm:py-3 shadow-2xs">
                      <span className="flex h-7 w-7 sm:h-8 sm:w-8 items-center justify-center rounded-xl bg-slate-900 font-mono text-xs font-black text-white shadow-xs">
                        {roman}
                      </span>
                      <div className="flex flex-wrap items-baseline gap-2 sm:gap-3">
                        <h2 className="font-mono text-xs sm:text-sm font-black tracking-tight text-slate-900 uppercase">
                          Generation {roman} · {genInfo.region}
                        </h2>
                        <span className="font-mono text-[11px] sm:text-xs font-bold text-emerald-700">
                          #{genInfo.range}
                        </span>
                        <span className="font-mono text-[11px] sm:text-xs text-slate-500">
                          ({genInfo.count} Pokémon)
                        </span>
                      </div>
                      <div className="hidden sm:block h-px flex-1 bg-slate-200/80" />
                    </div>
                  </div>
                )}
                <PokemonCard
                  pokemon={p}
                  isRestored={restoredPokemonId === p.id}
                  evolutionRelation={evoRelation}
                  onSelect={saveScrollState}
                />
              </Fragment>
            );
          })}
        </div>
      )}

      {/* Infinite Scroll / Progressive Loading Controls */}
      {filteredPokemon.length > 0 && (
        <div className="mt-12 flex flex-col items-center justify-center gap-4">
          {/* Progress bar */}
          <div className="w-full max-w-md">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 mb-1.5">
              <span>
                Showing <strong className="text-slate-900">{displayedPokemon.length}</strong> of{" "}
                <strong className="text-slate-900">{filteredPokemon.length}</strong> Pokémon
              </span>
              <span className="font-mono text-emerald-700 font-bold">
                {Math.round((displayedPokemon.length / filteredPokemon.length) * 100)}%
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-300"
                style={{ width: `${(displayedPokemon.length / filteredPokemon.length) * 100}%` }}
              />
            </div>
          </div>

          {hasMore ? (
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                onClick={loadMore}
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-6 py-2.5 text-xs font-bold text-white shadow-md transition hover:bg-emerald-700 hover:shadow-lg active:scale-95"
              >
                <span>
                  Load More (+{Math.min(BATCH_SIZE, filteredPokemon.length - displayedPokemon.length)})
                </span>
                <span>↓</span>
              </button>

              <button
                type="button"
                onClick={loadAll}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50 active:scale-95"
              >
                <span>Show All ({filteredPokemon.length})</span>
              </button>
            </div>
          ) : (
            <div className="rounded-full bg-emerald-50 border border-emerald-200/80 px-4 py-1.5 text-xs font-bold text-emerald-800 flex items-center gap-1.5">
              <span>✓</span>
              <span>All {filteredPokemon.length} Pokémon loaded</span>
            </div>
          )}

          {/* Sentinel element for infinite scroll auto-trigger */}
          {hasMore && <div ref={sentinelRef} className="h-6 w-full pointer-events-none" />}
        </div>
      )}

      {/* Floating Back To Top Button */}
      <BackToTop threshold={600} />
    </div>
  );
}

function PokemonCard({
  pokemon,
  isRestored,
  evolutionRelation,
  onSelect,
}: {
  pokemon: PokedexEntry;
  isRestored?: boolean;
  evolutionRelation?: EvolutionRelation | null;
  onSelect?: (id: number) => void;
}) {
  const primaryType = pokemon.types[0] || "normal";
  const theme = TYPE_THEMES[primaryType];
  const isDirect = evolutionRelation?.type === "direct";

  return (
    <div
      id={`pokemon-card-${pokemon.id}`}
      onClickCapture={() => onSelect?.(pokemon.id)}
      className={`group relative flex flex-col justify-between overflow-hidden rounded-2xl border p-3.5 shadow-sm transition-all duration-300 hover:-translate-y-1.5 hover:shadow-xl ${
        isRestored
          ? "border-emerald-500 bg-emerald-50/40 ring-2 ring-emerald-500/80 shadow-md"
          : isDirect
          ? "border-amber-300/80 bg-white ring-1 ring-amber-300/40 shadow-sm hover:border-amber-400"
          : "border-slate-200/90 bg-white hover:border-slate-300"
      }`}
      style={{
        boxShadow: isRestored
          ? "0 4px 14px -2px rgba(16, 185, 129, 0.2)"
          : isDirect
          ? "0 2px 10px -2px rgba(245, 158, 11, 0.15)"
          : "0 2px 8px -2px rgba(0,0,0,0.05)",
      }}
    >
      {/* Background glowing gradient circle */}
      <div
        className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full opacity-15 blur-xl transition-opacity duration-300 group-hover:opacity-40"
        style={{ background: theme.glow }}
      />

      <div>
        {/* Top bar: Dex number and Region */}
        <div className="flex items-center justify-between text-[11px] font-mono font-bold text-slate-400">
          <span className="tracking-wider text-slate-500 font-semibold">
            {formatDexNumber(pokemon.id)}
          </span>
          <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
            Gen {pokemon.generation}
          </span>
        </div>

        {/* Artwork with 3D scale hover */}
        <Link
          href={`/pokemon/${pokemon.id}`}
          onClick={() => {
            onSelect?.(pokemon.id);
          }}
          className="relative mt-2 flex h-32 w-full items-center justify-center overflow-hidden rounded-xl bg-slate-50/70 p-2 transition-colors duration-300 group-hover:bg-slate-100/80"
        >
          <div className="relative h-28 w-28 transition-transform duration-300 ease-out group-hover:scale-110">
            <Image
              src={pokemon.artwork}
              alt={pokemon.name}
              fill
              sizes="(max-width: 640px) 150px, (max-width: 1024px) 200px, 250px"
              className="object-contain drop-shadow-md transition-all duration-300"
              loading="lazy"
            />
          </div>
        </Link>

        {/* Name & Evolution Badge */}
        <div className="mt-3">
          {evolutionRelation && (
            <div className="mb-1.5 flex items-center">
              {evolutionRelation.type === "direct" ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold text-amber-700 border border-amber-200/80 shadow-2xs">
                  <span>★ Direct Match</span>
                  <span className="text-amber-600/75 font-normal">({evolutionRelation.stageName})</span>
                </span>
              ) : evolutionRelation.type === "pre-evolution" ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 border border-indigo-200/80 shadow-2xs">
                  <span>Pre-Evo</span>
                  <span className="text-indigo-600/75 font-normal">({evolutionRelation.stageName})</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200/80 shadow-2xs">
                  <span>Evolution</span>
                  <span className="text-emerald-600/75 font-normal">({evolutionRelation.stageName})</span>
                </span>
              )}
            </div>
          )}
          <Link
            href={`/pokemon/${pokemon.id}`}
            onClick={() => {
              onSelect?.(pokemon.id);
            }}
            className="block text-sm font-black tracking-tight text-slate-900 transition hover:text-emerald-600 line-clamp-1"
          >
            {pokemon.name}
          </Link>
        </div>

        {/* Type Badges */}
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {pokemon.types.map((t) => {
            const tTheme = TYPE_THEMES[t];
            return (
              <span
                key={t}
                className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white shadow-2xs ${tTheme.badge}`}
              >
                <span>{tTheme.name}</span>
              </span>
            );
          })}
        </div>
      </div>

      {/* Action footer: View cards */}
      <div className="mt-4 pt-2.5 border-t border-slate-100">
        <Link
          href={`/pokemon/${pokemon.id}`}
          onClick={() => onSelect?.(pokemon.id)}
          className="flex items-center justify-between rounded-xl bg-slate-50 px-2.5 py-1.5 text-[11px] font-bold text-slate-700 transition hover:bg-emerald-600 hover:text-white group/btn"
        >
          <span>View Cards</span>
          <span className="transition-transform group-hover/btn:translate-x-0.5">→</span>
        </Link>
      </div>
    </div>
  );
}
