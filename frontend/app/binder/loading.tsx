import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function BinderLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        <section className="mb-8 pt-1">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-50/80 px-3.5 py-1 text-xs font-semibold text-emerald-800">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                PORTFOLIO BINDER
              </div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
                My Collection Binder
              </h1>
            </div>
          </div>
        </section>

        <SectionLoadingBar label="Portfolio Binder" detail="Streaming card valuations..." />

        {/* Skeleton Grid */}
        <div className="mt-8 rounded-3xl p-6 sm:p-8 binder-leather-cover">
          <div className="grid grid-cols-3 gap-3 sm:gap-4 max-w-2xl mx-auto">
            {Array.from({ length: 9 }).map((_, i) => (
              <div
                key={i}
                className="aspect-[5/7] rounded-xl border border-slate-800/80 bg-slate-900/40 animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
