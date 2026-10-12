import type { CardSummary } from "@/types/card";

/** Match the catalog's legacy sealed classification using the data already on the page. */
export function isSealedProduct(card: CardSummary): boolean {
  const rarity = card.rarity?.trim().toLowerCase();
  return !rarity || rarity === "none";
}

export function summarizeDisplayedCards(cards: CardSummary[]) {
  let highestCard: CardSummary | null = null;
  let totalPrice = 0;
  let pricedCount = 0;
  for (const card of cards) {
    const price = card.market_price;
    if (price == null || !Number.isFinite(price) || price < 0) continue;
    totalPrice += price;
    pricedCount += 1;
    if (!isSealedProduct(card) && (!highestCard || price > highestCard.market_price!)) highestCard = card;
  }
  return {
    count: cards.length,
    highestCard,
    totalPrice: cards.length === 0 || pricedCount > 0 ? totalPrice : null,
    pricedCount,
    missingCount: cards.length - pricedCount,
  };
}
