"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CardGrid } from "@/components/card-grid";
import { CardTableView } from "@/components/card-table-view";
import { SearchForm } from "@/components/search-form";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { BackToTop } from "@/components/ui/back-to-top";
import { useCurrency } from "@/context/currency-context";
import { CARD_PAGE_SIZE, getCardSets, getSetStats, searchCards } from "@/lib/api";
import type { CardSetOption, CardSort, CardSummary, GameLanguage, SetStats } from "@/types/card";

function formatMoney(value: number | null | undefined, currency: string = "USD"): string {
  if (value === null || value === undefined) return "Price pending";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

type CatalogQuickFilter = "all" | "under10" | "10to50" | "grails" | "specials";

const QUICK_FILTERS: { id: CatalogQuickFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "under10", label: "Under $10" },
  { id: "10to50", label: "$10 – $50" },
  { id: "grails", label: "$100+ Grails" },
  { id: "specials", label: "Illustration / Specials" },
];

type CatalogBrowserProps = {
  initialCards: CardSummary[];
  initialHideSealed?: boolean;
  initialQuery: string;
  initialSetId: string;
  initialSetStats?: SetStats | null;
  initialSortBy: CardSort;
  sets: CardSetOption[];
};

export function CatalogBrowser({
  initialCards,
  initialHideSealed = true,
  initialQuery,
  initialSetId,
  initialSetStats = null,
  initialSortBy = "price_desc",
  sets,
}: CatalogBrowserProps) {
  const searchParams = useSearchParams();

  const getUrlParams = useCallback(() => {
    const params = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : searchParams;
    const q = params.get("q")?.trim() ?? initialQuery;
    const s = params.get("set")?.trim() ?? initialSetId;
    const validSorts: CardSort[] = ["price_desc", "price_asc", "number_asc", "number_desc", "name", "set"];
    const rawSort = params.get("sort") as CardSort;
    const sort = validSorts.includes(rawSort) ? rawSort : initialSortBy;
    const hs = params.get("hide_sealed") === "false" || params.get("sealed") === "true" ? false : true;
    const g = (params.get("game") as GameLanguage) || "all";
    return { q, s, sort, hs, g };
  }, [initialHideSealed, initialQuery, initialSetId, initialSortBy, searchParams]);

  const { formatPrice } = useCurrency();
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("cardboarddex_catalog_view");
      if (saved === "grid" || saved === "table") {
        setViewMode(saved);
      }
    } catch {}
  }, []);

  const handleViewModeChange = (mode: "grid" | "table") => {
    setViewMode(mode);
    try {
      localStorage.setItem("cardboarddex_catalog_view", mode);
    } catch {}
  };

  const [query, setQuery] = useState(initialQuery);
  const [setId, setSetId] = useState(initialSetId);
  const [sortBy, setSortBy] = useState<CardSort>(initialSortBy);
  const [hideSealed, setHideSealed] = useState(initialHideSealed);
  const [game, setGame] = useState<GameLanguage>("all");
  const [quickFilter, setQuickFilter] = useState<CatalogQuickFilter>("all");
  const [cards, setCards] = useState(initialCards);

  const displayedCards = useMemo(() => {
    if (quickFilter === "all") return cards;
    if (quickFilter === "under10") {
      return cards.filter((c) => c.market_price !== null && c.market_price < 10);
    }
    if (quickFilter === "10to50") {
      return cards.filter(
        (c) => c.market_price !== null && c.market_price >= 10 && c.market_price <= 50
      );
    }
    if (quickFilter === "grails") {
      return cards.filter((c) => c.market_price !== null && c.market_price >= 100);
    }
    if (quickFilter === "specials") {
      return cards.filter((c) => {
        const r = (c.rarity || "").toLowerCase();
        return (
          r.includes("illustration") ||
          r.includes("secret") ||
          r.includes("hyper") ||
          r.includes("special") ||
          r.includes("sir") ||
          r.includes("alt")
        );
      });
    }
    return cards;
  }, [cards, quickFilter]);

  const [setsList, setSetsList] = useState<CardSetOption[]>(sets);
  const [setStats, setSetStats] = useState<SetStats | null>(initialSetStats);
  const [isLoadingStats, setIsLoadingStats] = useState(false);
  const [hasMore, setHasMore] = useState(initialCards.length === CARD_PAGE_SIZE);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const isInitialized = useRef(false);
  const requestVersion = useRef(0);
  const loadingMoreRef = useRef(false);

  useEffect(() => {
    const { q, s, sort, hs, g } = getUrlParams();
    setQuery(q);
    setSetId(s);
    setSortBy(sort);
    setHideSealed(hs);
    setGame(g);

    if (!isInitialized.current) {
      isInitialized.current = true;
      if (q !== initialQuery || s !== initialSetId || sort !== initialSortBy || hs !== initialHideSealed) {
        void (async () => {
          setIsSearching(true);
          if (s) setIsLoadingStats(true);
          try {
            const [nextCards, nextStats] = await Promise.all([
              searchCards(q.trim(), { setId: s, sortBy: sort, hideSealed: hs, game: g }),
              s ? getSetStats(s, { q: q.trim(), hideSealed: hs, game: g }).catch(() => null) : Promise.resolve(null),
            ]);
            setCards(nextCards);
            setHasMore(nextCards.length === CARD_PAGE_SIZE);
            if (s) setSetStats(nextStats);
            else setSetStats(null);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Could not load cards.");
          } finally {
            setIsSearching(false);
            setIsLoadingStats(false);
          }
        })();
      } else if (initialCards.length === 0) {
        void (async () => {
          setIsSearching(true);
          if (s && !initialSetStats) setIsLoadingStats(true);
          try {
            const [nextCards, nextStats] = await Promise.all([
              searchCards(q.trim(), { setId: s, sortBy: sort, hideSealed: hs, game: g }),
              s && !initialSetStats
                ? getSetStats(s, { q: q.trim(), hideSealed: hs, game: g }).catch(() => null)
                : Promise.resolve(initialSetStats),
            ]);
            setCards(nextCards);
            setHasMore(nextCards.length === CARD_PAGE_SIZE);
            if (s) setSetStats(nextStats);
          } catch (err) {
            console.error("Failed fetching initial catalog cards on client:", err);
          } finally {
            setIsSearching(false);
            setIsLoadingStats(false);
          }
        })();
      }
    }
  }, [getUrlParams, initialCards.length, initialHideSealed, initialQuery, initialSetId, initialSortBy]);

  useEffect(() => {
    setSetsList(sets);
  }, [sets]);

  useEffect(() => {
    if (!sets || sets.length === 0) {
      void getCardSets().then((latestSets) => {
        if (latestSets && latestSets.length > 0) {
          setSetsList(latestSets);
        }
      }).catch(() => {});
    }
  }, [sets]);


  useEffect(() => {
    if (!isInitialized.current) return;

    const version = ++requestVersion.current;
    const timer = window.setTimeout(async () => {
      setIsSearching(true);
      if (setId) setIsLoadingStats(true);
      setError(null);
      try {
        const [nextCards, nextStats] = await Promise.all([
          searchCards(query.trim(), { setId, sortBy, hideSealed, game }),
          setId
            ? getSetStats(setId, { q: query.trim(), hideSealed, game }).catch((err) => {
                console.error("Failed fetching set stats:", err);
                return null;
              })
            : Promise.resolve(null),
        ]);
        if (requestVersion.current !== version) return;
        setCards(nextCards);
        setHasMore(nextCards.length === CARD_PAGE_SIZE);
        setSetStats(nextStats);

        const url = new URL(window.location.href);
        query.trim() ? url.searchParams.set("q", query.trim()) : url.searchParams.delete("q");
        setId ? url.searchParams.set("set", setId) : url.searchParams.delete("set");
        sortBy !== "price_desc" ? url.searchParams.set("sort", sortBy) : url.searchParams.delete("sort");
        !hideSealed ? url.searchParams.set("hide_sealed", "false") : url.searchParams.delete("hide_sealed");
        game !== "all" ? url.searchParams.set("game", game) : url.searchParams.delete("game");
        window.history.replaceState(null, "", `${url.pathname}${url.search}`);
      } catch (requestError) {
        if (requestVersion.current !== version) return;
        setError(requestError instanceof Error ? requestError.message : "Could not load cards.");
        setCards([]);
        setHasMore(false);
      } finally {
        if (requestVersion.current === version) {
          setIsSearching(false);
          setIsLoadingStats(false);
        }
      }
    }, 250);

    return () => window.clearTimeout(timer);
  }, [query, setId, sortBy, hideSealed, game]);

  const loadMore = useCallback(async () => {
    if (!hasMore || isSearching || loadingMoreRef.current) return;
    loadingMoreRef.current = true;
    setIsLoadingMore(true);
    const version = requestVersion.current;
    try {
      const nextCards = await searchCards(query.trim(), {
        offset: cards.length,
        setId,
        sortBy,
        hideSealed,
        game,
      });
      if (requestVersion.current !== version) return;
      setCards((current) => [...current, ...nextCards]);
      setHasMore(nextCards.length === CARD_PAGE_SIZE);
      setError(null);
    } catch (requestError) {
      if (requestVersion.current !== version) return;
      setError(requestError instanceof Error ? requestError.message : "Could not load more cards.");
    } finally {
      loadingMoreRef.current = false;
      setIsLoadingMore(false);
    }
  }, [cards.length, hasMore, isSearching, query, setId, sortBy, hideSealed, game]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { rootMargin: "320px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore]);

  const clearFilters = () => {
    setQuery("");
    setSetId("");
    setSetStats(null);
    setSortBy("price_desc");
    setHideSealed(true);
    setGame("all");
    setQuickFilter("all");
  };

  const handleSetChange = (newSetId: string) => {
    setSetId(newSetId);
  };

  const filteredSets = setsList.filter((s) => {
    if (game === "pokemon-japan") return s.series === "Pokemon Japan";
    if (game === "pokemon") return s.series !== "Pokemon Japan";
    return true;
  });

  const selectedSet = setsList.find((cardSet) => cardSet.id === setId);
  const resultsTitle = query.trim()
    ? `Results for “${query.trim()}”`
    : selectedSet
      ? selectedSet.name
      : "Browse cards";

  return (
    <section className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-10 sm:px-6 sm:pt-14 lg:px-8">
      <div className="max-w-4xl">
        <SearchForm
          isSearching={isSearching}
          onClear={() => setQuery("")}
          onQueryChange={setQuery}
          query={query}
        />

        {/* Quick Filter Chips */}
        <div className="mt-3 flex flex-wrap items-center gap-1.5 font-mono text-xs">
          <span className="text-slate-400 text-[11px] uppercase tracking-wider font-semibold mr-1">
            Filter:
          </span>
          {QUICK_FILTERS.map((chip) => {
            const isActive = quickFilter === chip.id;
            return (
              <button
                key={chip.id}
                type="button"
                onClick={() => setQuickFilter(chip.id)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  isActive
                    ? "bg-slate-900 text-white shadow-2xs"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-950"
                }`}
              >
                {chip.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-10 grid items-start gap-7 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_8px_28px_rgba(15,23,42,0.035)] lg:sticky lg:top-24">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-950">Browse</h2>
            {(setId || sortBy !== "price_desc" || !hideSealed || query || game !== "all") ? (
              <button className="text-xs font-semibold text-emerald-700 transition hover:text-emerald-900" onClick={clearFilters} type="button">
                Reset
              </button>
            ) : null}
          </div>

          {/* Region / Language Selector */}
          <div className="mt-5 block">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Language / Region</span>
            <div className="mt-2 grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1 text-[11px] font-bold">
              <button
                type="button"
                onClick={() => {
                  setGame("all");
                  setSetId("");
                }}
                className={`rounded-lg py-1.5 transition ${
                  game === "all" ? "bg-white text-slate-950 shadow-xs" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                ALL
              </button>
              <button
                type="button"
                onClick={() => {
                  setGame("pokemon");
                  setSetId("");
                }}
                className={`rounded-lg py-1.5 transition ${
                  game === "pokemon" ? "bg-white text-slate-950 shadow-xs" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => {
                  setGame("pokemon-japan");
                  setSetId("");
                }}
                className={`rounded-lg py-1.5 transition ${
                  game === "pokemon-japan" ? "bg-white text-red-950 shadow-xs font-black" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                JA
              </button>
            </div>
          </div>

          <label className="mt-5 block">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Set</span>
            <select
              className="mt-2 block h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
              onChange={(event) => handleSetChange(event.target.value)}
              value={setId}
            >
              <option value="">All sets ({filteredSets.length})</option>
              {filteredSets.map((cardSet) => <option key={cardSet.id} value={cardSet.id}>{cardSet.name}</option>)}
            </select>
          </label>

          <label className="mt-5 block">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Sort</span>
            <select
              className="mt-2 block h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
              onChange={(event) => setSortBy(event.target.value as CardSort)}
              value={sortBy}
            >
              <option value="price_desc">Price: High to Low</option>
              <option value="price_asc">Price: Low to High</option>
              <option value="number_asc">Card # (Lowest to Highest)</option>
              <option value="number_desc">Card # (Highest to Lowest)</option>
              <option value="name">Card name (A-Z)</option>
              <option value="set">Set & Release Date</option>
            </select>
          </label>

          <div className="mt-5 block">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
              {game === "pokemon-japan" ? "Rarity None" : "Products"}
            </span>
            <button
              type="button"
              onClick={() => setHideSealed((prev) => !prev)}
              className={`mt-2 flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-xs font-semibold transition ${
                hideSealed
                  ? "border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-300 hover:bg-slate-100"
                  : "border-emerald-500/30 bg-emerald-50 text-emerald-800 shadow-sm hover:bg-emerald-100/60"
              }`}
              aria-pressed={!hideSealed}
            >
              <span>{game === "pokemon-japan" ? "None" : "Sealed Products"}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  hideSealed ? "bg-slate-200 text-slate-600" : "bg-emerald-600 text-white"
                }`}
              >
                {hideSealed ? "Hidden" : "Shown"}
              </span>
            </button>
            <p className="mt-1.5 text-[11px] text-slate-400">
              {game === "pokemon-japan"
                ? (hideSealed ? "Hiding items with rarity None." : "Showing items with rarity None.")
                : (hideSealed ? "Hiding boxes, packs & bundles." : "Showing cards and sealed products.")}
            </p>
          </div>

          <div className="mt-6 border-t border-slate-100 pt-5">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Data</p>
            <div className="mt-3 space-y-2.5 text-sm text-slate-600">
              <p className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-emerald-500" /> TCG API catalog</p>
              <p className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-slate-300" /> eBay listings data</p>
            </div>
          </div>
        </aside>

        <div className="min-w-0">
          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-lg font-bold tracking-tight text-slate-950">{resultsTitle}</h2>
              <p aria-live="polite" className="mt-1 text-sm text-slate-500">
                {isSearching ? "Updating cards…" : `${displayedCards.length} card${displayedCards.length === 1 ? "" : "s"} loaded`}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {/* Grid / Table View Switcher */}
              <div className="flex items-center rounded-xl bg-slate-100 p-1 text-xs font-mono">
                <button
                  type="button"
                  onClick={() => handleViewModeChange("grid")}
                  className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition ${
                    viewMode === "grid"
                      ? "bg-white text-slate-950 shadow-xs font-bold"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                  title="Visual Card Grid View"
                  aria-label="Grid view"
                >
                  <span>⊞</span>
                  <span>Grid</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleViewModeChange("table")}
                  className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition ${
                    viewMode === "table"
                      ? "bg-white text-slate-950 shadow-xs font-bold"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                  title="Compact Trader Table View"
                  aria-label="Table view"
                >
                  <span>☰</span>
                  <span>Table</span>
                </button>
              </div>

              {setId ? (
                <div className="flex flex-col items-start sm:items-end">
                  <div
                    className={`group relative flex items-center gap-2.5 rounded-xl border border-emerald-600/25 bg-gradient-to-r from-emerald-500/10 via-emerald-500/5 to-teal-500/10 px-3.5 py-2 font-mono shadow-2xs backdrop-blur-xs transition-all hover:border-emerald-500/40 hover:shadow-sm ${
                      isLoadingStats ? "animate-pulse opacity-80" : ""
                    }`}
                    title={
                      setStats
                        ? `${setStats.priced_cards} of ${setStats.total_cards} cards verified with active market prices.`
                        : "Aggregating set total prices…"
                    }
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                      </span>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-800">
                        {query.trim() || quickFilter !== "all" ? "Filtered Total" : "Set Total"}
                      </span>
                    </div>

                    <div className="h-4 w-px bg-emerald-600/20" />

                    <span className="text-base font-black tracking-tight text-emerald-950 sm:text-lg">
                      <AnimatedNumber
                        value={
                          setStats && quickFilter === "all"
                            ? setStats.total_price
                            : displayedCards.reduce((sum, c) => sum + (c.market_price ?? 0), 0)
                        }
                        format={(val) => formatPrice(val)}
                      />
                    </span>

                    <span className="rounded-md bg-emerald-600/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800">
                      {setStats && quickFilter === "all"
                        ? `${setStats.priced_cards}/${setStats.total_cards} priced`
                        : `${displayedCards.filter((c) => c.market_price !== null).length} priced`}
                    </span>
                  </div>
                </div>
              ) : (
                <span className="hidden text-xs font-medium text-slate-400 sm:inline">Exact catalog matches</span>
              )}
            </div>
          </div>

          {error ? (
            <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">
              {error}
            </div>
          ) : null}

          <div className={isSearching ? "opacity-45 transition-opacity" : "transition-opacity"}>
            {viewMode === "grid" ? (
              <CardGrid cards={displayedCards} query={query || selectedSet?.name || ""} />
            ) : (
              <CardTableView cards={displayedCards} query={query || selectedSet?.name || ""} />
            )}
          </div>

          <div className="flex min-h-24 items-center justify-center" ref={sentinelRef}>
            {hasMore ? (
              <button
                className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-emerald-500 hover:text-emerald-800 disabled:cursor-wait disabled:opacity-60"
                disabled={isLoadingMore}
                onClick={() => void loadMore()}
                type="button"
              >
                {isLoadingMore ? "Loading more cards…" : "Load more cards"}
              </button>
            ) : cards.length > 0 ? (
              <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">End of results</p>
            ) : null}
          </div>
        </div>
      </div>

      <BackToTop />
    </section>
  );
}
