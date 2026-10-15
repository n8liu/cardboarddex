import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HomeLiveStats } from "@/components/home-live-stats";
import { HomeTrendingCard } from "@/components/home-trending-card";
import { getHomeStats, getTrendingDashboard } from "@/lib/api";
vi.mock("@/lib/api", () => ({ getHomeStats: vi.fn(), getTrendingDashboard: vi.fn(), cardImageUrl: (url: string) => url }));
vi.mock("@/components/card-image", () => ({ default: ({ alt }: { alt: string }) => <span role="img" aria-label={alt} /> }));
const totals = { products: 100, sets: 10, price_observations: 1000, calculated_at: "2026-10-14" };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(getHomeStats).mockResolvedValue(totals); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

it("refreshes totals each minute, pauses while hidden, and refreshes on return", async () => {
  vi.useFakeTimers();
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  render(<HomeLiveStats />);
  await act(async () => {});
  expect(screen.getByText("1,000", { selector: ".sr-only" })).toBeInTheDocument();
  vi.mocked(getHomeStats).mockResolvedValue({ ...totals, price_observations: 1200 });
  await act(async () => { vi.advanceTimersByTime(60_000); });
  expect(screen.getByText("1,200", { selector: ".sr-only" })).toBeInTheDocument();
  hidden.mockReturnValue(true);
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); vi.advanceTimersByTime(120_000); });
  expect(getHomeStats).toHaveBeenCalledTimes(2);
  hidden.mockReturnValue(false);
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
  expect(getHomeStats).toHaveBeenCalledTimes(3);
});

it("retains last totals and explains a refresh failure", async () => {
  vi.useFakeTimers();
  vi.spyOn(console, "error").mockImplementation(() => {});
  render(<HomeLiveStats />); await act(async () => {});
  vi.mocked(getHomeStats).mockRejectedValue(new Error("offline"));
  await act(async () => { vi.advanceTimersByTime(60_000); });
  expect(screen.getByText(/Showing last available totals/)).toBeInTheDocument();
  expect(screen.getByText("1,000", { selector: ".sr-only" })).toBeInTheDocument();
});

it("chooses only from the top 50 and keeps the card stable across rerenders", async () => {
  vi.spyOn(Math, "random").mockReturnValue(0.999);
  const cards = Array.from({ length: 51 }, (_, i) => ({ rank: i + 1, card_id: `card-${i + 1}`, name: `Card ${i + 1}`, set_name: "Test set", image_url: "/image", market_price: 25, clicks_count: 1, trend_score: 1, trend_direction: "up" as const }));
  vi.mocked(getTrendingDashboard).mockResolvedValue({ timeframe: "7d", trending_cards: cards, trending_pokemon: [], volume_pokemon: [], total_volume_usd: 0, total_sales_count: 0, updated_at: "2026-10-14" });
  const { rerender } = render(<HomeTrendingCard />);
  expect(await screen.findByRole("img", { name: "Card 50" })).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.queryByText("$25.00")).not.toBeInTheDocument();
  expect(screen.queryByText("Test set")).not.toBeInTheDocument();
  rerender(<HomeTrendingCard />);
  expect(getTrendingDashboard).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("Card 51")).not.toBeInTheDocument();
});

it("does not overlap requests and aborts an outstanding refresh on unmount", async () => {
  vi.useFakeTimers();
  vi.mocked(getHomeStats).mockImplementation(() => new Promise(() => {}));
  const { unmount } = render(<HomeLiveStats />);
  await act(async () => { vi.advanceTimersByTime(180_000); });
  expect(getHomeStats).toHaveBeenCalledTimes(1);
  const signal = vi.mocked(getHomeStats).mock.calls[0][0];
  unmount();
  expect(signal?.aborted).toBe(true);
});
