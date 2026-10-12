export default function SealedSignalsLoading() {
  return (
    <div className="min-h-[calc(100vh-65px)] bg-white text-slate-950">
      <div role="status" aria-label="Loading sealed return rankings" className="mx-auto min-w-0 max-w-[1600px] px-4 pb-20 pt-8 font-mono sm:px-6 lg:px-8">
        <header className="mb-6">
          <div className="mb-3 inline-flex flex-wrap items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-emerald-500" />
            <span>SEALED MARKET</span>
            <span aria-hidden="true" className="text-slate-300">|</span>
            <span className="text-slate-500">TCG MARKET PRICES</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">Sealed Signals</h1>
          <p className="mt-2 max-w-2xl text-xs leading-relaxed text-slate-600 sm:text-sm">Compare price growth across newer releases and older sealed products, ranked independently in each era.</p>
        </header>
        <div aria-hidden="true" className="mb-4 border-y border-slate-200 py-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="h-11 flex-1 animate-pulse rounded-xl bg-slate-100" />
            <div className="h-11 animate-pulse rounded-xl bg-slate-100 sm:w-48" />
            <div className="h-11 animate-pulse rounded-xl bg-slate-100 sm:w-40" />
          </div>
          <div className="mt-3 flex flex-wrap justify-between gap-3 border-t border-slate-100 pt-3">
            <div className="h-11 w-80 max-w-full animate-pulse rounded-xl bg-slate-100" />
            <div className="h-11 w-64 max-w-full animate-pulse rounded-xl bg-slate-100" />
          </div>
        </div>
        <p className="mb-6 text-[11px] leading-relaxed text-slate-500">Loading sealed product rankings…</p>
        <div className="grid items-start gap-5 lg:grid-cols-2">
          {["Newer releases", "Older & vintage"].map((title) => (
            <div key={title} className="rounded-2xl border border-slate-200/90 bg-slate-50/50 p-3.5 shadow-2xs sm:p-4">
              <div className="mb-3 border-b border-slate-200 pb-3">
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-900">{title}</h2>
                <div aria-hidden="true" className="mt-3 h-3 w-48 animate-pulse rounded bg-slate-200" />
              </div>
              <div aria-hidden="true" className="space-y-2">{[0, 1, 2].map((n) => <div key={n} className="h-24 animate-pulse rounded-xl border border-slate-200/80 bg-white" />)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
