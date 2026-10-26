import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CompareDashboard, parseCompareIds } from "@/components/compare-dashboard";
import { getCard, getCardPricing, searchCards } from "@/lib/api";
import type { CardDetail, CardPricing } from "@/types/card";

const chart = vi.fn();
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(window.location.search) }));
vi.mock("@/lib/api", () => ({ getCard: vi.fn(), getCardPricing: vi.fn(), searchCards: vi.fn(), cardImageUrl: (src: string) => src }));
vi.mock("@/components/card-image", () => ({ default: () => null }));
vi.mock("@/components/card-link", () => ({ CardLink: ({ children }: { children: React.ReactNode }) => <a>{children}</a> }));
vi.mock("@/context/currency-context", () => ({ useCurrency: () => ({ formatPrice: (v: number) => `$${v}` }) }));
vi.mock("@/components/price-history-chart", () => ({ PriceHistoryChart: (props: unknown) => { chart(props); return <div>chart</div>; } }));

const today = new Date().toISOString().slice(0, 10);
const card = (id: string, name: string) => ({ id, name, set_name: "Base", number: "1", image_url: "", market_price: 10 }) as CardDetail;
const pricing = (price: number): CardPricing => ({
  card_id: "x", observations: [], provider_states: [], ppt_mapped: true,
  market_history_series: [{ id: "s", provider: "ppt", language: "english", currency: "USD", printing: "Holofoil", condition: "Near Mint",
    grade: null, metric: "market", fetched_at: today, points: [{ date: today, price, sales_count: null }] }],
}) as CardPricing;

beforeEach(() => {
  chart.mockReset();
  window.history.replaceState(null, "", "/compare?ids=a,b,a,c,d,e");
  vi.mocked(getCard).mockImplementation(async (id) => card(id, `Card ${id.toUpperCase()}`));
  vi.mocked(getCardPricing).mockImplementation(async (id) => pricing(id === "a" ? 50 : 200));
  vi.mocked(searchCards).mockResolvedValue([]);
});
afterEach(cleanup);

it("parses at most four unique ids", () => {
  expect(parseCompareIds(" a, b,,a ,c,d,e")).toEqual(["a", "b", "c", "d"]);
  expect(parseCompareIds(null)).toEqual([]);
});

it("plots one line per card, indexed by default, with a price toggle", async () => {
  render(<CompareDashboard />);
  await act(async () => {});
  const props = chart.mock.lastCall![0] as { extraSeries: { key: string; name: string }[]; data: Record<string, unknown>[] };
  expect(props.extraSeries.map((s) => s.key)).toEqual(["card:a", "card:b", "card:c", "card:d"]);
  expect(props.data.at(-1)).toMatchObject({ "card:a": 100, "card:b": 100 });
  fireEvent.click(screen.getByRole("button", { name: "Price" }));
  expect((chart.mock.lastCall![0] as typeof props).data.at(-1)).toMatchObject({ "card:a": 50, "card:b": 200 });
  // Full: the add-a-card box is hidden at four cards.
  expect(screen.queryByLabelText("Add a card")).toBeNull();
});

it("removes a card through the URL", async () => {
  render(<CompareDashboard />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Remove Card B" }));
  expect(window.location.search).toBe("?ids=a%2Cc%2Cd");
});
