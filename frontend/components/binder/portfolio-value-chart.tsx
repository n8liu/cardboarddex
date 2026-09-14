"use client";

import React, { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCurrency } from "@/context/currency-context";
import type { PortfolioHistoryPoint } from "@/types/binder";

type TimeframeOption = "7D" | "1M" | "3M" | "1Y" | "ALL";

interface PortfolioValueChartProps {
  history: PortfolioHistoryPoint[];
  currentValue: number;
}

export function PortfolioValueChart({ history, currentValue }: PortfolioValueChartProps) {
  const { formatPrice, convertPrice, currency } = useCurrency();
  const [timeframe, setTimeframe] = useState<TimeframeOption>("1M");

  // Filter history points based on selected timeframe
  const filteredData = useMemo(() => {
    if (!history || history.length === 0) {
      const todayIso = new Date().toISOString().slice(0, 10);
      return [
        { date: todayIso, total_value: currentValue, card_count: 0, convertedValue: convertPrice(currentValue) ?? 0 },
      ];
    }

    const now = new Date();
    let daysToKeep = 365 * 5;
    if (timeframe === "7D") daysToKeep = 7;
    else if (timeframe === "1M") daysToKeep = 30;
    else if (timeframe === "3M") daysToKeep = 90;
    else if (timeframe === "1Y") daysToKeep = 365;

    const cutoff = new Date(now.getTime() - daysToKeep * 86400 * 1000)
      .toISOString()
      .slice(0, 10);

    let sliced = history.filter((p) => p.date >= cutoff);
    if (sliced.length === 0) sliced = history.slice(-7);

    return sliced.map((p) => ({
      ...p,
      convertedValue: convertPrice(p.total_value) ?? 0,
    }));
  }, [history, timeframe, currentValue, convertPrice]);

  const { minVal, maxVal, startingVal, peakVal } = useMemo(() => {
    if (filteredData.length === 0) {
      return { minVal: 0, maxVal: 100, startingVal: 0, peakVal: 0 };
    }
    const vals = filteredData.map((d) => d.convertedValue);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    return {
      minVal: Math.max(0, min * 0.92),
      maxVal: max * 1.08 || 100,
      startingVal: vals[0],
      peakVal: max,
    };
  }, [filteredData]);

  const convertedCurrent = convertPrice(currentValue) ?? 0;
  const periodDiff = startingVal > 0 ? convertedCurrent - startingVal : 0;
  const periodPct = startingVal > 0 ? (periodDiff / startingVal) * 100 : 0;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6 shadow-xs">
      {/* Chart Top Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <h3 className="font-mono text-xs sm:text-sm font-bold uppercase tracking-wider text-slate-600">
              Portfolio Valuation Trend
            </h3>
          </div>
          <div className="mt-1 flex items-baseline gap-2.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-slate-950">
              {formatPrice(currentValue)}
            </span>
            {startingVal > 0 && (
              <span
                className={`font-mono text-xs font-bold px-2 py-0.5 rounded-full ${
                  periodDiff >= 0
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : "bg-rose-50 text-rose-700 border border-rose-200"
                }`}
              >
                {periodDiff >= 0 ? "+" : ""}
                {periodDiff.toFixed(2)} ({periodPct >= 0 ? "+" : ""}
                {periodPct.toFixed(1)}%)
              </span>
            )}
          </div>
        </div>

        {/* Timeframe Buttons */}
        <div className="flex items-center rounded-xl border border-slate-200 bg-slate-100/80 p-1 font-mono text-xs">
          {(["7D", "1M", "3M", "1Y", "ALL"] as const).map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => setTimeframe(tf)}
              className={`rounded-lg px-2.5 py-1 font-bold transition ${
                timeframe === tf
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-950"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Area */}
      <div className="mt-4 h-[240px] sm:h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={filteredData}
            margin={{ top: 10, right: 10, left: -15, bottom: 0 }}
          >
            <defs>
              <linearGradient id="portfolioAreaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity={0.25} />
                <stop offset="60%" stopColor="#10b981" stopOpacity={0.06} />
                <stop offset="100%" stopColor="#10b981" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#94a3b8"
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: "#e2e8f0" }}
              tickFormatter={(val: string) => {
                const parts = val.split("-");
                return parts.length >= 3 ? `${parts[1]}/${parts[2]}` : val;
              }}
            />
            <YAxis
              stroke="#94a3b8"
              fontSize={10}
              domain={[minVal, maxVal]}
              tickLine={false}
              axisLine={false}
              tickFormatter={(val: number) => {
                if (currency === "JPY") return `¥${Math.round(val)}`;
                if (val >= 1000) return `$${(val / 1000).toFixed(1)}k`;
                return `$${Math.round(val)}`;
              }}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload || !payload.length) return null;
                const point = payload[0].payload;
                return (
                  <div className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur-sm font-mono text-xs">
                    <p className="text-slate-500 pb-1 border-b border-slate-100">
                      {new Intl.DateTimeFormat("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      }).format(new Date(`${point.date}T00:00:00Z`))}
                    </p>
                    <div className="mt-1.5 space-y-1">
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-slate-500">Total Binder:</span>
                        <span className="font-bold text-emerald-600">
                          {formatPrice(point.total_value)}
                        </span>
                      </div>
                      {point.card_count !== undefined && (
                        <div className="flex items-center justify-between gap-4">
                          <span className="text-slate-500">Cards Count:</span>
                          <span className="text-slate-800 font-semibold">{point.card_count} cards</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              }}
            />
            <Area
              type="monotone"
              dataKey="convertedValue"
              stroke="none"
              fill="url(#portfolioAreaGrad)"
            />
            <Line
              type="monotone"
              dataKey="convertedValue"
              stroke="#10b981"
              strokeWidth={2.5}
              dot={filteredData.length <= 2}
              activeDot={{
                r: 5,
                fill: "#10b981",
                stroke: "#ffffff",
                strokeWidth: 2,
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* KPI Stats Row below chart */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-3 pt-3 border-t border-slate-100 font-mono text-xs">
        <div>
          <span className="text-slate-500">Period Start:</span>
          <p className="font-bold text-slate-800">{formatPrice(startingVal)}</p>
        </div>
        <div>
          <span className="text-slate-500">Peak Valuation:</span>
          <p className="font-bold text-emerald-600">{formatPrice(peakVal)}</p>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <span className="text-slate-500">Data Points:</span>
          <p className="font-bold text-slate-800">{filteredData.length} daily snapshots</p>
        </div>
      </div>
    </div>
  );
}
