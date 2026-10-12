import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PokemonCardsView } from "@/components/pokemon-cards-view";
import { summarizeDisplayedCards } from "@/lib/pokemon-card-summary";
import { getPokemonCards } from "@/lib/api";
import type { CardSummary } from "@/types/card";
import type { PokemonCardsResponse } from "@/types/pokemon";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(window.location.search) }));
vi.mock("@/components/card-image", () => ({ default: () => null }));
vi.mock("@/components/ui/holo-card", () => ({ HoloCard: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/lib/api", () => ({ getPokemonCards: vi.fn(), cardImageUrl: (s: string) => s }));
const card = (id: string, price: number | null, rarity: string | null = "Rare"): CardSummary => ({
  id, name: `Pikachu ${id}`, set_id: "set", set_name: "Test Set", number: id,
  printed_total: null, rarity, image_url: `/cards/${id}/image`, market_price: price, market_currency: "USD",
});
const initialCards = [card("Box", 1000, null), card("VMAX", 120), card("Promo", 30), card("Pending", null)];
const response = (cards: CardSummary[]): PokemonCardsResponse => ({ pokemon_name: "Pikachu", cards, available_sets: [], total_cards: 0, highest_price: null, lowest_price: null });
const metric = (label: string) => within(screen.getByText(label).parentElement!);
beforeEach(() => { window.history.replaceState(null, "", "/pokemon/25"); vi.mocked(getPokemonCards).mockReset(); });
afterEach(cleanup);

it("derives displayed metrics locally and hides sealed products by default", () => {
  render(<PokemonCardsView pokemonName="Pikachu" initialCards={initialCards} availableSets={[]} />);
  expect(metric("Cards shown").getByText("3")).toBeInTheDocument();
  expect(metric("Highest Value Card").getByText("$120.00")).toBeInTheDocument();
  expect(metric("Highest Value Card").getByRole("link")).toHaveAttribute("href", "/cards/VMAX");
  expect(metric("Total displayed price").getByText("$150.00")).toBeInTheDocument();
  expect(metric("Total displayed price").getByText(/2 of 3.*1 price unavailable/)).toBeInTheDocument();
  expect(screen.queryByText("Pikachu Box")).not.toBeInTheDocument();
  expect(getPokemonCards).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /Show sealed products/ }));
  expect(metric("Products shown").getByText("4")).toBeInTheDocument();
  expect(metric("Total displayed price").getByText("$1150.00")).toBeInTheDocument();
  expect(metric("Highest Value Card").getByText("$120.00")).toBeInTheDocument();
  expect(screen.getByText("Pikachu Box")).toBeInTheDocument();
  expect(getPokemonCards).not.toHaveBeenCalled();
});

it("recalculates for the visible search results, zero prices, and empty states", () => {
  render(<PokemonCardsView pokemonName="Pikachu" initialCards={[...initialCards, card("Free", 0)]} availableSets={[]} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Promo" } });
  expect(metric("Cards shown").getByText("1")).toBeInTheDocument();
  expect(metric("Highest Value Card").getByText("$30.00")).toBeInTheDocument();
  expect(metric("Total displayed price").getByText("$30.00")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Free" } });
  expect(metric("Highest Value Card").getByText("$0.00")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Pending" } });
  expect(metric("Highest Value Card").getByText("Unavailable")).toBeInTheDocument();
  expect(metric("Total displayed price").getByText("Unavailable")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "no-match" } });
  expect(metric("Cards shown").getByText("0")).toBeInTheDocument();
  expect(metric("Total displayed price").getByText("$0.00")).toBeInTheDocument();
  expect(getPokemonCards).not.toHaveBeenCalled();
});

it("ignores late filter responses and stale API summary fields", async () => {
  let finish!: (r: PokemonCardsResponse) => void;
  vi.mocked(getPokemonCards).mockImplementation((_name, options) => options?.game === "pokemon" ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve(response([card("Japanese", 75)])));
  render(<PokemonCardsView pokemonName="Pikachu" initialCards={initialCards} availableSets={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "EN" }));
  fireEvent.click(screen.getByRole("button", { name: "JP" }));
  await waitFor(() => expect(metric("Cards shown").getByText("1")).toBeInTheDocument());
  expect(metric("Highest Value Card").getByText("$75.00")).toBeInTheDocument();
  finish(response([card("Obsolete", 999)]));
  await waitFor(() => expect(screen.queryByText("Pikachu Obsolete")).not.toBeInTheDocument());
  expect(metric("Total displayed price").getByText("$75.00")).toBeInTheDocument();
});

it("restores the local sealed toggle from shared URLs and back navigation", async () => {
  window.history.replaceState(null, "", "/pokemon/25?hide_sealed=false");
  render(<PokemonCardsView pokemonName="Pikachu" initialCards={initialCards} availableSets={[]} />);
  expect(screen.getByText("Pikachu Box")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Hide sealed products/ }));
  await waitFor(() => expect(window.location.search).toBe(""));
  window.history.replaceState(null, "", "/pokemon/25?hide_sealed=false");
  fireEvent.popState(window);
  expect(screen.getByText("Pikachu Box")).toBeInTheDocument();
  expect(getPokemonCards).not.toHaveBeenCalled();
});

it("reports a failed refresh and retries without trusting server totals", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(getPokemonCards).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(response([card("Refreshed", 42)]));
  render(<PokemonCardsView pokemonName="Pikachu" initialCards={initialCards} availableSets={[]} />);
  fireEvent.change(screen.getByLabelText("Sort cards"), { target: { value: "price_asc" } });
  await screen.findByRole("alert");
  expect(metric("Cards shown").getByText("3")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(metric("Highest Value Card").getByText("$42.00")).toBeInTheDocument());
  expect(metric("Cards shown").getByText("1")).toBeInTheDocument();
  log.mockRestore();
});

it("excludes non-finite prices and sealed products from the highest card", () => {
  const result = summarizeDisplayedCards([card("missing", null), card("nan", NaN), card("negative", -1), card("zero", 0), card("sealed", 500, "None")]);
  expect(result.highestCard?.id).toBe("zero");
  expect(result.totalPrice).toBe(500);
  expect(result.missingCount).toBe(3);
});
