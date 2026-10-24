import { expect, it } from "vitest";
import { carryForward, mergeProviderHistory, providerSeriesName, robustMedian, selectHistorySeries, withoutAskingOutliers } from "@/lib/provider-history";
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

it("presents the continuation as PPT while retaining historical provenance", () => {
  const combined = { ...series, provider: "market", points: [
    { date: "2026-10-14", price: 20, sales_count: null, source: "tcgapi", condition: null },
    { date: "2026-10-16", price: 30, sales_count: null, source: "pokemonpricetracker" },
  ] };
  expect(providerSeriesName(combined)).toMatch(/^PPT /);
  const rows = mergeProviderHistory([], [combined], "2026-10-01", "2026-10-16");
  expect(rows[0]["ppt:source"]).toBe("tcgapi");
  expect(rows[0]["ppt:condition"]).toBe("Unknown condition");
  expect(rows[1].ppt).toBeUndefined();
  expect(rows[2].ppt).toBe(30);
});

it("fills calendar days for eBay-only history without inventing values", () => {
  const rows = mergeProviderHistory([{ date: "2026-10-14", rawPrice: 5 }, { date: "2026-10-16", rawPrice: 7 }], [], "2026-10-01", "2026-10-17");
  expect(rows.map((row) => row.date)).toEqual(["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17"]);
  expect(rows[1].rawPrice).toBeUndefined();
  expect(rows[3].rawPrice).toBeUndefined();
});

it("holds each recorded price on every later day without filling recorded data", () => {
  const rows = mergeProviderHistory([], [series], "2026-10-12", "2026-10-18");
  const result = carryForward(rows, ["ppt"]);
  // The line starts at the first observation; nothing is drawn before it.
  expect(result[0]).toEqual({ date: "2026-10-14", ppt: 20, "ppt:line": 20, "ppt:source": "pokemonpricetracker" });
  expect(result[1]).toEqual({ date: "2026-10-15", "ppt:line": 20, "ppt:carried": 20, "ppt:carriedFrom": "2026-10-14", "ppt:source": "pokemonpricetracker" });
  // A new observation replaces the held price, which then continues through today.
  expect(result.map((row) => [row.date, row["ppt:line"], row["ppt:carriedFrom"]])).toEqual([
    ["2026-10-14", 20, undefined], ["2026-10-15", 20, "2026-10-14"], ["2026-10-16", 30, undefined],
    ["2026-10-17", 30, "2026-10-16"], ["2026-10-18", 30, "2026-10-16"],
  ]);
  expect(result.every((row, index) => row.ppt === rows[index].ppt)).toBe(true);
  expect(rows[1]).toEqual({ date: "2026-10-15" });
});

it("shows one raw line per enabled printing and every grade of enabled companies only", () => {
  const make = (id: string, printing: string | null, condition: string | null, grade: string | null): ProviderHistorySeries => ({ ...series, id, printing, condition, grade });
  const all = [
    make("holo-nm", "Holofoil", "Near Mint", null), make("holo-lp", "Holofoil", "Lightly Played", null),
    make("rev-lp", "Reverse Holofoil", "Lightly Played", null), make("normal-nm", "Normal", "Near Mint", null),
    make("psa9", null, null, "psa9"), make("psa10", null, null, "psa10"), make("psa9_5", null, null, "psa9_5"),
    make("cgc10", null, null, "cgc10"), make("bgs10", null, null, "bgs10"),
  ];
  const ids = (printings: string[], companies: string[], preferredCondition?: string) =>
    selectHistorySeries(all, { printings: new Set(printings), companies: new Set(companies), preferredCondition }).map((s) => s.id);
  // Default: every printing on, no grading company.
  expect(ids(["Holofoil", "Reverse Holofoil", "Normal"], [])).toEqual(["holo-nm", "rev-lp", "normal-nm"]);
  expect(ids(["Holofoil"], [], "Lightly Played")).toEqual(["holo-lp"]);
  expect(ids([], ["psa"])).toEqual(["psa10", "psa9_5", "psa9"]);
  expect(ids(["Normal"], ["cgc", "psa"])).toEqual(["normal-nm", "psa10", "psa9_5", "psa9", "cgc10"]);
  // Companies without a toggle never appear.
  expect(ids([], ["psa", "cgc", "tag"])).not.toContain("bgs10");
});

it("ignores wild eBay asks and matches the backend robust median", () => {
  expect(robustMedian([180, 200, 210, 195, 17_500_000])).toBe(197.5);
  expect(robustMedian([100, 17_500_000])).toBe(100);
  expect(robustMedian([1, 300, 310, 320])).toBe(310);
  expect(robustMedian([])).toBeNull();
  // A wider band keeps real moves over a long series.
  expect(withoutAskingOutliers([100, 150, 400, 17_500_000], 10)).toEqual([100, 150, 400]);
});
