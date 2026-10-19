import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useMemo } from "react";
import CatalogPage from "@/app/catalog/page";
import SealedPage from "@/app/sealed-signals/page";
import MoversPage from "@/app/market-movers/page";
import GradingPage from "@/app/grading-profit/page";
import TrendingPage from "@/app/top-volume/page";
import LivePage from "@/app/live-updates/page";
import * as api from "@/lib/api";
import type { CardSummary } from "@/types/card";

vi.mock("next/navigation", () => ({
  useSearchParams: () => useMemo(() => new URLSearchParams(window.location.search), []),
}));
vi.mock("@/components/card-image", () => ({ default: () => null }));
vi.mock("@/components/card-grid", () => ({ CardGrid: ({ cards }: { cards: CardSummary[] }) => <div>{cards.map((card) => <p key={card.id}>{card.name}</p>)}</div> }));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof api>(),
  searchCards: vi.fn(), getCardSets: vi.fn(), getSetStats: vi.fn(),
  getSealedSignals: vi.fn(), getMarketMovers: vi.fn(), getGradingProfit: vi.fn(),
  getTrendingDashboard: vi.fn(), getGradedSalesActivity: vi.fn(), getLiveFeed: vi.fn(), getLiveStats: vi.fn(),
}));
const requests = [api.searchCards, api.getCardSets, api.getSetStats, api.getSealedSignals,
  api.getMarketMovers, api.getGradingProfit, api.getTrendingDashboard, api.getGradedSalesActivity, api.getLiveFeed, api.getLiveStats];
const pending = () => new Promise<never>(() => {});
const card = (name: string): CardSummary => ({ id: name, name, set_id: "test", set_name: "Test", number: "1", printed_total: null, rarity: "Rare", image_url: "", market_price: 10, market_currency: "USD" });

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  requests.forEach((request) => vi.mocked(request).mockReset().mockImplementation(pending));
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each([
  ["sealed products", SealedPage, /Loading newer products/, api.getSealedSignals],
  ["market movers", MoversPage, /Loading market movers/, api.getMarketMovers],
  ["grading", GradingPage, /Loading grading opportunities/, api.getGradingProfit],
  ["trending", TrendingPage, /Loading trending cards/, api.getTrendingDashboard],
  ["live updates", LivePage, /Loading latest market updates/, api.getLiveFeed],
] as const)("renders %s controls before the API responds", async (_name, Page, label, request) => {
  const page = Page();
  expect(request).not.toHaveBeenCalled();
  render(page);
  expect(screen.getByRole("heading", { level: 1 })).toBeVisible();
  expect(screen.getByText(label)).toBeVisible();
  const input = screen.getAllByRole("textbox")[0];
  expect(input).toBeEnabled();
  fireEvent.change(input, { target: { value: "Pikachu" } });
  expect(input).toHaveValue("Pikachu");
  await waitFor(() => expect(request).toHaveBeenCalled());
});

it("loads catalog cards without waiting for sets or set statistics, and only requests cards once", async () => {
  window.history.replaceState(null, "", "/catalog?set=test&game=pokemon-japan");
  let resolve!: (cards: CardSummary[]) => void;
  vi.mocked(api.searchCards).mockImplementation(() => new Promise((done) => { resolve = done; }));
  const page = await CatalogPage({ searchParams: Promise.resolve({ set: "test", game: "pokemon-japan" }) });
  expect(api.searchCards).not.toHaveBeenCalled();
  render(page);
  expect(screen.getByText("Loading cards…")).toBeVisible();
  expect(screen.getByRole("searchbox")).toBeEnabled();
  await waitFor(() => expect(api.searchCards).toHaveBeenCalledTimes(1));
  expect(api.searchCards).toHaveBeenCalledWith("", expect.objectContaining({ setId: "test", game: "pokemon-japan" }));
  await act(async () => resolve([card("Loaded card")]));
  expect(screen.getByText("Loaded card")).toBeVisible();
  expect(screen.queryByText("Loading cards…")).not.toBeInTheDocument();
  expect(api.searchCards).toHaveBeenCalledTimes(1);
});

it("ignores an old catalog response after the search changes", async () => {
  let resolveOld!: (cards: CardSummary[]) => void;
  vi.mocked(api.searchCards).mockImplementation((query) => query === "new" ? Promise.resolve([card("Current result")]) : new Promise((done) => { resolveOld = done; }));
  render(await CatalogPage({ searchParams: Promise.resolve({}) }));
  await waitFor(() => expect(api.searchCards).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "new" } });
  await screen.findByText("Current result");
  await act(async () => resolveOld([card("Obsolete result")]));
  expect(screen.queryByText("Obsolete result")).not.toBeInTheDocument();
  expect(screen.getByRole("searchbox")).toHaveValue("new");
});

it("shows a retryable grading error and clears loading after recovery", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(api.getGradingProfit).mockRejectedValueOnce(new Error("API offline")).mockResolvedValueOnce({ page: 1, per_page: 24, total_cards: 0, total_pages: 1, grading_fee: 24.99, sort_by: "psa10_profit_desc", items: [], updated_at: "2026-10-12" });
  render(GradingPage());
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load results");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  await waitFor(() => expect(screen.queryByText("Loading grading opportunities…")).not.toBeInTheDocument());
  expect(api.getGradingProfit).toHaveBeenCalledTimes(2);
  expect(log).toHaveBeenCalledWith("Failed fetching grading profit opportunities:", expect.any(Error));
  log.mockRestore();
});

