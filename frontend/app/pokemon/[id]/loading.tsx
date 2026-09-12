import { PageLoadingStatus } from "@/components/page-loading-status";

export default function PokemonDetailLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        {/* Instant Live Status Banner */}
        <div className="mb-6">
          <PageLoadingStatus
            title="Loading Pokémon Profile"
            description="Fetching official PokéAPI stats, artwork, and matching trading card market comps..."
          />
        </div>

        {/* Header Breadcrumb & Cycle Nav Skeleton */}
        <div className="mb-6 flex items-center justify-between">
          <div className="h-8 w-36 animate-pulse rounded-xl bg-slate-200" />
          <div className="flex gap-2">
            <div className="h-8 w-24 animate-pulse rounded-xl bg-slate-200" />
            <div className="h-8 w-24 animate-pulse rounded-xl bg-slate-200" />
          </div>
        </div>

        {/* Hero Species Card Skeleton */}
        <div className="mb-8 rounded-3xl border border-slate-200 bg-white p-6 shadow-xs sm:p-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-center">
            <div className="h-44 w-44 shrink-0 animate-pulse rounded-2xl bg-slate-100 self-center md:self-auto" />
            <div className="flex-1 space-y-3">
              <div className="flex items-center gap-2">
                <div className="h-4 w-16 animate-pulse rounded bg-slate-200" />
                <div className="h-4 w-24 animate-pulse rounded bg-slate-200" />
              </div>
              <div className="h-10 w-64 animate-pulse rounded-xl bg-slate-200" />
              <div className="flex gap-2">
                <div className="h-6 w-20 animate-pulse rounded-lg bg-slate-100" />
                <div className="h-6 w-20 animate-pulse rounded-lg bg-slate-100" />
              </div>
              <div className="h-4 w-full max-w-lg animate-pulse rounded bg-slate-100" />
            </div>
          </div>
        </div>

        {/* Cards Section Header Skeleton */}
        <div className="mb-4 flex items-center justify-between border-b border-slate-200 pb-3">
          <div className="h-6 w-48 animate-pulse rounded bg-slate-200" />
          <div className="h-4 w-28 animate-pulse rounded bg-slate-200" />
        </div>

        {/* Cards Grid Skeleton */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={`poke-card-skel-${i}`}
              className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-3 shadow-xs"
            >
              <div className="aspect-[2.5/3.5] w-full animate-pulse rounded-xl bg-slate-100" />
              <div className="mt-3 space-y-1.5">
                <div className="h-3 w-16 animate-pulse rounded bg-slate-100" />
                <div className="h-4 w-full animate-pulse rounded bg-slate-200" />
              </div>
              <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2">
                <div className="h-3 w-10 animate-pulse rounded bg-slate-100" />
                <div className="h-4 w-12 animate-pulse rounded bg-slate-200" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
