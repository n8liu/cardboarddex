import { afterEach, expect, it, vi } from "vitest";
import { fetchPortfolioDataWithFallback } from "@/lib/portfolio";
import { getCard, getCardPricing, getPortfolioValuation } from "@/lib/api";
import { getPokemonDetail } from "@/lib/pokeapi";
import type { CardDetail } from "@/types/card";
vi.mock("@/lib/api", () => ({ getCard: vi.fn(), getCardPricing: vi.fn(), getPortfolioValuation: vi.fn() }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it("limits binder fallback to four requests and preserves successful cards", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(getPortfolioValuation).mockRejectedValue(new Error("batch unavailable"));
  let active = 0;
  let maximum = 0;
  async function read() {
    maximum = Math.max(maximum, ++active);
    await new Promise((resolve) => setTimeout(resolve, 2));
    active--;
  }
  vi.mocked(getCard).mockImplementation(async (id) => {
    await read();
    if (id === "bad") throw new Error("detail unavailable");
    return { id, name: id, set_name: "Test", number: "1", printed_total: null, rarity: "Rare", image_url: "", market_price: 10 } as CardDetail;
  });
  vi.mocked(getCardPricing).mockImplementation(async () => { await read(); return null; });
  const result = await fetchPortfolioDataWithFallback(["1", "2", "3", "4", "5", "6", "bad"]);
  expect(maximum).toBe(4);
  expect(result.total_cards).toBe(6);
  expect(log).toHaveBeenCalledWith("[portfolio] Card bad detail failed:", expect.any(Error));
});

it("gives both PokéAPI reads a three-second deadline and uses the existing fallback", async () => {
  vi.useFakeTimers();
  vi.spyOn(console, "error").mockImplementation(() => {});
  const timeout = vi.spyOn(AbortSignal, "timeout").mockImplementation((ms) => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(new Error("PokeAPI deadline")), ms);
    return controller.signal;
  });
  vi.stubGlobal("fetch", vi.fn((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(options.signal.reason));
  })));
  const detail = getPokemonDetail(25);
  await vi.advanceTimersByTimeAsync(3000);
  expect((await detail)?.name).toBe("Pikachu");
  expect(timeout).toHaveBeenCalledTimes(2);
  expect(timeout).toHaveBeenCalledWith(3000);
});
