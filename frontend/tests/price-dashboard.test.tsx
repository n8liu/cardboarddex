import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PriceDashboard } from "@/components/price-dashboard";
import type { CardPricing, PriceObservation } from "@/types/card";
vi.mock("next/dynamic", () => ({ default: () => () => null }));
afterEach(cleanup);
const observation: PriceObservation = { provider: "tcgapi", provider_card_id: "card", variant_id: "normal", condition: null, printing: "Normal", grading_company: null, grade: null, price: 100, currency: "USD", observed_at: "2026-10-01", provider_updated_at: null, price_change_24h: 1, price_change_7d: 75, price_change_30d: 90 };
it("uses current TCG fields and seven-day summaries, not historical percentages or listing prices", () => {
  const pricing: CardPricing = { card_id: "card", provider_states: [], observations: [observation], tcg_market_prices: [{ ...observation, price_change_7d: -4, price_change_30d: null }], avg_listing_price: 30, median_listing_price: 25, listing_sample_count: 3 };
  render(<PriceDashboard pricing={pricing} />);
  const tcg = screen.getByText("TCG Market Price").closest('.rounded-2xl') as HTMLElement;
  expect(tcg).toHaveTextContent("24h: +1.0%");
  expect(tcg).toHaveTextContent("7d: -4.0%");
  expect(tcg).not.toHaveTextContent("30d:");
  const average = screen.getByText("Avg Listing (Raw, 7d)").parentElement!;
  expect(within(average).getByText("$30.00", { selector: ".sr-only" })).toBeInTheDocument();
  expect(average).toHaveTextContent("past 7 days");
  const median = screen.getByText("Median Listing (Raw, 7d)").parentElement!;
  expect(within(median).getByText("$25.00", { selector: ".sr-only" })).toBeInTheDocument();
});
it("never labels an eBay quote as the TCG market price", () => {
  render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], observations: [{ ...observation, provider: "ebay" }], tcg_market_prices: [] }} />);
  const tcg = screen.getByText("TCG Market Price").closest('.rounded-2xl') as HTMLElement;
  expect(tcg).toHaveTextContent("—");
  expect(tcg).not.toHaveTextContent("$100");
});
