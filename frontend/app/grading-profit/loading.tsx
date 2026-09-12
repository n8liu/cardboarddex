import { PageLoadingStatus } from "@/components/page-loading-status";

export default function GradingProfitLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Instant Live Status Banner */}
        <div className="mb-6">
          <PageLoadingStatus
            title="Calculating Grading Arbitrage"
            description="Evaluating real-time PSA 10 & 9 spreads, raw market prices, and net grading margins..."
          />
        </div>

        {/* Header Skeleton */}
        <div className="mb-8 flex flex-col justify-between gap-4 border-b border-slate-200 pb-8 sm:flex-row sm:items-end">
          <div className="space-y-2.5 max-w-xl">
            <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
            <div className="h-8 w-64 animate-pulse rounded bg-slate-200" />
            <div className="h-4 w-96 animate-pulse rounded bg-slate-200" />
          </div>
          <div className="h-24 w-72 animate-pulse rounded-2xl bg-slate-200" />
        </div>

        {/* Filters Skeleton */}
        <div className="mb-6 h-28 w-full animate-pulse rounded-2xl bg-slate-200/80" />

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
    </main>
  );
}
