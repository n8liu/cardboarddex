import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HistorySparkline, PriceFreshness, PurchaseReturn } from "@/components/market-history-panel";
import { CatalogHealth } from "@/components/admin/catalog-health";
import { adminRequest } from "@/lib/admin-api";
import type { MarketHistory } from "@/types/market-data";
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

it("connects recorded prices across unknown days without fabricating observations", () => {
  const { container } = render(<HistorySparkline points={[history.points[0],
    { date: "2026-09-20", market_price: null, sales_volume: null, avg_sales_price: null }, history.points[1]]} />);
  expect(container.querySelectorAll("polyline")).toHaveLength(1);
  expect(container.querySelector("polyline")?.getAttribute("points")?.split(" ")).toHaveLength(2);
});
