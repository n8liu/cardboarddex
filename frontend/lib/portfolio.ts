import { getCard, getCardPricing, getPortfolioValuation } from "@/lib/api";
import type {
  PortfolioCardItem,
  PortfolioHistoryPoint,
  PortfolioValuationResponse,
} from "@/types/binder";

export async function fetchPortfolioDataWithFallback(
  cardIds: string[],
  days: number = 365
): Promise<PortfolioValuationResponse> {
  const uniqueIds = Array.from(new Set(cardIds.filter(Boolean)));
  if (uniqueIds.length === 0) {
    return {
      total_cards: 0,
      total_current_value: 0,
      currency: "USD",
      delta_24h_amount: 0,
      delta_24h_percent: 0,
      delta_7d_amount: 0,
      delta_7d_percent: 0,
      delta_30d_amount: 0,
      delta_30d_percent: 0,
      highest_value_card: null,
      cards: [],
      history: [],
    };
  }

  // 1. Try server batch portfolio endpoint
  try {
    const serverResult = await getPortfolioValuation(uniqueIds, days);
    if (serverResult && Array.isArray(serverResult.cards)) {
      return serverResult;
    }
  } catch (err) {
    console.warn(
      "[portfolio] Server batch valuation failed, falling back to client-side hydration:",
      err
    );
  }

  // 2. Client-side fallback: fetch cards in batches
  const cards: PortfolioCardItem[] = [];
  const cardHistories: { cardId: string; points: { date: string; price: number }[] }[] = [];

  // Four workers, one HTTP read at a time each: never fan out with binder size.
  const cardResults: PromiseSettledResult<{ id: string; detail: Awaited<ReturnType<typeof getCard>>; pricing: Awaited<ReturnType<typeof getCardPricing>> }>[] = [];
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(4, uniqueIds.length) }, async () => {
    while (cursor < uniqueIds.length) {
      const index = cursor++;
      const id = uniqueIds[index];
      const detail = await getCard(id).catch((error) => {
        console.error(`[portfolio] Card ${id} detail failed:`, error);
        return null;
      });
      const pricing = await getCardPricing(id).catch((error) => {
        console.error(`[portfolio] Card ${id} pricing failed:`, error);
        return null;
      });
      cardResults[index] = { status: "fulfilled", value: { id, detail, pricing } };
    }
  }));

  for (const res of cardResults) {
    if (res.status !== "fulfilled" || !res.value.detail) continue;
    const { id, detail, pricing } = res.value;

    let marketPrice = detail.market_price ?? 0;
    let p24: number | null = null;
    let p7: number | null = null;
    let p30: number | null = null;

    const quote = (pricing?.market_quotes ?? pricing?.provider_quotes ?? []).find(q => q.primary && !q.grade);
    if (quote) {
      marketPrice = quote.price;
      p24 = quote.stale ? null : quote.price_change_24h ?? null;
      p7 = quote.stale ? null : quote.price_change_7d ?? null;
      p30 = quote.stale ? null : quote.price_change_30d ?? null;
    }
    const series = (pricing?.market_history_series ?? []).filter(s => !s.grade && s.metric === "market" &&
      (!quote || (s.printing === quote.printing && [quote.condition, null, "Unknown"].includes(s.condition))));
    const selected = quote ? series : [...series].sort((a, b) => (b.points.at(-1)?.date ?? "").localeCompare(a.points.at(-1)?.date ?? "")).slice(0, 1);
    const points = new Map<string, number>();
    for (const s of selected) for (const point of s.points) if (point.price !== null) points.set(point.date, point.price);
    cardHistories.push({ cardId: id, points: [...points].map(([date, price]) => ({ date, price })) });

    cards.push({
      id: detail.id,
      name: detail.name,
      set_name: detail.set_name,
      number: detail.printed_total
        ? `${detail.number}/${detail.printed_total}`
        : detail.number,
      rarity: detail.rarity,
      image_url: detail.image_url,
      market_price: marketPrice > 0 ? marketPrice : null,
      market_currency: "USD",
      price_status: quote ? (quote.stale ? "stale" : "recent") : marketPrice > 0 ? "legacy" : "unavailable",
      price_date: quote?.price_date ?? null,
      market_source: quote?.provider ?? detail.market_source,
      price_change_24h: p24,
      price_change_7d: p7,
      price_change_30d: p30,
    });
  }

  // Sort descending by price
  cards.sort((a, b) => (b.market_price ?? 0) - (a.market_price ?? 0));
  const totalVal = cards.reduce((sum, c) => sum + (c.market_price ?? 0), 0);

  // Generate combined historical timeline
  const allDates = new Set<string>();
  for (const ch of cardHistories) {
    for (const pt of ch.points) {
      allDates.add(pt.date);
    }
  }

  const sortedDates = Array.from(allDates).sort();
  const history: PortfolioHistoryPoint[] = [];

  if (sortedDates.length > 0) {
    for (const d of sortedDates) {
      const runningPrices: Record<string, number> = {};
      for (const ch of cardHistories) {
        const matchingPt = ch.points.find((p) => p.date === d);
        if (matchingPt) {
          runningPrices[ch.cardId] = matchingPt.price;
        }
      }
      const dayTotal = Object.values(runningPrices).reduce((a, b) => a + b, 0);
      history.push({
        date: d,
        total_value: Math.round(dayTotal * 100) / 100,
        card_count: Object.keys(runningPrices).length,
      });
    }
  }

  return {
    total_cards: cards.length,
    total_current_value: Math.round(totalVal * 100) / 100,
    currency: "USD",
    delta_24h_amount: null,
    delta_24h_percent: null,
    delta_7d_amount: null,
    delta_7d_percent: null,
    delta_30d_amount: null,
    delta_30d_percent: null,
    highest_value_card: cards[0] ?? null,
    cards,
    history,
  };
}
