import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function GradingProfitLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Real Instant Header */}
        <div className="flex flex-col justify-between gap-6 border-b border-slate-200/80 pb-6 lg:flex-row lg:items-end">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
                <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
                <span>ARBITRAGE CALCULATOR</span>
                <span className="text-slate-300">|</span>
                <span className="text-slate-500">PSA 10 &amp; 9 COMP ENGINE</span>
              </span>
            </div>
            <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-950 uppercase">
              Grading Profitability
            </h1>
            <p className="mt-2 max-w-2xl text-xs sm:text-sm text-slate-600 leading-relaxed">
              Calculated net dollar spreads and expected returns between raw cards and graded slabs.
            </p>
          </div>

          {/* Interactive Fee Simulator Inline Shell */}
          <div className="flex flex-col gap-2 rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs sm:min-w-[320px]">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                Grading Fee Simulator
              </span>
              <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-black text-indigo-700 border border-indigo-200/60 font-mono">
                $24.99 / card
              </span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100 mt-2" />
          </div>
        </div>

        {/* Filters Bar Skeleton */}
        <div className="mt-6 mb-6 h-28 w-full animate-pulse rounded-2xl bg-white border border-slate-200/80 p-4" />

        {/* Content Section with Progress Bar */}
        <div className="mt-6">
          <SectionLoadingBar
            label="Calculating Grading Arbitrage..."
            detail="Evaluating raw buy-in vs PSA 10/9 historical sold comps"
          />

          {/* Cards Grid Skeleton */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="h-80 w-full animate-pulse rounded-3xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex gap-4">
                  <div className="h-28 w-20 rounded-xl bg-slate-200" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-20 rounded bg-slate-200" />
                    <div className="h-5 w-3/4 rounded bg-slate-200" />
                    <div className="h-4 w-16 rounded bg-slate-200" />
                  </div>
                </div>
                <div className="mt-6 space-y-3">
                  <div className="h-10 w-full rounded-xl bg-slate-100" />
                  <div className="h-10 w-full rounded-xl bg-slate-100" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
