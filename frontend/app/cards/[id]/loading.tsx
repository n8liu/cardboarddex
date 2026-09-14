import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function CardDetailLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        {/* Back Link Shell */}
        <div className="mb-6 flex items-center gap-2">
          <div className="h-8 w-24 animate-pulse rounded-lg bg-slate-200" />
        </div>

        {/* Section Loading Bar */}
        <div className="mb-8">
          <SectionLoadingBar
            label="Loading Card Market Comps..."
            detail="Querying price history, PSA graded comps, and verified eBay sold listings"
          />
        </div>

        {/* Card Main Layout Skeleton */}
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[380px_minmax(0,1fr)] xl:grid-cols-[440px_minmax(0,1fr)]">
          {/* Left Column: Image Frame Skeleton */}
          <div className="space-y-4">
            <div className="aspect-[2.5/3.5] w-full animate-pulse rounded-3xl border border-slate-200 bg-white p-6 shadow-xs" />
            <div className="h-12 w-full animate-pulse rounded-2xl bg-slate-200" />
          </div>

          {/* Right Column: Details, Matrix & Charts Skeleton */}
          <div className="space-y-6">
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs sm:p-8 space-y-4">
              <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
              <div className="h-8 w-80 animate-pulse rounded-xl bg-slate-200" />
              <div className="flex gap-2">
                <div className="h-6 w-24 animate-pulse rounded-lg bg-slate-100" />
                <div className="h-6 w-20 animate-pulse rounded-lg bg-slate-100" />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-20 animate-pulse rounded-2xl bg-slate-50 border border-slate-100" />
                ))}
              </div>
            </div>

            {/* Price Chart Skeleton */}
            <div className="h-80 w-full animate-pulse rounded-3xl border border-slate-200 bg-white p-6 shadow-xs" />

            {/* Recent Sales Table Skeleton */}
            <div className="h-64 w-full animate-pulse rounded-3xl border border-slate-200 bg-white p-6 shadow-xs" />
          </div>
        </div>
      </div>
    </main>
  );
}
