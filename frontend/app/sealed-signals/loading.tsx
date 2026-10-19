export default function SealedSignalsLoading() {
  return (
    <div className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
      <div role="status" aria-label="Loading sealed return rankings" className="mx-auto max-w-[1600px] px-4 pb-20 pt-8 font-mono sm:px-6 lg:px-8">
        <header className="mb-6">
          <p className="mb-3 text-[11px] font-semibold text-slate-500">SEALED MARKET · TCG MARKET PRICES</p>
          <h1 className="text-2xl font-black uppercase tracking-tight sm:text-4xl">Sealed Signals</h1>
          <p className="mt-2 text-sm text-slate-600">Compare price growth across newer releases and older sealed products.</p>
        </header>
        <div aria-hidden="true" className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((n) => <div key={n} className="h-28 animate-pulse rounded-xl border border-slate-200 bg-white motion-reduce:animate-none" />)}
        </div>
        <div aria-hidden="true" className="mb-6 h-44 animate-pulse rounded-2xl border border-slate-200 bg-white motion-reduce:animate-none" />
        <p className="mb-6 text-xs text-slate-500">Loading sealed product rankings…</p>
        <div className="grid gap-10 lg:grid-cols-2">
          {["Newer releases", "Older & vintage"].map((title) => <div key={title}>
            <h2 className="mb-4 text-lg font-bold">{title}</h2>
            <div aria-hidden="true" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">{[0, 1].map((n) => <div key={n} className="h-96 animate-pulse rounded-2xl border border-slate-200 bg-white motion-reduce:animate-none" />)}</div>
          </div>)}
        </div>
      </div>
    </div>
  );
}
