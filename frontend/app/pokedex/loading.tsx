import { PageLoadingStatus } from "@/components/page-loading-status";

export default function PokedexLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        {/* Instant Live Status Banner */}
        <div className="mb-6">
          <PageLoadingStatus
            title="Loading National Pokédex"
            description="Preparing canonical data, base stats, and market links for 1,025 Pokémon species..."
          />
        </div>

        {/* Header Skeleton */}
        <div className="mb-6 space-y-2">
          <div className="h-8 w-60 animate-pulse rounded-xl bg-slate-200" />
          <div className="h-4 w-96 max-w-full animate-pulse rounded bg-slate-200" />
        </div>

        {/* Controls Bar Skeleton */}
        <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="h-10 w-full sm:w-80 animate-pulse rounded-xl bg-slate-100" />
          <div className="flex gap-1.5 overflow-x-auto">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="h-8 w-14 shrink-0 animate-pulse rounded-lg bg-slate-100" />
            ))}
          </div>
        </div>

        {/* Pokédex Species Grid Skeleton */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 18 }).map((_, i) => (
            <div
              key={`dex-skel-${i}`}
              className="flex flex-col items-center rounded-2xl border border-slate-200/90 bg-white p-4 text-center shadow-xs"
            >
              <div className="flex w-full justify-between">
                <div className="h-3 w-12 animate-pulse rounded bg-slate-100" />
                <div className="h-3 w-8 animate-pulse rounded bg-slate-100" />
              </div>
              <div className="my-3 h-24 w-24 animate-pulse rounded-full bg-slate-100" />
              <div className="h-4 w-24 animate-pulse rounded bg-slate-200" />
              <div className="mt-2 flex gap-1">
                <div className="h-4 w-10 animate-pulse rounded-md bg-slate-100" />
                <div className="h-4 w-10 animate-pulse rounded-md bg-slate-100" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
