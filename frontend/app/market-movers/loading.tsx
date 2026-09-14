import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function MarketMoversLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Real Instant Header */}
        <div className="border-b border-slate-200/80 pb-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>MOMENTUM RADAR</span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-500">TCG MARKET PRICES</span>
            </span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-950 uppercase">
            Market Movers
          </h1>
          <p className="mt-2 max-w-2xl text-xs sm:text-sm text-slate-600 leading-relaxed">
            Price surges and drops across 24-hour, 7-day, and 30-day velocity windows.
          </p>
        </div>

        {/* Telemetry Stats Grid Skeleton */}
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs">
              <div className="h-3 w-24 animate-pulse rounded bg-slate-200" />
              <div className="mt-2 h-7 w-20 animate-pulse rounded bg-slate-200" />
              <div className="mt-1 h-3 w-32 animate-pulse rounded bg-slate-100" />
            </div>
          ))}
        </div>

        {/* Control Bar Skeleton */}
        <div className="mt-8 flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="h-10 w-72 animate-pulse rounded-xl bg-slate-100" />
          <div className="flex gap-3">
            <div className="h-10 w-56 animate-pulse rounded-xl bg-slate-100" />
            <div className="h-10 w-48 animate-pulse rounded-xl bg-slate-100" />
          </div>
        </div>

        {/* Content Section with Progress Bar */}
        <div className="mt-8">
          <SectionLoadingBar
            label="Loading Market Movers from API..."
            detail="Calculating 24h, 7d & 30d velocity spreads"
          />

          {/* Grid Skeleton */}
          <div className="grid gap-10 lg:grid-cols-2">
            <div>
              <div className="mb-4 h-6 w-40 animate-pulse rounded-md bg-slate-200" />
              <div className="grid gap-4 sm:grid-cols-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={`g-skel-${i}`} className="h-36 animate-pulse rounded-2xl border border-slate-200 bg-white p-4" />
                ))}
              </div>
            </div>

            <div>
              <div className="mb-4 h-6 w-40 animate-pulse rounded-md bg-slate-200" />
              <div className="grid gap-4 sm:grid-cols-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={`l-skel-${i}`} className="h-36 animate-pulse rounded-2xl border border-slate-200 bg-white p-4" />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
