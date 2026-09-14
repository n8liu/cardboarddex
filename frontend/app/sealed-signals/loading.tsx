import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function SealedSignalsLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Header - Static Instant Load */}
        <div className="border-b border-slate-200/80 pb-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
              <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
              <span>INVESTMENT SIGNALS</span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-500">4-FACTOR QUANTITATIVE MODEL</span>
            </span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-950 uppercase">
            Sealed Investment Signals
          </h1>
          <p className="mt-2 max-w-2xl text-xs sm:text-sm text-slate-600 leading-relaxed">
            Quantitative 0–100 buy ratings evaluating supply float, liquidity, velocity, and vintage age.
          </p>
        </div>

        {/* Telemetry Stats Grid Shell */}
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Strong Buys
            </div>
            <div className="mt-2 h-7 w-12 animate-pulse rounded bg-slate-200" />
            <div className="mt-1 text-[11px] text-slate-500">
              Top conviction rating
            </div>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Low Supply Float
            </div>
            <div className="mt-2 h-7 w-12 animate-pulse rounded bg-slate-200" />
            <div className="mt-1 text-[11px] text-slate-500">
              &lt; 15 active listings
            </div>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Avg Signal Score
            </div>
            <div className="mt-2 h-7 w-16 animate-pulse rounded bg-slate-200" />
            <div className="mt-1 text-[11px] text-slate-500">
              Across items
            </div>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Top 30d Momentum
            </div>
            <div className="mt-2 h-7 w-16 animate-pulse rounded bg-slate-200" />
            <div className="mt-1 text-[11px] text-slate-500">
              30-day price gain
            </div>
          </div>
        </div>

        {/* Filter Bar Skeleton */}
        <div className="mt-6 h-24 w-full animate-pulse rounded-2xl bg-slate-200/80" />

        {/* Section Loading Bar */}
        <div className="mt-8 mb-6">
          <SectionLoadingBar
            label="Evaluating Sealed Product Telemetry..."
            detail="Running 4-factor quantitative scoring model: supply float, buylist liquidity, price momentum, and vintage scarcity"
          />
        </div>

        {/* Cards Grid Skeleton */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="flex h-96 flex-col justify-between rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div>
                <div className="flex items-center justify-between">
                  <div className="h-6 w-24 animate-pulse rounded-full bg-slate-200" />
                  <div className="h-4 w-12 animate-pulse rounded bg-slate-200" />
                </div>
                <div className="mt-4 flex gap-3">
                  <div className="h-20 w-20 animate-pulse rounded-xl bg-slate-200" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-full animate-pulse rounded bg-slate-200" />
                    <div className="h-4 w-2/3 animate-pulse rounded bg-slate-200" />
                  </div>
                </div>
              </div>
              <div className="space-y-2 border-t border-slate-100 pt-4">
                <div className="flex justify-between">
                  <div className="h-3 w-16 animate-pulse rounded bg-slate-100" />
                  <div className="h-3 w-12 animate-pulse rounded bg-slate-200" />
                </div>
                <div className="flex justify-between">
                  <div className="h-3 w-16 animate-pulse rounded bg-slate-100" />
                  <div className="h-3 w-12 animate-pulse rounded bg-slate-200" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
