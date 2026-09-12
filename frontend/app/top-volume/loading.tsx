import { PageLoadingStatus } from "@/components/page-loading-status";

export default function TopVolumeLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-white text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 sm:px-6 lg:px-8">
        {/* Instant Live Status Banner */}
        <div className="mb-6">
          <PageLoadingStatus
            title="Loading Trending Dashboard"
            description="Syncing real-time search interest, popular Pokémon species, and verified market volume..."
          />
        </div>

        {/* Header Skeleton */}
        <div className="mb-6 flex flex-col justify-between gap-4 border-b border-slate-200/80 pb-6 sm:flex-row sm:items-end">
          <div className="space-y-2 max-w-xl">
            <div className="h-3.5 w-32 animate-pulse rounded bg-slate-200" />
            <div className="h-8 w-80 animate-pulse rounded-xl bg-slate-200" />
            <div className="h-3.5 w-96 max-w-full animate-pulse rounded bg-slate-200" />
          </div>
          <div className="flex gap-2">
            <div className="h-10 w-28 animate-pulse rounded-xl bg-slate-100" />
            <div className="h-10 w-32 animate-pulse rounded-xl bg-slate-100" />
          </div>
        </div>

        {/* Filter Controls Bar Skeleton */}
        <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-slate-50/50 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="h-10 w-full sm:w-72 animate-pulse rounded-xl bg-white border border-slate-200" />
          <div className="flex gap-1.5 overflow-x-auto">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-8 w-16 shrink-0 animate-pulse rounded-lg bg-slate-200/70" />
            ))}
          </div>
        </div>

        {/* 3-Column Skeleton Grid (Matching Current Dashboard Architecture) */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Column 1: Trending Cards */}
          <div className="rounded-2xl border border-slate-200/80 bg-slate-50/30 p-4">
            <div className="mb-3 flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-16 animate-pulse rounded bg-slate-200" />
            </div>
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div
                  key={`c-skel-${i}`}
                  className="flex h-[62px] animate-pulse items-center justify-between rounded-xl border border-slate-200/60 bg-white px-3"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="h-4 w-6 rounded bg-slate-200" />
                    <div className="h-10 w-10 rounded-lg bg-slate-200" />
                    <div className="space-y-1">
                      <div className="h-3 w-28 rounded bg-slate-200" />
                      <div className="h-2.5 w-20 rounded bg-slate-100" />
                    </div>
                  </div>
                  <div className="h-4 w-14 rounded bg-slate-200" />
                </div>
              ))}
            </div>
          </div>

          {/* Column 2: Popular Pokémon */}
          <div className="rounded-2xl border border-slate-200/80 bg-slate-50/30 p-4">
            <div className="mb-3 flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-16 animate-pulse rounded bg-slate-200" />
            </div>
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div
                  key={`p-skel-${i}`}
                  className="flex h-[62px] animate-pulse items-center justify-between rounded-xl border border-slate-200/60 bg-white px-3"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="h-4 w-6 rounded bg-slate-200" />
                    <div className="h-10 w-10 rounded-lg bg-slate-200" />
                    <div className="space-y-1">
                      <div className="h-3 w-24 rounded bg-slate-200" />
                      <div className="h-2.5 w-16 rounded bg-slate-100" />
                    </div>
                  </div>
                  <div className="h-4 w-12 rounded bg-slate-200" />
                </div>
              ))}
            </div>
          </div>

          {/* Column 3: Volume Leaders */}
          <div className="rounded-2xl border border-slate-200/80 bg-slate-50/30 p-4">
            <div className="mb-3 flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-16 animate-pulse rounded bg-slate-200" />
            </div>
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div
                  key={`v-skel-${i}`}
                  className="flex h-[62px] animate-pulse items-center justify-between rounded-xl border border-slate-200/60 bg-white px-3"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="h-4 w-6 rounded bg-slate-200" />
                    <div className="h-10 w-10 rounded-lg bg-slate-200" />
                    <div className="space-y-1">
                      <div className="h-3 w-24 rounded bg-slate-200" />
                      <div className="h-2.5 w-20 rounded bg-slate-100" />
                    </div>
                  </div>
                  <div className="h-4 w-16 rounded bg-slate-200" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
