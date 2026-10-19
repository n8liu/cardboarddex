import { expect, it } from "vitest";
import { mergeProviderHistory, providerSeriesName } from "@/lib/provider-history";
import type { ProviderHistorySeries } from "@/types/card";
const series: ProviderHistorySeries = { id: "ppt", provider: "pokemonpricetracker", language: "english", currency: "USD", printing: "Holofoil", condition: "Near Mint", grade: null, metric: "market", fetched_at: "2026-10-16", points: [
  { date: "2026-10-14", price: 20, sales_count: null }, { date: "2026-10-16", price: 30, sales_count: 0 },
] };
it("keeps sources separate and leaves missing provider days unfilled", () => {
  const result = mergeProviderHistory([{ date: "2026-10-15", tcgPrice: 999 }], [series], "2026-10-01", "2026-10-16");
  expect(result).toEqual([{ date: "2026-10-14", ppt: 20, "ppt:source": "pokemonpricetracker" }, { date: "2026-10-15", tcgPrice: 999 }, { date: "2026-10-16", ppt: 30, "ppt:source": "pokemonpricetracker" }]);
  expect(mergeProviderHistory([], [series], "2026-10-15", "2026-10-16")).toEqual([{ date: "2026-10-16", ppt: 30, "ppt:source": "pokemonpricetracker" }]);
});
it("labels graded daily means independently from current median quotes", () => {
  expect(providerSeriesName({ ...series, grade: "psa10", metric: "daily_average" })).toBe("PPT PSA 10 · daily sales average");
  expect(providerSeriesName(series)).toContain("Holofoil · Near Mint · market");
});
