import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CommandPalette, openCommandPalette } from "@/components/command-palette";
import { getCardSets, searchCards } from "@/lib/api";

const push = vi.fn();
let pathname = "/catalog";
const binder = { quickAddCard: vi.fn(), isCardInBinder: vi.fn(() => false), isHydrated: true };

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => pathname }));
vi.mock("@/lib/api", () => ({ getCardSets: vi.fn(), searchCards: vi.fn(), cardImageUrl: (src: string) => src }));
vi.mock("@/components/card-image", () => ({ default: () => null }));
vi.mock("@/context/binder-context", () => ({ useBinder: () => binder }));
vi.mock("@/context/currency-context", () => ({
  SUPPORTED_CURRENCIES: [], useCurrency: () => ({ currency: "USD", setCurrency: vi.fn(), formatPrice: (v: number) => `$${v}` }),
}));

beforeEach(() => {
  pathname = "/catalog";
  push.mockReset(); binder.quickAddCard.mockReset(); binder.isCardInBinder.mockReset().mockReturnValue(false);
  vi.mocked(searchCards).mockResolvedValue([]);
  vi.mocked(getCardSets).mockResolvedValue([
    { id: "sv8", name: "Surging Sparks", series: "Scarlet & Violet", release_date: "2024-11-08" },
    { id: "sv8-jp", name: "Super Electric Breaker", series: "Pokemon Japan", release_date: "2024-10-18" },
  ]);
});
afterEach(cleanup);

async function open() {
  render(<CommandPalette />);
  await act(async () => { openCommandPalette(); });
  return screen.getByRole("combobox");
}

it("finds sets by name and links Japanese sets with their game", async () => {
  const input = await open();
  expect(getCardSets).toHaveBeenCalledTimes(1);
  fireEvent.change(input, { target: { value: "breaker" } });
  const option = await screen.findByRole("option", { name: /Super Electric Breaker/ });
  fireEvent.click(option);
  expect(push).toHaveBeenCalledWith("/catalog?set=sv8-jp&game=pokemon-japan");
});

it("adds the current card to the binder from a card page", async () => {
  pathname = "/cards/base1-4";
  const input = await open();
  fireEvent.change(input, { target: { value: "binder" } });
  fireEvent.click(screen.getByRole("option", { name: /Add this card to my binder/ }));
  expect(binder.quickAddCard).toHaveBeenCalledWith("base1-4");
});

it("exposes the active option to assistive tech", async () => {
  const input = await open();
  const options = screen.getAllByRole("option");
  expect(options[0]).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(input, { key: "ArrowDown" });
  expect(input).toHaveAttribute("aria-activedescendant", "palette-option-1");
  expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
});
