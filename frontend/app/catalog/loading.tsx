import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function CatalogLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        {/* Header - Static Instant Load */}
        <div className="mb-6">
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-950">
            Pokémon Card Catalog
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-600">
            Search 54,480+ Pokémon cards across 482 expansions with live verified market comps.
          </p>
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

        {/* Section Loading Bar */}
        <div className="mb-6">
          <SectionLoadingBar
            label="Querying Catalog Database..."
            detail="Filtering cards across 482 expansions and verified market comps"
          />
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
