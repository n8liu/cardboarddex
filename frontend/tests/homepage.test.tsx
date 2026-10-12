import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LandingPage } from "@/components/landing-page";
import { getHomeOverview } from "@/lib/api";
import type { HomeOverview } from "@/types/home";

vi.mock("@/components/card-image", () => ({ default: () => null }));
vi.mock("@/components/search-autocomplete", () => ({ SearchAutocomplete: () => <input aria-label="Search cards" /> }));
vi.mock("@/components/command-palette", () => ({ openCommandPalette: vi.fn() }));
vi.mock("@/lib/api", () => ({ getHomeOverview: vi.fn(), cardImageUrl: (s: string) => s }));
const overview: HomeOverview = {
  calculated_at: "2026-10-12T00:00:00Z", catalog_updated_at: "2026-10-10T00:00:00Z", latest_observation_at: "2026-10-09T00:00:00Z",
  products: 1234, sets: 12, price_observations: 2345,
  gainer: { card_id: "gain", name: "Gaining Card", set_name: "Test Set", image_url: "/cards/gain/image", printing: "Normal", market_price: 100, change_percent: 20, market_price_as_of: "2026-09-01", observed_at: "2026-10-09", price_freshness: "stale", history: [] },
  loser: null, sealed: null,
  releases: [
    { id: "en", name: "English Release", game: "pokemon", release_date: "2026-10-01", upcoming: false, card_count: 20, image_url: null },
    { id: "jp", name: "Japanese Release", game: "pokemon-japan", release_date: "2026-09-01", upcoming: false, card_count: 30, image_url: null },
    { id: "next", name: "Future Set", game: "pokemon-japan", release_date: "2026-11-01", upcoming: true, card_count: 0, image_url: null },
  ],
};
beforeEach(() => { localStorage.clear(); vi.mocked(getHomeOverview).mockReset(); });
afterEach(cleanup);

it("shows dated highlights, verified counts, and all six visual tool links", async () => {
  vi.mocked(getHomeOverview).mockResolvedValue(overview);
  render(<LandingPage />);
  expect(await screen.findByText("Gaining Card")).toBeInTheDocument();
  expect(screen.getByText(/Price dated Sep 1, 2026 · Stale/)).toBeInTheDocument();
  expect(screen.getByText("1,234")).toBeInTheDocument();
  expect(screen.getByText("2,345")).toBeInTheDocument();
  expect(screen.queryByText(/LIVE DATA ENGINE ACTIVE|15-Min|54,680/)).not.toBeInTheDocument();
  const tools = within(screen.getByRole("region", { name: "A little curiosity. A lot to discover." }));
  for (const href of ["/market-movers", "/sealed-signals", "/binder", "/catalog", "/grading-profit", "/pokedex"]) {
    expect(tools.getAllByRole("link").some((a) => a.getAttribute("href") === href)).toBe(true);
  }
});

it("filters release language and separates upcoming dates without mixing them", async () => {
  vi.mocked(getHomeOverview).mockResolvedValue(overview);
  render(<LandingPage />);
  await screen.findByText("English Release");
  expect(screen.queryByText("Future Set")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Japanese" }));
  expect(screen.queryByText("English Release")).not.toBeInTheDocument();
  expect(screen.getByText("Japanese Release").closest("a")).toHaveAttribute("href", "/catalog?set=jp&game=pokemon-japan");
  fireEvent.click(screen.getByRole("button", { name: "Upcoming" }));
  expect(screen.getByText("Future Set")).toBeInTheDocument();
  expect(screen.queryByText("Japanese Release")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "English" }));
  expect(screen.getByText("No upcoming sets listed for this language yet.")).toBeInTheDocument();
});

it("keeps search usable on API failure and allows a retry without made-up totals", async () => {
  vi.mocked(getHomeOverview).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ ...overview, products: 0 });
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  render(<LandingPage />);
  await screen.findByRole("alert");
  expect(screen.getByRole("textbox", { name: "Search cards" })).toBeInTheDocument();
  expect(screen.getAllByText("Unavailable")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "Retry data" }));
  await screen.findByText("Gaining Card");
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(screen.getByText("0")).toBeInTheDocument();
  log.mockRestore();
});
