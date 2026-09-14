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

  const cardResults = await Promise.allSettled(
    uniqueIds.map(async (id) => {
      const [detail, pricing] = await Promise.all([
        getCard(id).catch(() => null),
        getCardPricing(id).catch(() => null),
      ]);
      return { id, detail, pricing };
    })
  );

  for (const res of cardResults) {
    if (res.status !== "fulfilled" || !res.value.detail) continue;
    const { id, detail, pricing } = res.value;

    let marketPrice = detail.market_price ?? 0;
    let p24: number | null = null;
    let p7: number | null = null;
    let p30: number | null = null;

    // Check pricing observations
    if (pricing && Array.isArray(pricing.observations)) {
      const tcgObs = pricing.observations.filter(
        (o) => o.provider === "tcgapi" && !o.grading_company
      );
      if (tcgObs.length > 0) {
        const latest = tcgObs[tcgObs.length - 1];
        if (latest.price) marketPrice = latest.price;
        p24 = latest.price_change_24h ?? null;
        p7 = latest.price_change_7d ?? null;
        p30 = latest.price_change_30d ?? null;
      }

      // Collect points
      const points = tcgObs
        .filter((o) => o.observed_at && o.price)
        .map((o) => ({
          date: o.observed_at.slice(0, 10),
          price: o.price,
        }));
      cardHistories.push({ cardId: id, points });
    }

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
    const runningPrices: Record<string, number> = {};
    for (const d of sortedDates) {
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

  const todayIso = new Date().toISOString().slice(0, 10);
  if (history.length === 0 || history[history.length - 1].date !== todayIso) {
    history.push({
      date: todayIso,
      total_value: Math.round(totalVal * 100) / 100,
      card_count: cards.length,
    });
  }

  return {
    total_cards: cards.length,
    total_current_value: Math.round(totalVal * 100) / 100,
    currency: "USD",
    delta_24h_amount: cards.reduce((s, c) => s + (c.price_change_24h ?? 0), 0) || null,
    delta_24h_percent: null,
    delta_7d_amount: cards.reduce((s, c) => s + (c.price_change_7d ?? 0), 0) || null,
    delta_7d_percent: null,
    delta_30d_amount: cards.reduce((s, c) => s + (c.price_change_30d ?? 0), 0) || null,
    delta_30d_percent: null,
    highest_value_card: cards[0] ?? null,
    cards,
    history,
  };
}
