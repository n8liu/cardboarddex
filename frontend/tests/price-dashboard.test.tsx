import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PriceDashboard } from "@/components/price-dashboard";
import type { CardPricing, PriceObservation } from "@/types/card";
vi.mock("next/dynamic", () => ({ default: () => () => null }));
afterEach(cleanup);
const observation: PriceObservation = { provider: "tcgapi", provider_card_id: "card", variant_id: "normal", condition: null, printing: "Normal", grading_company: null, grade: null, price: 100, currency: "USD", observed_at: "2026-10-01", provider_updated_at: null, price_change_24h: 1, price_change_7d: 75, price_change_30d: 90 };
it("retains the dated legacy snapshot without presenting retired momentum as current", () => {
  const pricing: CardPricing = { card_id: "card", provider_states: [], observations: [observation], tcg_market_prices: [{ ...observation, price: 110, price_change_7d: -4, price_change_30d: null }], avg_listing_price: 30, median_listing_price: 25, listing_sample_count: 3 };
  render(<PriceDashboard pricing={pricing} />);
  const tcg = screen.getByText("Market Price").closest('.rounded-2xl') as HTMLElement;
  expect(within(tcg).getByText("$110.00", { selector: ".sr-only" })).toBeInTheDocument();
  expect(tcg).not.toHaveTextContent("24h:");
  expect(tcg).toHaveTextContent(/Legacy market|Last known/);
  expect(tcg).not.toHaveTextContent("7d:");
  expect(tcg).not.toHaveTextContent("30d:");
  const average = screen.getByText("Avg Listing (Raw, 7d)").parentElement!;
  expect(within(average).getByText("$30.00", { selector: ".sr-only" })).toBeInTheDocument();
  expect(average).toHaveTextContent("past 7 days");
  const median = screen.getByText("Median Listing (Raw, 7d)").parentElement!;
  expect(within(median).getByText("$25.00", { selector: ".sr-only" })).toBeInTheDocument();
});
it("never labels an eBay quote as the TCG market price", () => {
  render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], observations: [{ ...observation, provider: "ebay" }], tcg_market_prices: [] }} />);
  const tcg = screen.getByText("Market Price").closest('.rounded-2xl') as HTMLElement;
  expect(tcg).toHaveTextContent("—");
  expect(tcg).not.toHaveTextContent("$100");
});

it.each([undefined, []])("falls back to the newest raw TCG graph quote when snapshots are %s", (snapshots) => {
  render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], tcg_market_prices: snapshots, observations: [
    observation,
    { ...observation, price: 120, observed_at: "2026-10-15" },
    { ...observation, provider: "ebay", price: 500, observed_at: "2026-10-16" },
    { ...observation, variant_id: "graded", grading_company: "PSA", grade: 10, price: 900, observed_at: "2026-10-16" },
  ] }} />);
  const tcg = screen.getByText("Market Price").closest('.rounded-2xl') as HTMLElement;
  expect(within(tcg).getByText("$120.00", { selector: ".sr-only" })).toBeInTheDocument();
  expect(tcg).toHaveTextContent(/Legacy market|Last known/);
  expect(tcg).not.toHaveTextContent("7d:");
  expect(tcg).not.toHaveTextContent("30d:");
});

it("uses backend eligible groups and discloses excluded listings", async () => {
  const { fireEvent } = await import("@testing-library/react");
  render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], observations: [observation],
    eligibility_version: "identity-v1", selected_printing: "Holofoil", selected_condition: "Near Mint",
    lowest_matched_price: 30, listing_sample_count: 3, listing_seller_count: 2,
    listing_groups: [
      { printing: "Holofoil", condition: "Near Mint", lowest_matched_price: 30, avg_listing_price: 60, median_listing_price: 60, listing_sample_count: 3, listing_seller_count: 2 },
      { printing: "Holofoil", condition: "Damaged", lowest_matched_price: 5, avg_listing_price: null, median_listing_price: null, listing_sample_count: 1, listing_seller_count: 1 },
    ], excluded_listing_count: 1, unconfirmed_listings: [{ item_id: "bad", title: "Uncertain card", status: "uncertain", reasons: ["image_identifier_unreadable"] }],
  }} />);
  expect(screen.getByText("Lowest Matched Listing")).toBeInTheDocument();
  expect(screen.queryByText("Lowest Verified (Raw)")).not.toBeInTheDocument();
  expect(screen.getByText("Unconfirmed listings (1) · Excluded from statistics")).toBeInTheDocument();
  expect(screen.getByText(/image identifier unreadable/)).toBeInTheDocument();
  const lowest = screen.getByText("Lowest Matched Listing").parentElement!;
  expect(within(lowest).getByText("$30.00", { selector: ".sr-only" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("eBay comparison group"), { target: { value: JSON.stringify(["Holofoil", "Damaged"]) } });
  expect(within(lowest).getByText("$5.00", { selector: ".sr-only" })).toBeInTheDocument();
  expect(screen.getAllByText(/Insufficient comparable listings/)).toHaveLength(2);
});

