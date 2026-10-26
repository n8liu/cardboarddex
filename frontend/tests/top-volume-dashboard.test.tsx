import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TopVolumeDashboard } from "@/components/top-volume-dashboard";
import { getGradedSalesActivity, getTrendingDashboard } from "@/lib/api";
import type { TrendingDashboardResponse, VolumeTimeframe } from "@/types/card";

vi.mock("@/lib/api", () => ({
  getTrendingDashboard: vi.fn(), getGradedSalesActivity: vi.fn(), cardImageUrl: (src: string) => src,
}));
vi.mock("@/components/card-image", () => ({ default: () => null }));

const dashboard = (timeframe: VolumeTimeframe, clicks: number): TrendingDashboardResponse => ({
  timeframe, volume_pokemon: [], total_volume_usd: 0, total_sales_count: 0, updated_at: "2026-10-26T00:00:00Z",
  trending_cards: [{ rank: 1, card_id: "pika", name: "Pikachu", set_name: "Base", image_url: "/i", market_price: 5,
    clicks_count: clicks, trend_score: 1, trend_direction: "up" }],
  trending_pokemon: [],
} as TrendingDashboardResponse);

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getGradedSalesActivity).mockReturnValue(new Promise(() => {}));
});
afterEach(cleanup);

it("labels windowed counts as views and all-time counts as clicks", async () => {
  vi.mocked(getTrendingDashboard).mockImplementation(async ({ timeframe } = {}) =>
    timeframe === "all_time" ? dashboard("all_time", 40) : dashboard(timeframe ?? "7d", 3));
  render(<TopVolumeDashboard initialData={dashboard("7d", 3)} />);
  expect(await screen.findByText("3 views")).toBeVisible();
  expect(screen.getByText("Most viewed · last 7 days")).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "All" }));
  expect(await screen.findByText("40 clicks")).toBeVisible();
  expect(vi.mocked(getTrendingDashboard)).toHaveBeenLastCalledWith({ timeframe: "all_time" });
});
