import { SectionLoadingBar } from "@/components/section-loading-bar";

export default function PokedexLoading() {
  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950 font-mono">
      <div className="mx-auto min-w-0 max-w-[1600px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        {/* Header Section - Static Instant Load */}
        <section className="mb-8 pt-1">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-50/80 px-3.5 py-1 text-xs font-semibold text-emerald-800">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                Official National Pokédex · Generations I – IX
              </div>

              <h1 className="text-3xl font-black tracking-tight text-slate-950 sm:text-4xl lg:text-5xl font-sans">
                CardboardDex{" "}
                <span className="text-emerald-600">
                  Pokédex
                </span>
              </h1>

              <p className="mt-2 text-sm leading-relaxed text-slate-600 sm:text-base font-sans">
                Explore all 1,025 Pokémon across 9 generations. Click any Pokémon to view official stats,
                high-resolution artwork, and all verified trading cards with real-time market prices,
                eBay sales, and PSA graded comps.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 text-xs font-semibold">
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
                <span className="text-emerald-700 font-mono text-sm font-bold">1,025</span>
                <span className="text-slate-600">Pokémon</span>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
                <span className="text-cyan-700 font-mono text-sm font-bold">54,480+</span>
                <span className="text-slate-600">Cards Tracked</span>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
                <span className="text-amber-700 font-mono text-sm font-bold">482</span>
                <span className="text-slate-600">Sets Indexed</span>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 shadow-2xs">
                <span className="text-indigo-700 font-mono text-sm font-bold">17,400+</span>
                <span className="text-slate-600">Verified Comps</span>
              </div>
            </div>
          </div>
        </section>

        {/* Controls Bar Skeleton */}
        <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="h-10 w-full sm:w-80 animate-pulse rounded-xl bg-slate-100" />
          <div className="flex gap-1.5 overflow-x-auto">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="h-8 w-14 shrink-0 animate-pulse rounded-lg bg-slate-100" />
            ))}
          </div>
        </div>

        {/* Section Loading Bar */}
        <div className="mb-6">
          <SectionLoadingBar
            label="Loading National Pokédex..."
            detail="Preparing canonical data, base stats, and market links for 1,025 Pokémon species"
          />
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