it("starts catalog immediately but debounces rapid typing", async () => {
  vi.useFakeTimers();
  try {
    render(await CatalogPage({ searchParams: Promise.resolve({}) }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(api.searchCards).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "pi" } });
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "pikachu" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(249); });
    expect(api.searchCards).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(api.searchCards).toHaveBeenCalledTimes(2);
    expect(api.searchCards).toHaveBeenLastCalledWith("pikachu", expect.anything());
  } finally { cleanup(); vi.useRealTimers(); }
});

it("pauses Live Comps in hidden tabs, resumes immediately, and avoids overlapping polls", async () => {
  vi.useFakeTimers();
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  const empty = { items: [], total_pages: 1, total_items: 0, page: 1, per_page: 24,
    total_ebay_updates: 0, total_tcg_updates: 0, graded_updates_count: 0, provider_filter: "all", grade_filter: "all", updated_at: "2026-10-12" };
  vi.mocked(api.getLiveFeed).mockResolvedValue(empty as never);
  try {
    render(LivePage());
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    expect(api.getLiveFeed).toHaveBeenCalledTimes(1);
    hidden.mockReturnValue(true);
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(api.getLiveFeed).toHaveBeenCalledTimes(1);
    vi.mocked(api.getLiveFeed).mockImplementation(pending);
    hidden.mockReturnValue(false);
    fireEvent(document, new Event("visibilitychange"));
    expect(api.getLiveFeed).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(45_000); });
    expect(api.getLiveFeed).toHaveBeenCalledTimes(2);
  } finally { cleanup(); hidden.mockRestore(); vi.useRealTimers(); }
});

it("collapses catalog filters by default and again when mobile search is focused", async () => {
  vi.stubGlobal("innerWidth", 390);
  render(await CatalogPage({ searchParams: Promise.resolve({}) }));
  const toggle = screen.getByRole("button", { name: "Show filters" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  fireEvent.focus(screen.getByRole("searchbox"));
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(document.getElementById("catalog-browse-filters")).toHaveClass("hidden", "lg:block");
  expect(document.getElementById("catalog-quick-filters")).toHaveClass("hidden", "lg:flex");
});

it("renders Live Comps as a catalog grid and allows switching to the list", async () => {
  vi.mocked(api.getLiveFeed).mockResolvedValue({
    page: 1, per_page: 24, has_more: false, updated_at: "2026-10-15",
    items: [{ id: "comp", card_id: "card", card_name: "Grid card", set_id: "set", set_name: "Test set", image_url: "/image", provider: "ebay", price: 20, currency: "USD", observed_at: "2026-10-15" }],
  });
  render(LivePage());
  expect(await screen.findByRole("link", { name: "Grid card" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Grid" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Full Width" }));
  expect(screen.getByRole("button", { name: "Full Width" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("link", { name: "Grid card" })).toHaveAttribute("href", "/cards/card");
});

const feedResult = (name: string, page = 1, has_more = false) => ({
  page, per_page: 24, has_more, updated_at: new Date().toISOString(),
  items: [{ id: name, card_id: name, card_name: name, set_id: "s", set_name: "Set",
    image_url: "/image", provider: "tcgapi", price: 20, currency: "USD", observed_at: new Date().toISOString() }],
});

it("shows cards while totals fail, and keeps totals retry independent of the feed", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(api.getLiveStats).mockRejectedValue(new Error("offline"));
  vi.mocked(api.getLiveFeed).mockResolvedValue(feedResult("Visible card"));
  try {
    render(LivePage());
    expect(await screen.findByRole("link", { name: "Visible card" })).toBeVisible();
    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(screen.getByText("1 records loaded")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry totals" }));
    await waitFor(() => expect(api.getLiveStats).toHaveBeenCalledTimes(2));
    expect(api.getLiveFeed).toHaveBeenCalledTimes(1);
  } finally { log.mockRestore(); }
});

it("ignores obsolete filter responses while totals remain pending", async () => {
  let finish!: (value: ReturnType<typeof feedResult>) => void;
  vi.mocked(api.getLiveFeed).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }))
    .mockResolvedValue(feedResult("New card"));
  render(LivePage());
  await waitFor(() => expect(api.getLiveFeed).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "new" } });
  expect(await screen.findByRole("link", { name: "New card" })).toBeVisible();
  await act(async () => finish(feedResult("Obsolete card")));
  expect(screen.queryByRole("link", { name: "Obsolete card" })).not.toBeInTheDocument();
  expect(screen.getAllByText("Loading totals…")).toHaveLength(2);
});

it("keeps final-page has_more after a first-page poll", async () => {
  vi.useFakeTimers();
  vi.mocked(api.getLiveFeed).mockResolvedValueOnce(feedResult("First", 1, true))
    .mockResolvedValueOnce(feedResult("Last", 2, false))
    .mockResolvedValue(feedResult("Newest", 1, true));
  try {
    render(LivePage());
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    fireEvent.click(screen.getByRole("button", { name: /Load more/ }));
    await act(async () => {});
    expect(screen.getByText("End of results")).toBeVisible();
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(screen.getByRole("link", { name: "Newest" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Last" })).toBeVisible();
    expect(screen.getByText("End of results")).toBeVisible();
  } finally { cleanup(); vi.useRealTimers(); }
});

it("loads graded sales independently while Trending remains pending", async () => {
  vi.mocked(api.getGradedSalesActivity).mockResolvedValue({ status: "not_synced", coverage: "Provider-reported coverage", synced_at: null, products_with_sales_data: 0, items: [] });
  render(TrendingPage());
  expect(await screen.findByText(/No graded sales counts have been synced/)).toBeVisible();
  expect(screen.getByText(/Loading trending cards/)).toBeVisible();
});
