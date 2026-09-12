"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type ChartPoint = {
  date: string;
  price?: number | null;
  rawPrice?: number | null;
  tcgPrice?: number | null;
  psa10Price?: number | null;
  psa9Price?: number | null;
};

export type SeriesCounts = {
  raw?: number;
  tcg?: number;
  psa10?: number;
  psa9?: number;
};

type PriceHistoryChartProps = {
  data: ChartPoint[];
  currency: string;
  label?: string;
  obsCounts?: SeriesCounts;
};

function money(value: number, currency: string, compact = false): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: compact ? 0 : 2,
    notation: compact ? "compact" : "standard",
  }).format(value);
}

function MultiLineTooltip({
  active,
  payload,
  label,
  currency,
  hasRaw,
  hasTcg,
  hasPsa10,
  hasPsa9,
  customLabel,
}: any) {
  if (!active || !label) return null;
  const point: ChartPoint | undefined = payload?.[0]?.payload;
  if (!point) return null;

  const seriesConfigs = [
    { key: "rawPrice", name: "Raw eBay", color: "#10b981", val: point.rawPrice, active: hasRaw },
    { key: "tcgPrice", name: "TCG API", color: "#8b5cf6", val: point.tcgPrice, active: hasTcg },
    { key: "psa10Price", name: "PSA 10 eBay", color: "#f59e0b", val: point.psa10Price, active: hasPsa10 },
    { key: "psa9Price", name: "PSA 9 eBay", color: "#0284c7", val: point.psa9Price, active: hasPsa9 },
  ];

  const activeSeries = seriesConfigs.filter((s) => s.active);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 shadow-xl text-xs font-mono min-w-[200px]">
      <div className="mb-2 font-semibold text-zinc-700 border-b border-zinc-100 pb-1.5 flex items-center justify-between">
        <span>
          {new Intl.DateTimeFormat("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
            timeZone: "UTC",
          }).format(new Date(`${String(label)}T00:00:00Z`))}
        </span>
      </div>
      <div className="space-y-1.5">
        {activeSeries.length > 0 ? (
          activeSeries.map((s) => (
            <div key={s.key} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-zinc-600">
                <span className="inline-block h-2 w-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                <span>{s.name}</span>
              </span>
              <span className="font-semibold text-zinc-900">
                {s.val !== null && s.val !== undefined ? money(s.val, currency) : "—"}
              </span>
            </div>
          ))
        ) : point.price !== null && point.price !== undefined ? (
          <div className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-zinc-600">
              <span className="inline-block h-2 w-2 rounded-full bg-lime-600" />
              <span>{customLabel}</span>
            </span>
            <span className="font-semibold text-zinc-900">{money(point.price, currency)}</span>
          </div>
        ) : (
          <div className="text-zinc-400">No data</div>
        )}
      </div>
    </div>
  );
}

