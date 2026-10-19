type SearchFormProps = {
  query: string;
  isSearching: boolean;
  onQueryChange: (value: string) => void;
  onClear: () => void;
};

export function SearchForm({
  query,
  isSearching,
  onQueryChange,
  onClear,
}: SearchFormProps) {
  return (
    <div role="search">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Pokémon price guide</p>
      <h1 className="mt-2 text-3xl font-bold tracking-[-0.035em] text-slate-950 sm:text-4xl">Find your next card.</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Explore a focused catalog with current PPT pricing and matched eBay asking-price comparisons.</p>
      <div className="mt-6 flex min-w-0 flex-col gap-2 sm:flex-row">
        <label className="min-w-0 flex-1">
          <span className="sr-only">Search cards or sets</span>
          <span className="relative block">
          <svg aria-hidden="true" className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" viewBox="0 0 24 24">
            <path d="m21 21-4.35-4.35m2.35-5.65a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
          </svg>
          <input
            data-mobile-search
            aria-busy={isSearching}
            autoComplete="off"
            className="h-13 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-10 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
            id="card-search"
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search cards or sets"
            type="search"
            value={query}
          />
            {isSearching ? <span aria-hidden="true" className="search-spinner absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-slate-200 border-t-emerald-600" /> : null}
          </span>
        </label>
        <button
          className="h-13 rounded-xl border border-slate-200 bg-white px-5 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-default disabled:opacity-40"
          disabled={!query}
          onClick={onClear}
          type="button"
        >
          Clear
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-400">Results update as you type.</p>
    </div>
  );
}
