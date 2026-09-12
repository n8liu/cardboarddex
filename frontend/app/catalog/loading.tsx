import { PageLoadingStatus } from "@/components/page-loading-status";

export default function CatalogLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        {/* Instant Live Status Banner */}
        <div className="mb-6">
          <PageLoadingStatus
            title="Loading Card Catalog"
            description="Querying 54,480+ Pokémon cards across 482 expansions and verified market comps..."
          />
        </div>

        {/* Header Skeleton */}
        <div className="mb-6 space-y-2">
          <div className="h-8 w-64 animate-pulse rounded-xl bg-slate-200" />
          <div className="h-4 w-96 max-w-full animate-pulse rounded bg-slate-200" />
        </div>

        {/* Filter Controls Bar Skeleton */}
        <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="h-10 w-full sm:w-80 animate-pulse rounded-xl bg-slate-100" />
          <div className="flex flex-wrap gap-2">
            <div className="h-10 w-36 animate-pulse rounded-xl bg-slate-100" />
            <div className="h-10 w-36 animate-pulse rounded-xl bg-slate-100" />
            <div className="h-10 w-28 animate-pulse rounded-xl bg-slate-100" />
          </div>
        </div>

        {/* Card Grid Skeleton */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 18 }).map((_, i) => (
            <div
              key={`cat-skel-${i}`}
              className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-3 shadow-xs"
            >
              <div className="aspect-[2.5/3.5] w-full animate-pulse rounded-xl bg-slate-100 p-2" />
              <div className="mt-3 space-y-1.5">
                <div className="h-2.5 w-16 animate-pulse rounded bg-slate-100" />
                <div className="h-3.5 w-full animate-pulse rounded bg-slate-200" />
                <div className="h-3 w-20 animate-pulse rounded bg-slate-100" />
              </div>
              <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2">
                <div className="h-2.5 w-10 animate-pulse rounded bg-slate-100" />
                <div className="h-4 w-14 animate-pulse rounded bg-slate-200" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