it("prefers PPT market and seven-day PSA medians while retaining dated legacy quotes", () => {
  const quote = { provider: "pokemonpricetracker", language: "english", currency: "USD", printing: "Holofoil", condition: "Lightly Played", grade: null, metric: "market", price: 140, price_date: "2026-10-16", fetched_at: "2026-10-16T12:00:00Z", stale: false, primary: true, price_change_7d: 10 };
  render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], observations: [observation], ppt_mapped: true,
    provider_quotes: [quote, { ...quote, primary: false, grade: "psa10", metric: "median_7d", price: 500 }],
  }} />);
  const market = screen.getByText("Market Price").closest('.rounded-2xl') as HTMLElement;
  expect(within(market).getByText("$140.00", { selector: ".sr-only" })).toBeInTheDocument();
  expect(market).toHaveTextContent("Lightly Played");
  expect(market).toHaveTextContent("7d: +10.0%");
  expect(screen.getByText("PSA 10 · 7-day median").parentElement).toHaveTextContent("$500.00");
  expect(screen.getByRole("button", { name: "6 Months" })).toBeInTheDocument();
});

it("does not substitute a historical graded listing for missing recent PPT median", () => {
  render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], ppt_mapped: true,
    observations: [{ ...observation, provider: "ebay", grading_company: "PSA", grade: 10, price: 900 }], provider_quotes: [],
  }} />);
  const metric = screen.getByText("PSA 10 · 7-day median").parentElement!;
  expect(metric).toHaveTextContent("—");
  expect(metric).not.toHaveTextContent("900");
});

it("defaults the price history to every printing on, grading companies off and 3 months", () => {
  const base = { provider: "market", language: "english", currency: "USD", metric: "market", fetched_at: "2026-10-16", points: [] };
  render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], observations: [], ppt_mapped: true, market_history_series: [
    { ...base, id: "holo", printing: "Holofoil", condition: "Near Mint", grade: null },
    { ...base, id: "rev", printing: "Reverse Holofoil", condition: "Near Mint", grade: null },
    ...["psa10", "psa9", "psa8"].map((grade) => ({ ...base, id: grade, printing: null, condition: null, grade, metric: "daily_average" })),
    { ...base, id: "cgc10", printing: null, condition: null, grade: "cgc10", metric: "daily_average" },
    { ...base, id: "bgs9_5", printing: null, condition: null, grade: "bgs9_5", metric: "daily_average" },
  ] }} />);
  const printings = screen.getByRole("group", { name: "Printings" });
  expect(within(printings).getByRole("button", { name: "Holofoil" })).toHaveAttribute("aria-pressed", "true");
  expect(within(printings).getByRole("button", { name: "Reverse Holofoil" })).toHaveAttribute("aria-pressed", "true");
  const graded = screen.getByRole("group", { name: "Graded" });
  const psa = within(graded).getByRole("button", { name: /PSA/ });
  expect(psa).toHaveAttribute("aria-pressed", "false");
  expect(psa).toHaveTextContent("3");
  expect(within(graded).getByRole("button", { name: /CGC/ })).toHaveAttribute("aria-pressed", "false");
  expect(within(graded).getByRole("button", { name: /BGS/ })).toHaveTextContent("1");
  // Companies without history get no toggle at all.
  expect(within(graded).queryByRole("button", { name: /TAG|SGC/ })).toBeNull();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  fireEvent.click(psa);
  expect(psa).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(within(printings).getByRole("button", { name: "Holofoil" }));
  expect(within(printings).getByRole("button", { name: "Holofoil" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("button", { name: "3 Months" })).toHaveAttribute("aria-pressed", "true");
});

it("keeps variants with a shared provider card ID distinct while sorting", () => {
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  try {
    const variants = [
      { ...observation, price: 100, printing: "Normal" },
      { ...observation, price: 200, printing: "Holofoil" },
      { ...observation, price: 900, grading_company: "PSA", grade: 10 },
    ];
    render(<PriceDashboard pricing={{ card_id: "card", provider_states: [], observations: variants }} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    fireEvent.click(within(table).getByText("Market price"));
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    for (const price of ["$100.00", "$200.00", "$900.00"]) {
      expect(within(table).getByText(price)).toBeInTheDocument();
    }
    expect(errors.mock.calls.filter(args => args.some(arg => String(arg).includes("same key")))).toEqual([]);
  } finally {
    errors.mockRestore();
  }
});
