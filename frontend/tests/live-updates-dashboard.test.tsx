import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useMemo } from "react";
import { LiveUpdatesDashboard } from "@/components/live-updates-dashboard";
import { getLiveFeed, getLiveStats } from "@/lib/api";
import type { LiveFeedResponse, LiveUpdateItem } from "@/types/card";

vi.mock("next/navigation", () => ({
  useSearchParams: () => useMemo(() => new URLSearchParams(window.location.search), []),
}));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(), getLiveFeed: vi.fn(), getLiveStats: vi.fn(),
}));

const item = (id: string, name: string, observedAt: string): LiveUpdateItem => ({
  id, card_id: id, card_name: name, set_name: "Base", set_id: "base", card_number: null,
  image_url: `/cards/${id}/image`, provider: "pokemonpricetracker", update_type: "market_update",
  price_date: observedAt, metric: "market", price: 10, currency: "USD", condition: "Near Mint",
  printing: "Holofoil", grading_company: null, grade: null, listing_title: null, listing_url: null,
  observed_at: observedAt,
} as LiveUpdateItem);
const feed = (items: LiveUpdateItem[]): LiveFeedResponse => ({
  page: 1, per_page: 24, has_more: false, items, updated_at: new Date().toISOString(),
});
const empty = feed([]);

beforeEach(() => {
  vi.useFakeTimers();
  window.history.replaceState(null, "", "/live-updates?provider=pokemonpricetracker");
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  vi.mocked(getLiveStats).mockReset().mockReturnValue(new Promise(() => {}));
  vi.mocked(getLiveFeed).mockReset();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

it("shows a PPT row ingested by the worker on the next poll without a reload", async () => {
  const old = item("1", "Pikachu", "2026-10-18T01:52:52Z");
  const fresh = item("2", "Charizard", "2026-10-20T01:00:00Z");
  vi.mocked(getLiveFeed).mockResolvedValueOnce(feed([old])).mockResolvedValue(feed([fresh, old]));
  render(<LiveUpdatesDashboard initialData={empty} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
  expect(screen.getByText("Pikachu")).toBeVisible();
  expect(screen.queryByText("Charizard")).toBeNull();
  expect(vi.mocked(getLiveFeed).mock.calls[0][0]).toMatchObject({ provider: "pokemonpricetracker", page: 1 });

  await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
  const names = screen.getAllByRole("link", { name: /Pikachu|Charizard/ }).map((link) => link.textContent);
  expect(names[0]).toBe("Charizard");  // newest ingestion is prepended
  expect(names.filter((name) => name === "Pikachu")).toHaveLength(1);  // no duplicates
});

it("tints only rows added by a poll, once", async () => {
  const old = item("1", "Pikachu", "2026-10-18T01:52:52Z");
  const fresh = item("2", "Charizard", "2026-10-20T01:00:00Z");
  vi.mocked(getLiveFeed).mockResolvedValueOnce(feed([old])).mockResolvedValue(feed([fresh, old]));
  render(<LiveUpdatesDashboard initialData={empty} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
  const tile = (name: string) => screen.getByRole("link", { name }).closest(".rounded-2xl");
  expect(tile("Pikachu")).not.toHaveClass("animate-fresh-row");  // initial load is not "new"

  await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
  expect(tile("Charizard")).toHaveClass("animate-fresh-row");
  expect(tile("Pikachu")).not.toHaveClass("animate-fresh-row");

  await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
  expect(tile("Charizard")).not.toHaveClass("animate-fresh-row");
});

it("keeps showing totals from a paused worker, labelled as dated", async () => {
  vi.mocked(getLiveFeed).mockResolvedValue(empty);
  vi.mocked(getLiveStats).mockReset().mockResolvedValue({
    total_items: 1234, total_ebay_updates: 0, total_tcg_updates: 0, total_legacy_updates: 0,
    total_ppt_updates: 1234, graded_updates_count: 56, is_stale: true,
    generated_at: new Date(Date.now() - 2 * 60 * 60_000).toISOString(),
  });
  render(<LiveUpdatesDashboard initialData={empty} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
  expect(screen.getByText(/updates paused/)).toBeVisible();
  expect(screen.queryByText("Unavailable")).toBeNull();
});
