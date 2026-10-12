import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SealedSignalsDashboard } from "@/components/sealed-signals-dashboard";
import { getSealedSignals } from "@/lib/api";
import type { SealedSignalItem, SealedSignalsResponse } from "@/types/card";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(window.location.search) }));
vi.mock("@/components/card-image", () => ({ default: () => null }));
vi.mock("@/lib/api", () => ({ getSealedSignals: vi.fn(), cardImageUrl: (url: string) => url }));
const item = (id: string, growth: number | null = 12): SealedSignalItem => ({
  card_id: id, name: `${id} Booster Box`, set_id: id, set_name: id, image_url: "/test.png",
  product_type: "Booster Box", market_price: 120, total_listings: 4, supply_rating: "Low",
  set_age_months: 12, price_change_30d: growth, signal_score: 75, signal_label: "BUY",
  supply_score: 20, demand_score: 20, momentum_score: 20, vintage_score: 15, release_date: "2025-01-01",
});
const data = (items: SealedSignalItem[], page = 1, totalPages = 1): SealedSignalsResponse => ({
  items, page, per_page: 12, total_items: items.length, total_pages: totalPages,
  signal_filter: "all", product_type_filter: "all", sort_by: "momentum_desc",
  strong_buy_count: 0, buy_count: 0, hold_count: 0, underperform_count: 0, updated_at: "2026-10-11",
});
beforeEach(() => { window.history.replaceState(null, "", "/sealed-signals"); vi.mocked(getSealedSignals).mockReset(); });
afterEach(cleanup);

it("shows separate rankings, distinguishes zero and missing growth, and hides secondary filters", () => {
  render(<SealedSignalsDashboard initialData={{ newer: data([item("new", 0)]), older: data([item("old", null)]) }} />);
  expect(within(screen.getByRole("region", { name: "Newer releases" })).getByText("0.0%")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Older & vintage" })).getByText("Unavailable")).toBeInTheDocument();
  expect(screen.queryByLabelText("Rank by")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Filters & sort/ }));
  expect(screen.getByLabelText("Rank by")).toHaveValue("momentum_desc");
  expect(getSealedSignals).not.toHaveBeenCalled();
});

it("loads each era independently and applies URL filters on first load", async () => {
  window.history.replaceState(null, "", "/sealed-signals?type=etb&q=151");
  vi.mocked(getSealedSignals).mockImplementation(async ({ era } = {}) => data([item(era!)]));
  render(<SealedSignalsDashboard initialData={{ newer: data([item("stale")]), older: null }} />);
  await screen.findByText("newer Booster Box");
  await screen.findByText("older Booster Box");
  expect(screen.queryByText("stale Booster Box")).not.toBeInTheDocument();
  expect(getSealedSignals).toHaveBeenCalledWith(expect.objectContaining({ era: "newer", productType: "etb", query: "151", page: 1 }));
  expect(getSealedSignals).toHaveBeenCalledWith(expect.objectContaining({ era: "older", productType: "etb", query: "151", page: 1 }));
});

it("paginates only the requested column", async () => {
  vi.mocked(getSealedSignals).mockResolvedValue(data([item("second")], 2, 2));
  render(<SealedSignalsDashboard initialData={{ newer: data([item("first")], 1, 2), older: data([item("old")]) }} />);
  fireEvent.click(screen.getByRole("button", { name: "Load more newer products" }));
  await screen.findByText("second Booster Box");
  expect(screen.getByText("first Booster Box")).toBeInTheDocument();
  expect(getSealedSignals).toHaveBeenCalledTimes(1);
  expect(getSealedSignals).toHaveBeenCalledWith(expect.objectContaining({ era: "newer", page: 2 }));
});

it("shows a retryable error without blanking the other column", async () => {
  vi.mocked(getSealedSignals).mockRejectedValueOnce(new Error("Unavailable")).mockResolvedValueOnce(data([item("recovered")]));
  render(<SealedSignalsDashboard initialData={{ newer: null, older: data([item("old")]) }} />);
  await screen.findByRole("alert");
  expect(screen.getByText("old Booster Box")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("recovered Booster Box");
});

it("ignores a late response from an obsolete filter request", async () => {
  let resolveOld!: (value: SealedSignalsResponse) => void;
  const old = new Promise<SealedSignalsResponse>((resolve) => { resolveOld = resolve; });
  vi.mocked(getSealedSignals).mockImplementation(({ productType } = {}) => productType === "etb" ? old : Promise.resolve(data([item("current")])));
  render(<SealedSignalsDashboard initialData={{ newer: data([]), older: data([]) }} />);
  fireEvent.change(screen.getByLabelText("Product type"), { target: { value: "etb" } });
  await waitFor(() => expect(getSealedSignals).toHaveBeenCalledTimes(2));
  fireEvent.change(screen.getByLabelText("Product type"), { target: { value: "pack" } });
  await screen.findAllByText("current Booster Box");
  resolveOld(data([item("obsolete")]));
  await waitFor(() => expect(screen.queryByText("obsolete Booster Box")).not.toBeInTheDocument());
});

it("filters both eras by language, keeps it when paginating, and resets to all", async () => {
  vi.mocked(getSealedSignals).mockImplementation(async ({ era, game, page = 1 } = {}) => data([item(`${game}-${era}-${page}`)], page, 2));
  render(<SealedSignalsDashboard initialData={{ newer: data([item("initial-new")]), older: data([item("initial-old")]) }} />);
  const language = within(screen.getByRole("group", { name: "Product language" }));
  fireEvent.click(language.getByRole("button", { name: "Japanese" }));
  await screen.findByText("pokemon-japan-newer-1 Booster Box");
  await screen.findByText("pokemon-japan-older-1 Booster Box");
  expect(window.location.search).toBe("?game=pokemon-japan");
  expect(language.getByRole("button", { name: "Japanese" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Load more newer products" }));
  await screen.findByText("pokemon-japan-newer-2 Booster Box");
  expect(getSealedSignals).toHaveBeenLastCalledWith(expect.objectContaining({ game: "pokemon-japan", era: "newer", page: 2 }));
  fireEvent.click(language.getByRole("button", { name: "English" }));
  await screen.findByText("pokemon-newer-1 Booster Box");
  await screen.findByText("pokemon-older-1 Booster Box");
  expect(screen.queryByText("pokemon-japan-newer-2 Booster Box")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  expect(window.location.search).toBe("");
  expect(language.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("initial-new Booster Box")).toBeInTheDocument();
});

it("restores language from shared URLs and browser navigation", async () => {
  window.history.replaceState(null, "", "/sealed-signals?game=pokemon-japan&period=90&type=etb");
  vi.mocked(getSealedSignals).mockImplementation(async ({ era, game } = {}) => data([item(`${game}-${era}`)]));
  render(<SealedSignalsDashboard initialData={{ newer: data([item("stale")]), older: data([]) }} />);
  await screen.findByText("pokemon-japan-newer Booster Box");
  expect(getSealedSignals).toHaveBeenCalledWith(expect.objectContaining({ game: "pokemon-japan", period: 90, productType: "etb" }));
  expect(screen.queryByText("stale Booster Box")).not.toBeInTheDocument();
  window.history.replaceState(null, "", "/sealed-signals?game=pokemon");
  fireEvent.popState(window);
  await screen.findByText("pokemon-newer Booster Box");
  expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("Product type")).toHaveValue("all");
  expect(screen.getByRole("button", { name: "30 days" })).toHaveAttribute("aria-pressed", "true");
});
