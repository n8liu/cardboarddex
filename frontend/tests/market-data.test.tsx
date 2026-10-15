import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MarketHistoryPanel, PriceFreshness, PurchaseReturn } from "@/components/market-history-panel";
import { SalesActivityPanel } from "@/components/sales-activity-panel";
import { CatalogHealth } from "@/components/admin/catalog-health";
import { getMarketHistory, getSalesActivity } from "@/lib/api";
import { adminRequest } from "@/lib/admin-api";
import type { MarketHistory, SalesActivity } from "@/types/market-data";
vi.mock("@/lib/api", () => ({ getMarketHistory: vi.fn(), getSalesActivity: vi.fn() }));
vi.mock("@/lib/admin-api", () => ({ adminRequest: vi.fn() }));
const history: MarketHistory = {
  card_id: "box", printing: "Normal", currency: "USD", days: 30, status: "ready", synced_at: "2026-10-11",
  coverage_start: "2026-09-11", coverage_end: "2026-10-11", return_end: "2026-10-11",
  return_percent: 0, complete_return_window: true, market_price: 100,
  market_price_as_of: "2026-09-01", price_age_days: 40, price_freshness: "stale", checked_at: "2026-10-11",
  points: [{ date: "2026-09-11", market_price: 100, sales_volume: null, avg_sales_price: null }, { date: "2026-10-11", market_price: 100, sales_volume: 0, avg_sales_price: null }],
};
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

it("distinguishes old prices from recent checks", () => {
  render(<PriceFreshness value={history} />);
  expect(screen.getByText(/Price dated 2026-09-01/)).toHaveTextContent("Stale price");
  expect(screen.getByText(/Provider checked 2026-10-11/)).toBeInTheDocument();
});

it("calculates purchase return and rejects zero or negative costs", () => {
  render(<PurchaseReturn price={120} />);
  const input = screen.getByLabelText("Your total purchase cost (USD)");
  fireEvent.change(input, { target: { value: "100" } });
  expect(screen.getByText(/Estimated unrealized return: \+20.0%/)).toBeInTheDocument();
  fireEvent.change(input, { target: { value: "0" } });
  expect(screen.getByText("Enter a positive cost to estimate your return.")).toBeInTheDocument();
  fireEvent.change(input, { target: { value: "-10" } });
  expect(screen.queryByText(/Estimated unrealized return:/)).not.toBeInTheDocument();
});

it("renders actual history, missing sales, and valid zero growth", async () => {
  vi.mocked(getMarketHistory).mockResolvedValue(history);
  render(<MarketHistoryPanel cardId="box" />);
  expect(await screen.findByText(/30-day price growth: 0.0%/)).toBeInTheDocument();
  expect(screen.getByText("Not reported")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Market price history/ })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Period"), { target: { value: "90" } });
  await waitFor(() => expect(getMarketHistory).toHaveBeenLastCalledWith("box", 90, expect.any(AbortSignal)));
});

it("shows unavailable history without fabricating a return", async () => {
  vi.mocked(getMarketHistory).mockResolvedValue({ ...history, points: [], coverage_start: null, coverage_end: null, return_percent: null, status: "restricted" });
  render(<MarketHistoryPanel cardId="box" />);
  expect(await screen.findByText(/30-day return unavailable/)).toBeInTheDocument();
  expect(screen.getByText(/Provider access is restricted/)).toBeInTheDocument();
});

it("shows unknown sales instead of a zero total and supports retry", async () => {
  vi.mocked(getSalesActivity).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
    days: 30, start: "2026-09-12", end: "2026-10-11", synced_at: null, total_sales: null,
    products_with_sales_data: 0, coverage: "", items: [],
  } satisfies SalesActivity);
  render(<SalesActivityPanel />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByText("Retry"));
  expect(await screen.findByText("Sales data unavailable for this selection.")).toBeInTheDocument();
});

it("loads catalog health only when expanded and displays discovered missing sets", async () => {
  vi.mocked(adminRequest).mockResolvedValue({ status: "ready", games: [{ game: "pokemon", fetched_at: "2026-10-11", provider_synced_at: null,
    local_set_count: 1, discovered_set_count: 2, provider_set_count: 2, local_card_count: 10, provider_card_count: 20,
    latest_sets: [{ id: "new", name: "New expansion", release_date: "2026-10-01", present_locally: false, local_card_count: 0, provider_card_count: 10 }], missing_sets: [],
  }] });
  render(<CatalogHealth />);
  expect(adminRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /Catalog coverage/ }));
  expect(await screen.findByText("New expansion · Not yet imported")).toBeInTheDocument();
  expect(screen.getByText(/1 \/ 2 discovered sets/)).toBeInTheDocument();
});

it("explains unsynced sales without presenting a zero", async () => {
  vi.mocked(getSalesActivity).mockResolvedValue({
    days: 30, start: "2026-09-12", end: "2026-10-11", synced_at: null,
    total_sales: null, products_with_sales_data: 0, coverage: "", items: [], status: "not_synced",
  });
  render(<SalesActivityPanel />);
  expect(await screen.findByText(/Sales history has not been synced yet/)).toBeInTheDocument();
  expect(screen.queryByText(/0 reported sales/)).not.toBeInTheDocument();
});
