import type { ChartPoint } from "@/components/price-history-chart";
import type { ProviderHistorySeries } from "@/types/card";

export function providerSeriesName(series: ProviderHistorySeries): string {
  const identity = series.grade ? series.grade.toUpperCase().replace(/(PSA|CGC|BGS)/, "$1 ").replace("_", ".") : `${series.printing || "Unknown printing"} · ${series.condition || "Unknown condition"}`;
  return `${series.provider === "tcgapi" ? "Legacy market" : series.provider === "market" ? "Market price" : "PPT"} ${identity} · ${series.metric === "daily_average" ? "daily sales average" : "market"}`;
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
      dates.set(point.date, row);
    }
  }
  // Explicit null calendar days break lines across missing provider observations.
  const first = [...dates.keys()].sort()[0];
  if (first && series.length) {
    for (let time = Date.parse(first + "T00:00:00Z"); time <= Date.parse(end + "T00:00:00Z"); time += 86400000) {
      const date = new Date(time).toISOString().slice(0, 10);
      if (!dates.has(date)) dates.set(date, { date });
    }
  }
  return [...dates.values()].sort((a, b) => a.date.localeCompare(b.date));
}
