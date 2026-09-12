import { PageLoadingStatus } from "@/components/page-loading-status";

export default function LiveUpdatesLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Instant Live Status Banner */}
        <div className="mb-6">
          <PageLoadingStatus
            title="Connecting to Live Comps Feed"
            description="Ingesting streaming eBay sold listings, graded slab transactions, and TCG API price syncs..."
          />
        </div>

        {/* Header Skeleton */}
        <div className="mb-8 flex flex-col justify-between gap-4 border-b border-slate-200 pb-8 sm:flex-row sm:items-end">
          <div className="space-y-2.5 max-w-xl">
            <div className="h-4 w-40 animate-pulse rounded bg-slate-200" />
            <div className="h-8 w-80 animate-pulse rounded bg-slate-200" />
            <div className="h-4 w-96 animate-pulse rounded bg-slate-200" />
          </div>
          <div className="flex gap-3">
            <div className="h-16 w-40 animate-pulse rounded-xl bg-slate-200" />
            <div className="h-16 w-40 animate-pulse rounded-xl bg-slate-200" />
          </div>
        </div>

        {/* Controls Skeleton */}
        <div className="mb-6 h-28 w-full animate-pulse rounded-2xl bg-slate-200/80" />

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
