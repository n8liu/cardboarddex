import type { CardSummary } from "@/types/card";

const SEALED_KEYWORDS =
  /\b(booster[\s\-_]*(?:box|pack|bundle)|elite[\s\-_]+trainer[\s\-_]+box|\betb\b|blister|collection[\s\-_]*box|premium[\s\-_]*collection|special[\s\-_]*collection|mini[\s\-_]*tin|\btin\b|theme[\s\-_]*deck|battle[\s\-_]*deck|build[\s\-_]*&[\s\-_]*battle|display[\s\-_]*box|case)\b/i;

export type SealedCheckable = {
  name?: string | null;
  rarity?: string | null;
};

/** Match the catalog and market sealed classification using the data already on the card. */
export function isSealedProduct(card: SealedCheckable): boolean {
  if ("rarity" in card && card.rarity !== undefined) {
    const rarity = card.rarity?.trim().toLowerCase();
    if (!rarity || rarity === "none") return true;
  }
  if (card.name && (SEALED_KEYWORDS.test(card.name) || /code\s*card/i.test(card.name))) {
    return true;
  }
  return false;
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
