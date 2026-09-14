import { Suspense } from "react";

import { CatalogBrowser } from "@/components/catalog-browser";
import { getCardSets, getSetStats, searchCards } from "@/lib/api";
import type { CardSort, GameLanguage, SetStats } from "@/types/card";

export const dynamic = "force-dynamic";
export const runtime = "edge";

type CatalogProps = {
  searchParams: Promise<{
    q?: string;
    set?: string;
    sort?: string;
    hide_sealed?: string;
    sealed?: string;
    game?: string;
    min_price?: string;
    max_price?: string;
  }>;
};

export default async function CatalogPage({ searchParams }: CatalogProps) {
  const params = await searchParams;
  const query = params.q?.trim() ?? "";
  const setId = params.set?.trim() ?? "";
  const game = (params.game as GameLanguage) || "all";
  const hideSealed = params.hide_sealed === "false" || params.sealed === "true" ? false : true;
  const validSorts: CardSort[] = ["price_desc", "price_asc", "number_asc", "number_desc", "name", "set"];
  const sortBy: CardSort = validSorts.includes(params.sort as CardSort)
    ? (params.sort as CardSort)
    : "price_desc";

  const rawMinPrice = params.min_price ? parseFloat(params.min_price) : undefined;
  const initialMinPrice = rawMinPrice !== undefined && !isNaN(rawMinPrice) ? rawMinPrice : null;
  const rawMaxPrice = params.max_price ? parseFloat(params.max_price) : undefined;
  const initialMaxPrice = rawMaxPrice !== undefined && !isNaN(rawMaxPrice) ? rawMaxPrice : null;

  let cards: Awaited<ReturnType<typeof searchCards>> = [];
  let sets: Awaited<ReturnType<typeof getCardSets>> = [];
  let initialSetStats: SetStats | null = null;

  try {
    const [fetchedCards, fetchedSets, fetchedSetStats] = await Promise.all([
      searchCards(query, {
        setId,
        sortBy,
        hideSealed,
        game,
        minPrice: initialMinPrice,
        maxPrice: initialMaxPrice,
      }),
      getCardSets(),
      setId
        ? getSetStats(setId, {
            q: query,
            hideSealed,
            game,
            minPrice: initialMinPrice,
            maxPrice: initialMaxPrice,
          }).catch((err) => {
            console.error("Failed fetching initial set stats:", err);
            return null;
          })
        : Promise.resolve(null),
    ]);
    cards = fetchedCards;
    sets = fetchedSets;
    initialSetStats = fetchedSetStats;
  } catch (err) {
    console.error("Failed fetching catalog cards or sets:", err);
  }

  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <Suspense fallback={null}>
        <CatalogBrowser
          initialCards={cards}
          initialHideSealed={hideSealed}
          initialMinPrice={initialMinPrice}
          initialMaxPrice={initialMaxPrice}
          initialQuery={query}
          initialSetId={setId}
          initialSetStats={initialSetStats}
          initialSortBy={sortBy}
          sets={sets}
        />
      </Suspense>
    </main>
  );
}
