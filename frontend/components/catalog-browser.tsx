"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { CardGrid } from "@/components/card-grid";
import { SearchForm } from "@/components/search-form";
import { BackToTop } from "@/components/ui/back-to-top";
import { CARD_PAGE_SIZE, getCardSets, searchCards } from "@/lib/api";
import type { CardSetOption, CardSort, CardSummary, GameLanguage } from "@/types/card";

type CatalogBrowserProps = {
  initialCards: CardSummary[];
  initialHideSealed?: boolean;
  initialQuery: string;
  initialSetId: string;
  initialSortBy: CardSort;
  sets: CardSetOption[];
};

export function CatalogBrowser({
  initialCards,
  initialHideSealed = true,
  initialQuery,
  initialSetId,
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

  const [query, setQuery] = useState(initialQuery);
  const [setId, setSetId] = useState(initialSetId);
  const [sortBy, setSortBy] = useState<CardSort>(initialSortBy);
  const [hideSealed, setHideSealed] = useState(initialHideSealed);
  const [game, setGame] = useState<GameLanguage>("all");
  const [cards, setCards] = useState(initialCards);
  const [setsList, setSetsList] = useState<CardSetOption[]>(sets);
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
          try {
            const nextCards = await searchCards(q.trim(), { setId: s, sortBy: sort, hideSealed: hs, game: g });
            setCards(nextCards);
            setHasMore(nextCards.length === CARD_PAGE_SIZE);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Could not load cards.");
          } finally {
            setIsSearching(false);
          }
        })();
      }
    }
  }, [getUrlParams, initialHideSealed, initialQuery, initialSetId, initialSortBy]);

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
      setError(null);
      try {
        const nextCards = await searchCards(query.trim(), { setId, sortBy, hideSealed, game });
        if (requestVersion.current !== version) return;
        setCards(nextCards);
        setHasMore(nextCards.length === CARD_PAGE_SIZE);

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
        if (requestVersion.current === version) setIsSearching(false);
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
    setSortBy("price_desc");
    setHideSealed(true);
    setGame("all");
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
          <div className="mb-5 flex items-end justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold tracking-tight text-slate-950">{resultsTitle}</h2>
              <p aria-live="polite" className="mt-1 text-sm text-slate-500">
                {isSearching ? "Updating cards…" : `${cards.length} card${cards.length === 1 ? "" : "s"} loaded`}
              </p>
            </div>
            <span className="hidden text-xs font-medium text-slate-400 sm:inline">Exact catalog matches</span>
          </div>

          {error ? (
            <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">
              {error}
            </div>
          ) : null}

          <div className={isSearching ? "opacity-45 transition-opacity" : "transition-opacity"}>
            <CardGrid cards={cards} query={query || selectedSet?.name || ""} />
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
