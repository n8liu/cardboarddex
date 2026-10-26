import type { ChartPoint } from "@/components/price-history-chart";
import type { ProviderHistorySeries } from "@/types/card";

export function providerSeriesName(series: ProviderHistorySeries): string {
  const identity = series.grade ? series.grade.toUpperCase().replace(/(PSA|CGC|BGS|SGC|TAG)/, "$1 ").replace("_", ".") : `${series.printing || "Unknown printing"} · ${series.condition || "Unknown condition"}`;
  return `PPT ${identity} · ${series.metric === "daily_average" ? "daily sales average" : "market"}`;
}

export function mergeProviderHistory(legacy: ChartPoint[], series: ProviderHistorySeries[], cutoff: string, end: string): ChartPoint[] {
  const dates = new Map<string, ChartPoint>();
  for (const point of legacy) if (point.date >= cutoff && point.date <= end) dates.set(point.date, { ...point });
  for (const item of series) {
    for (const point of item.points) {
      if (point.date < cutoff || point.date > end) continue;
      const row = dates.get(point.date) ?? { date: point.date };
      row[item.id] = point.price;
      row[`${item.id}:source`] = point.source || item.provider;
      if ("condition" in point) row[`${item.id}:condition`] = point.condition ?? "Unknown condition";
      dates.set(point.date, row);
    }
  }
  // Every calendar day is a hoverable row; missing values stay null so nothing is plotted for them.
  const first = [...dates.keys()].sort()[0];
  if (first) {
    for (let time = Date.parse(first + "T00:00:00Z"); time <= Date.parse(end + "T00:00:00Z"); time += 86400000) {
      const date = new Date(time).toISOString().slice(0, 10);
      if (!dates.has(date)) dates.set(date, { date });
    }
  }
  return [...dates.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Display-only fill: `${key}:line` holds each recorded price until the next one (from the
 * key's first observation through the last row), and `:carried` marks held days for the
 * tooltip. Recorded keys are never filled.
 */
export function carryForward(rows: ChartPoint[], keys: string[]): ChartPoint[] {
  const last = new Map<string, ChartPoint>();
  return rows.map((row) => {
    const out: ChartPoint = { ...row };
    for (const key of keys) {
      if (typeof row[key] === "number") {
        last.set(key, row);
        out[`${key}:line`] = row[key];
        continue;
      }
      const known = last.get(key);
      if (!known) continue;
      out[`${key}:line`] = known[key];
      out[`${key}:carried`] = known[key];
      out[`${key}:carriedFrom`] = known.date;
      for (const meta of ["source", "condition"]) if (known[`${key}:${meta}`] !== undefined) out[`${key}:${meta}`] = known[`${key}:${meta}`];
    }
    return out;
  });
}

const ASKING_BAND = 3;

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * eBay asking prices without wild listings: keeps values within `band`x of the lower median
 * (always an actual listing), matching backend `asking_prices.robust_asking_price`.
 */
export function withoutAskingOutliers(values: number[], band = ASKING_BAND): number[] {
  const positive = values.filter((v) => v > 0);
  if (!positive.length) return [];
  const centre = [...positive].sort((a, b) => a - b)[Math.floor((positive.length - 1) / 2)];
  return positive.filter((v) => v >= centre / band && v <= centre * band);
}

/** Median of asking prices after dropping outliers; null when there are none. */
export function robustMedian(values: number[]): number | null {
  const kept = withoutAskingOutliers(values);
  return kept.length ? median(kept) : null;
}

export const GRADING_COMPANIES = ["psa", "cgc", "bgs", "sgc", "tag"] as const;
export type GradingCompany = (typeof GRADING_COMPANIES)[number];

/** "psa10" → "psa", "cgc9_5" → "cgc"; null for raw series. */
export function gradeCompany(grade: string | null): string | null {
  return grade ? grade.match(/^[a-z]+/i)?.[0].toLowerCase() ?? null : null;
}

function gradeValue(grade: string): number {
  return Number(grade.replace(/^[a-z]+/i, "").replace("_", ".")) || 0;
}

export function seriesPrinting(series: ProviderHistorySeries): string {
  return series.printing || "Unknown printing";
}

/**
 * Chart series for the toggles: one raw line per enabled printing (its preferred condition,
 * else Near Mint, else the first listed) and every grade of each enabled grading company,
 * highest grade first. Other conditions and companies stay hidden to keep the chart readable.
 */
export function selectHistorySeries(series: ProviderHistorySeries[], options: {
  printings: ReadonlySet<string>; companies: ReadonlySet<string>; preferredCondition?: string | null;
}): ProviderHistorySeries[] {
  const raw = series.filter((item) => !item.grade && options.printings.has(seriesPrinting(item)));
  const conditionFor = new Map<string, string | null>();
  for (const printing of new Set(raw.map(seriesPrinting))) {
    const conditions = raw.filter((item) => seriesPrinting(item) === printing).map((item) => item.condition);
    conditionFor.set(printing, [options.preferredCondition, "Near Mint"].find((c) => c && conditions.includes(c)) ?? conditions[0]);
  }
  const graded = series.filter((item) => options.companies.has(gradeCompany(item.grade) ?? ""))
    .sort((a, b) => GRADING_COMPANIES.indexOf(gradeCompany(a.grade) as GradingCompany) - GRADING_COMPANIES.indexOf(gradeCompany(b.grade) as GradingCompany)
      || gradeValue(b.grade!) - gradeValue(a.grade!));
  return [...raw.filter((item) => item.condition === conditionFor.get(seriesPrinting(item))), ...graded];
}

/**
 * The single raw line that best represents a card's market price: the primary quote's
 * printing and condition when known, else the first raw series (Near Mint preferred).
 */
export function primaryMarketSeries(series: ProviderHistorySeries[], primary?: { printing: string | null; condition: string | null } | null): ProviderHistorySeries | null {
  const raw = series.filter((item) => !item.grade);
  if (!raw.length) return null;
  const printing = primary?.printing && raw.some((item) => item.printing === primary.printing) ? primary.printing : seriesPrinting(raw[0]);
  return selectHistorySeries(raw, {
    printings: new Set([printing || "Unknown printing"]), companies: new Set(), preferredCondition: primary?.condition,
  })[0] ?? null;
}

/**
 * Rescales each key so its first recorded value in `rows` is 100, for comparing cards at
 * different price levels. Other keys and missing days are left as they are.
 */
export function indexToFirstValue(rows: ChartPoint[], keys: string[]): ChartPoint[] {
  const base = new Map<string, number>();
  for (const key of keys) {
    const first = rows.find((row) => typeof row[key] === "number" && (row[key] as number) > 0);
    if (first) base.set(key, first[key] as number);
  }
  return rows.map((row) => {
    const out: ChartPoint = { ...row };
    for (const [key, start] of base) if (typeof row[key] === "number") out[key] = Math.round((row[key] as number) / start * 10000) / 100;
    return out;
  });
}
