import { PageLoadingStatus } from "@/components/page-loading-status";

export default function RootLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        <div className="mb-6">
          <PageLoadingStatus
            title="Loading CardboardDex"
            description="Syncing real-time market comps, prices, and catalog data..."
          />
        </div>

        <div className="h-14 max-w-4xl animate-pulse rounded-2xl bg-slate-200" />
        <div className="mt-8 grid items-start gap-7 lg:grid-cols-[240px_minmax(0,1fr)]">
          <div className="h-80 animate-pulse rounded-2xl bg-slate-200" />
          <div>
            <div className="mb-5 flex justify-between">
              <div className="h-6 w-48 animate-pulse rounded-md bg-slate-200" />
              <div className="h-4 w-32 animate-pulse rounded-md bg-slate-200" />
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
              {Array.from({ length: 10 }).map((_, i) => (
                <div key={`card-skel-${i}`} className="aspect-[5/7] animate-pulse rounded-2xl border border-slate-200 bg-white p-3" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
