import { PageLoadingStatus } from "@/components/page-loading-status";

export default function SealedSignalsLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Instant Live Status Banner */}
        <div className="mb-6">
          <PageLoadingStatus
            title="Evaluating Sealed Signals"
            description="Running 4-factor quantitative scoring model: supply float, buylist liquidity, price momentum, and vintage scarcity..."
          />
        </div>

        {/* Header Skeleton */}
        <div className="mb-8 flex flex-col justify-between gap-4 border-b border-slate-200 pb-8 sm:flex-row sm:items-end">
          <div className="space-y-2.5 max-w-xl">
            <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
            <div className="h-8 w-64 animate-pulse rounded bg-slate-200" />
            <div className="h-4 w-96 animate-pulse rounded bg-slate-200" />
          </div>
          <div className="flex gap-3">
            <div className="h-16 w-36 animate-pulse rounded-xl bg-slate-200" />
            <div className="h-16 w-36 animate-pulse rounded-xl bg-slate-200" />
          </div>
        </div>

        {/* Filters Skeleton */}
        <div className="mb-6 h-28 w-full animate-pulse rounded-2xl bg-slate-200/80" />

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
