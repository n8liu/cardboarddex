import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function LiveUpdatesLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Header - Static Instant Load */}
        <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-8 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-sky-500 animate-ping" />
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-sky-700">
                Real-Time Ingestion Stream
              </span>
            </div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-950 sm:text-4xl">
              Live Updated Items &amp; Comps
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
              Streaming feed of verified market comps, eBay sold listings, graded slab submissions, and TCG API price syncs in real-time chronological order.
            </p>
          </div>

          {/* Top KPI Stats Shell */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-3 rounded-xl border border-sky-500/20 bg-sky-50/70 px-3.5 py-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-600 text-xs font-mono font-bold text-white shadow-xs">
                OBS
              </span>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-sky-800">Total Observations</p>
                <div className="mt-0.5 h-4 w-16 animate-pulse rounded bg-sky-200" />
              </div>
            </div>

            <div className="flex items-center gap-3 rounded-xl border border-purple-500/20 bg-purple-50/70 px-3.5 py-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-600 text-xs font-mono font-bold text-white shadow-xs">
                SLAB
              </span>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-purple-800">Graded Slabs</p>
                <div className="mt-0.5 h-4 w-16 animate-pulse rounded bg-purple-200" />
              </div>
            </div>
          </div>
        </div>

        {/* Controls Skeleton */}
        <div className="mt-8 mb-6 h-16 w-full animate-pulse rounded-2xl bg-slate-200/80" />

        {/* Section Loading Bar */}
        <div className="mb-6">
          <SectionLoadingBar
            label="Connecting to Live Comps Stream..."
            detail="Ingesting streaming eBay sold listings, graded slab transactions, and TCG API price syncs"
          />
        </div>

        {/* List Skeleton */}
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-20 w-full animate-pulse rounded-2xl bg-slate-200/70" />
          ))}
        </div>
      </div>
    </main>
  );
}