export function PriceHistoryChart({ data, currency, label = "eBay listings", obsCounts }: PriceHistoryChartProps) {
  const hasRaw = data.some((d) => d.rawPrice !== null && d.rawPrice !== undefined);
  const hasTcg = data.some((d) => d.tcgPrice !== null && d.tcgPrice !== undefined);
  const hasPsa10 = data.some((d) => d.psa10Price !== null && d.psa10Price !== undefined);
  const hasPsa9 = data.some((d) => d.psa9Price !== null && d.psa9Price !== undefined);
  const hasLegacyPrice =
    !hasRaw &&
    !hasTcg &&
    !hasPsa10 &&
    !hasPsa9 &&
    data.some((d) => d.price !== null && d.price !== undefined);

  const validPoints = data.filter(
    (d) =>
      (d.rawPrice !== null && d.rawPrice !== undefined) ||
      (d.tcgPrice !== null && d.tcgPrice !== undefined) ||
      (d.psa10Price !== null && d.psa10Price !== undefined) ||
      (d.psa9Price !== null && d.psa9Price !== undefined) ||
      (d.price !== null && d.price !== undefined),
  );

  if (validPoints.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-zinc-50/50 px-6 text-center">
        <div>
          <p className="text-sm font-medium text-zinc-800">History is still being collected</p>
          <p className="mt-1 text-xs text-zinc-500">Price observations will appear here once recorded.</p>
        </div>
      </div>
    );
  }

  // If only 1 observation date exists, synthesize a 24h baseline so Recharts renders the initial price level
  const chartData =
    validPoints.length === 1
      ? [
          {
            ...validPoints[0],
            date: new Date(new Date(`${validPoints[0].date}T00:00:00Z`).getTime() - 86400000)
              .toISOString()
              .slice(0, 10),
          },
          validPoints[0],
        ]
      : data;

  // Compute Y-axis domain based on currently displayed lines with 2 or more points
  const qualifyingKeys: (keyof ChartPoint)[] = [];
  if ((obsCounts?.raw ?? 0) >= 2) qualifyingKeys.push("rawPrice");
  if ((obsCounts?.tcg ?? 0) >= 2) qualifyingKeys.push("tcgPrice");
  if ((obsCounts?.psa10 ?? 0) >= 2) qualifyingKeys.push("psa10Price");
  if ((obsCounts?.psa9 ?? 0) >= 2) qualifyingKeys.push("psa9Price");

  const activeKeys =
    qualifyingKeys.length > 0
      ? qualifyingKeys
      : (["rawPrice", "tcgPrice", "psa10Price", "psa9Price", "price"] as (keyof ChartPoint)[]);

  const scaleValues: number[] = [];
  for (const d of chartData) {
    for (const k of activeKeys) {
      const val = d[k];
      if (typeof val === "number" && !isNaN(val) && val > 0) {
        scaleValues.push(val);
      }
    }
  }

  let yDomain: [number, number] | undefined = undefined;
  if (scaleValues.length > 0) {
    const minVal = Math.min(...scaleValues);
    const maxVal = Math.max(...scaleValues);
    const span = maxVal - minVal;
    const pad = span > 0 ? span * 0.08 : (minVal * 0.08 || 2);
    const yMin = Math.max(0, Math.floor((minVal - pad) * 100) / 100);
    const yMax = Math.ceil((maxVal + pad) * 100) / 100;
    yDomain = [yMin, yMax];
  }

  const showDots = validPoints.length <= 5 ? { r: 3 } : false;

  return (
    <div className="h-64 w-full" aria-label={`${label} price history chart`} role="img">
      <ResponsiveContainer height="100%" width="100%">
        <LineChart data={chartData} margin={{ bottom: 0, left: 0, right: 12, top: 4 }}>
          <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" vertical={false} />
          <XAxis
            axisLine={false}
            dataKey="date"
            minTickGap={32}
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickFormatter={(value: string) =>
              new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(
                new Date(`${value}T00:00:00Z`),
              )
            }
            tickLine={false}
          />
          <YAxis
            axisLine={false}
            domain={yDomain ?? ["auto", "auto"]}
            allowDataOverflow={true}
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickFormatter={(value: number) => money(value, currency, true)}
            tickLine={false}
            width={54}
          />
          <Tooltip
            content={
              <MultiLineTooltip
                currency={currency}
                hasRaw={hasRaw}
                hasTcg={hasTcg}
                hasPsa10={hasPsa10}
                hasPsa9={hasPsa9}
                customLabel={label}
              />
            }
          />
          <Legend
            verticalAlign="top"
            align="right"
            wrapperStyle={{ paddingBottom: "10px", fontSize: "11px", fontWeight: 500 }}
            iconType="circle"
            iconSize={8}
          />
          {hasRaw && (
            <Line
              activeDot={{ fill: "#059669", r: 4, stroke: "#ffffff", strokeWidth: 2 }}
              connectNulls
              dataKey="rawPrice"
              dot={showDots}
              isAnimationActive={false}
              name="Raw eBay"
              stroke="#10b981"
              strokeWidth={2}
              type="monotone"
            />
          )}
          {hasTcg && (
            <Line
              activeDot={{ fill: "#7c3aed", r: 4, stroke: "#ffffff", strokeWidth: 2 }}
              connectNulls
              dataKey="tcgPrice"
              dot={showDots}
              isAnimationActive={false}
              name="TCG API"
              stroke="#8b5cf6"
              strokeWidth={2}
              type="monotone"
            />
          )}
          {hasPsa10 && (
            <Line
              activeDot={{ fill: "#d97706", r: 4, stroke: "#ffffff", strokeWidth: 2 }}
              connectNulls
              dataKey="psa10Price"
              dot={showDots}
              isAnimationActive={false}
              name="PSA 10 eBay"
              stroke="#f59e0b"
              strokeWidth={2}
              type="monotone"
            />
          )}
          {hasPsa9 && (
            <Line
              activeDot={{ fill: "#0369a1", r: 4, stroke: "#ffffff", strokeWidth: 2 }}
              connectNulls
              dataKey="psa9Price"
              dot={showDots}
              isAnimationActive={false}
              name="PSA 9 eBay"
              stroke="#0284c7"
              strokeWidth={2}
              type="monotone"
            />
          )}
          {hasLegacyPrice && (
            <Line
              activeDot={{ fill: "#4d7c0f", r: 4, stroke: "#ffffff", strokeWidth: 2 }}
              connectNulls
              dataKey="price"
              dot={showDots}
              isAnimationActive={false}
              name={label}
              stroke="#65a30d"
              strokeWidth={2}
              type="monotone"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
