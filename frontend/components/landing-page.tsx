"use client";

import { HomeLiveStats } from "@/components/home-live-stats";
import { HomeTrendingCard } from "@/components/home-trending-card";
import { CacheNotice, useCacheNotice } from "@/components/cache-notice";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "@/components/card-image";
import { SearchAutocomplete } from "@/components/search-autocomplete";
import { HistorySparkline } from "@/components/market-history-panel";
import { RecentlyViewed } from "@/components/recently-viewed";
import { openCommandPalette } from "@/components/command-palette";
import { FEATURED_POKEMON } from "@/lib/featured-pokemon";
import { cardImageUrl, getHomeOverview } from "@/lib/api";
import { useCurrency } from "@/context/currency-context";
import type { GameLanguage } from "@/types/card";
import type { HomeHighlight, HomeOverview } from "@/types/home";

const POPULAR = ["Charizard", "Pikachu", "Umbreon", "151", "Evolving Skies"];
const LANGUAGES: [GameLanguage, string][] = [["all", "All"], ["pokemon", "English"], ["pokemon-japan", "Japanese"]];
const TOOLS = [
  { id: "movers", title: "Follow the market", label: "Market Movers", href: "/market-movers", description: "See which cards are gaining ground and which are cooling off." },
  { id: "sealed", title: "Compare sealed products", label: "Sealed Signals", href: "/sealed-signals", description: "Explore newer and vintage products side by side." },
  { id: "binder", title: "Build your collection", label: "Your Binder", href: "/binder", description: "Organize your cards in a personal, visual collector’s binder." },
  { id: "catalog", title: "Find your next card", label: "Card Catalog", href: "/catalog", description: "Browse English and Japanese sets, artwork, and market prices." },
  { id: "grading", title: "Explore grading spreads", label: "Grading Profitability", href: "/grading-profit", description: "Compare raw and graded prices with your grading costs." },
  { id: "pokedex", title: "Rediscover a favorite", label: "National Pokédex", href: "/pokedex", description: "Meet the Pokémon behind the cards. Explore species and evolutions." },
] as const;
const panel = "rounded-2xl border border-slate-200 bg-white shadow-2xs";
const hover = "transition-colors hover:border-emerald-300 hover:shadow-sm motion-safe:transition motion-safe:duration-200 motion-safe:hover:-translate-y-0.5 focus-visible:outline-emerald-600";
const pill = "min-h-9 rounded-lg px-3 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-200 aria-pressed:bg-slate-900 aria-pressed:text-white focus-visible:outline-emerald-600";

function dateLabel(value: string | null): string {
  if (!value) return "Unavailable";
  const date = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(date);
}

function MarketCard({ title, item, href, loading }: { title: string; item: HomeHighlight | null; href: string; loading: boolean }) {
  const { formatPrice } = useCurrency();
  if (!item) return <div className={`${panel} p-5`}>
    <h3 className="text-xs font-semibold text-slate-500">{title}</h3>
    {loading ? <div role="status" className="mt-5 space-y-3"><span className="text-xs text-slate-500">Loading {title}…</span><div className="h-16 rounded-lg bg-slate-100 motion-safe:animate-pulse" /><div className="h-5 w-32 rounded bg-slate-100 motion-safe:animate-pulse" /></div> : <><p className="mt-6 text-sm font-semibold text-slate-700">No qualifying price change available.</p><Link href={href} className="mt-6 inline-block text-xs font-bold text-emerald-700 hover:underline">Explore market data →</Link></>}
  </div>;
  const down = item.change_percent < 0;
  return <Link href={`/cards/${encodeURIComponent(item.card_id)}`} prefetch={false} className={`${panel} ${hover} flex flex-col p-5`}>
    <div className="flex items-center justify-between gap-2"><h3 className="text-xs font-semibold text-slate-500">{title}</h3><span className={`rounded-md border px-2 py-1 text-xs font-bold ${down ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{item.change_percent > 0 ? "+" : ""}{item.change_percent.toFixed(1)}%</span></div>
    <div className="my-5 flex items-center gap-4">
      <div className="flex h-24 w-20 shrink-0 items-center justify-center rounded-xl bg-slate-50"><Image src={cardImageUrl(item.image_url)} alt="" width={64} height={88} className="h-22 w-16 object-contain" /></div>
      <div className="min-w-0"><p className="line-clamp-2 text-sm font-bold leading-relaxed text-slate-950">{item.name}</p><p className="mt-1 text-[11px] text-slate-500">{item.set_name}{item.printing ? ` · ${item.printing}` : ""}</p><p className="mt-2 text-xl font-bold tracking-tight">{formatPrice(item.market_price)}</p></div>
    </div>
    <div className="mt-auto border-t border-slate-100 pt-3 text-[10px] leading-relaxed text-slate-500">
      <p className={item.price_freshness === "stale" ? "text-amber-800" : ""}>{item.market_price_as_of ? `Price dated ${dateLabel(item.market_price_as_of)}${item.price_freshness === "stale" ? " · Stale" : ""}` : "Price date unavailable"}</p>
      <p>Observed {dateLabel(item.observed_at)} · 30-day change</p>
    </div>
  </Link>;
}

function ToolPreview({ id, data }: { id: typeof TOOLS[number]["id"]; data: HomeOverview | null }) {
  if (id === "movers") return <div className="flex h-full flex-col justify-center px-4">
    {data?.gainer && data.gainer.history.filter((p) => p.market_price != null).length >= 2 ? <><HistorySparkline points={data.gainer.history} /><p className="truncate text-[10px] text-slate-500">{data.gainer.name} · observed prices</p></> : <><svg aria-hidden="true" viewBox="0 0 240 64" className="h-16 w-full text-slate-200"><path d="M0 16H240 M0 32H240 M0 48H240 M40 0V64 M100 0V64 M160 0V64 M220 0V64" stroke="currentColor" fill="none" /></svg><p className="text-center text-[11px] text-slate-500">Price history · 24h / 7d / 30d</p></>}
  </div>;
  if (id === "sealed") return <div className="grid h-full grid-cols-2 gap-3 p-4" aria-hidden="true">{["Newer", "Vintage"].map((era) => <div key={era} className="rounded-xl border border-slate-200 bg-white p-3"><p className="text-[10px] font-bold uppercase text-slate-600">{era}</p><div className="mt-3 h-2 w-4/5 rounded bg-emerald-100" /><div className="mt-2 h-2 w-3/5 rounded bg-slate-100" /><p className="mt-3 text-[9px] text-slate-400">30D / 90D</p></div>)}</div>;
  if (id === "binder") return <div aria-hidden="true" className="mx-auto grid h-full w-40 grid-cols-3 gap-1.5 p-3">{Array.from({ length: 9 }, (_, i) => <div key={i} className={`rounded border ${i < 4 ? "border-emerald-200 bg-emerald-50" : "border-dashed border-slate-300 bg-white/70"}`} />)}</div>;
  if (id === "grading") return <div aria-hidden="true" className="flex h-full items-center justify-center gap-5"><div className="flex h-20 w-16 items-center justify-center rounded-lg border border-slate-200 bg-white text-[10px] font-bold text-slate-500">RAW</div><span className="text-xl text-slate-400">→</span><div className="rounded-lg border-4 border-slate-200 bg-white p-2"><div className="mb-1 h-2 rounded bg-rose-100" /><div className="flex h-16 w-12 items-center justify-center rounded border border-slate-100 text-[10px] font-bold text-slate-600">GRADED</div></div></div>;
  if (id === "catalog") {
    const artwork = data?.releases.filter((r) => r.image_url && !r.upcoming).slice(0, 3) ?? [];
    return <div className="flex h-full items-center justify-center gap-3" aria-hidden="true">{artwork.length ? artwork.map((set) => <Image key={set.id} src={cardImageUrl(set.image_url!)} alt="" width={60} height={84} className="h-24 w-16 object-contain" />) : ["EN", "JP", "+"].map((text) => <div key={text} className="flex h-20 w-14 items-center justify-center rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-400">{text}</div>)}</div>;
  }
  return <div className="flex h-full items-center justify-center gap-3" aria-hidden="true">{FEATURED_POKEMON.slice(0, 3).map((p) => <Image key={p.id} src={p.artwork} alt="" width={76} height={76} unoptimized className="h-20 w-20 object-contain" />)}</div>;
}

export function LandingPage() {
  const [cacheMetadata, setCacheMetadata] = useCacheNotice();
  const [data, setData] = useState<HomeOverview | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [language, setLanguage] = useState<GameLanguage>("all");
  const [upcoming, setUpcoming] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setError(false);
    getHomeOverview(controller.signal, { bypassCache: attempt > 0, onCache: (metadata) => { if (!controller.signal.aborted) setCacheMetadata(metadata); } }).then((result) => { if (!controller.signal.aborted) setData(result); }).catch((err) => {
      if (!controller.signal.aborted) { console.error("Homepage overview failed:", err); setError(true); }
    });
    return () => controller.abort();
  }, [attempt]);
  const loading = !data && !error;
  const releases = (data?.releases ?? []).filter((r) => (language === "all" || r.game === language) && r.upcoming === upcoming)
    .sort((a, b) => (upcoming ? a.release_date.localeCompare(b.release_date) : b.release_date.localeCompare(a.release_date)) || a.id.localeCompare(b.id));

  return <div className="min-h-screen bg-[#f7f8f6] font-mono text-slate-950">
    <section className="relative z-10 overflow-visible border-b border-slate-200/80 bg-white px-4 py-8 sm:px-6 sm:py-10 lg:px-8 lg:py-12">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden"><div className="absolute -right-20 -top-40 h-[550px] w-[700px] rounded-full bg-[radial-gradient(ellipse,_#d1fae5_0%,_transparent_65%)] opacity-60" /></div>
      <div className="relative mx-auto max-w-[1600px]">
        <div className="grid items-center gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(300px,420px)] lg:gap-10 xl:gap-14">
          <div className="relative z-10 min-w-0">
            <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-600"><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-emerald-500" />For the love of collecting</p>
            <h1 className="text-4xl font-bold leading-[1.08] tracking-tight sm:text-5xl lg:text-7xl xl:text-[clamp(4.5rem,5.5vw,6rem)]">Your next card<br /><span className="text-emerald-700">starts here.</span></h1>
            <p className="mt-5 text-sm leading-relaxed text-slate-600 sm:text-base xl:text-lg">Discover Pokémon cards, compare market prices, and build a collection that’s yours.</p>
            <div className="mt-6 w-full lg:w-3/4"><SearchAutocomplete fullWidth /></div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]"><span className="text-slate-400">Try:</span>{POPULAR.map((q) => <Link key={q} href={`/catalog?q=${encodeURIComponent(q)}`} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-slate-600 transition-colors hover:border-emerald-300 hover:text-emerald-800">{q}</Link>)}</div>
            <div className="mt-5 flex flex-wrap items-center gap-3"><Link href="/catalog" className="rounded-xl bg-slate-900 px-5 py-3 text-xs font-bold text-white transition-colors hover:bg-slate-700">Explore the catalog →</Link><Link href="/binder" className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50">Open your binder</Link><button type="button" onClick={openCommandPalette} className="rounded-lg px-2 py-3 text-xs text-slate-500 hover:text-slate-900">Quick jump <kbd className="ml-1 rounded border border-slate-200 px-1.5 py-0.5 text-[10px]">⌘K / Ctrl K</kbd></button></div>
            <nav aria-label="Explore the market" className="mt-6 grid grid-cols-3 gap-2 border-t border-slate-200 pt-5 sm:gap-3">
              {[
                { href: "/top-volume", title: "Trending", detail: "Explore the top 50" },
                { href: "/live-updates", title: "Live Comps", detail: "Latest price updates" },
                { href: "/sealed-signals", title: "Sealed Signals", detail: "Compare sealed products" },
              ].map((item) => <Link key={item.href} href={item.href} className="group rounded-xl border border-slate-200 bg-slate-50/70 p-3 transition-colors hover:border-emerald-300 hover:bg-emerald-50/50 focus-visible:outline-emerald-600 sm:p-4">
                <span className="flex items-center justify-between gap-1 text-[11px] font-bold text-slate-800 sm:text-xs">{item.title}<span aria-hidden="true" className="text-emerald-700">↗</span></span>
                <span className="mt-2 block text-[10px] leading-relaxed text-slate-500">{item.detail}</span>
              </Link>)}
            </nav>
          </div>
          <HomeTrendingCard />
        </div>
      </div>
    </section>

    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 lg:px-8">
      <section aria-labelledby="market-heading" className="pt-6 pb-4 sm:pt-8">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">A quick market check</p><h2 id="market-heading" className="mt-1 text-2xl font-bold tracking-tight">Market today</h2><p className="mt-2 text-xs leading-relaxed text-slate-500">Latest available 30-day changes across tracked products. Check price dates below.</p></div><Link href="/market-movers?period=30d" className="text-xs font-bold text-emerald-700 hover:underline">Explore movers →</Link></div>
        <CacheNotice metadata={cacheMetadata} />
        {error && <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"><span>Market and catalog data are temporarily unavailable.</span><button type="button" onClick={() => setAttempt((n) => n + 1)} className="min-h-9 rounded-lg border border-amber-300 px-3 font-bold hover:bg-amber-100">Retry data</button></div>}
        <div className="grid gap-4 md:grid-cols-3"><MarketCard title="Biggest card gainer" item={data?.gainer ?? null} href="/market-movers?period=30d" loading={loading} /><MarketCard title="Biggest card drop" item={data?.loser ?? null} href="/market-movers?period=30d" loading={loading} /><MarketCard title="Strongest sealed growth" item={data?.sealed ?? null} href="/sealed-signals" loading={loading} /></div>
        <p className="mt-3 text-[10px] leading-relaxed text-slate-400">PPT market prices · Historical changes before fees · No forecast of future returns</p>
      </section>

      <RecentlyViewed />

      <section aria-labelledby="releases-heading" className="py-10 sm:py-12">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4"><div><p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Explore the expansions</p><h2 id="releases-heading" className="mt-1 text-2xl font-bold tracking-tight">{upcoming ? "Coming to the catalog" : "Latest releases"}</h2></div><div role="group" aria-label="Release language" className="inline-flex rounded-xl border border-slate-200 bg-slate-100 p-1">{LANGUAGES.map(([value, label]) => <button key={value} type="button" aria-pressed={language === value} onClick={() => setLanguage(value)} className={pill}>{label}</button>)}</div></div>
        <div role="group" aria-label="Release timing" className="mb-4 flex gap-4 border-b border-slate-200"><button type="button" aria-pressed={!upcoming} onClick={() => setUpcoming(false)} className="border-b-2 border-transparent pb-3 text-xs font-semibold text-slate-500 aria-pressed:border-emerald-600 aria-pressed:text-emerald-800">Released</button><button type="button" aria-pressed={upcoming} onClick={() => setUpcoming(true)} className="border-b-2 border-transparent pb-3 text-xs font-semibold text-slate-500 aria-pressed:border-emerald-600 aria-pressed:text-emerald-800">Upcoming</button></div>
        {loading ? <div role="status" className="flex gap-4 overflow-hidden"><span className="text-xs text-slate-500">Loading releases…</span>{[0, 1, 2, 3].map((i) => <div key={i} className="h-64 w-56 shrink-0 rounded-2xl bg-slate-200/60 motion-safe:animate-pulse" />)}</div> : !releases.length ? <p className={`${panel} p-8 text-sm text-slate-500`}>{error ? "Release data could not be loaded." : upcoming ? "No upcoming sets listed for this language yet." : "No dated releases available for this language yet."}</p> : <div className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-4" aria-label="Set releases">
          {releases.map((set) => <Link key={set.id} href={`/catalog?set=${encodeURIComponent(set.id)}&game=${set.game}`} prefetch={false} className={`${panel} ${hover} w-56 shrink-0 snap-start overflow-hidden`}>
            <div className="relative flex h-36 items-center justify-center border-b border-slate-100 bg-slate-50 p-4">{set.image_url ? <Image src={cardImageUrl(set.image_url)} alt={`Product artwork from ${set.name}`} width={108} height={116} className="h-28 w-28 object-contain" /> : <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Artwork pending</span>}<span className="absolute left-3 top-3 rounded border border-slate-200 bg-white/95 px-1.5 py-0.5 text-[9px] font-bold text-slate-500">{set.game === "pokemon" ? "EN" : "JP"}</span></div>
            <div className="p-4"><p className={`text-[10px] font-semibold ${set.upcoming ? "text-amber-700" : "text-emerald-700"}`}>{set.upcoming ? "Upcoming" : "Released"} · {dateLabel(set.release_date)}</p><h3 className="mt-2 line-clamp-2 min-h-10 text-sm font-bold leading-5">{set.name}</h3><p className="mt-3 text-[10px] text-slate-500">{set.card_count.toLocaleString("en-US")} catalog products <span aria-hidden="true">→</span></p></div>
          </Link>)}
        </div>}
        <p className="mt-2 text-[10px] leading-relaxed text-slate-400">Catalog release dates · Product artwork from each set · Upcoming dates may change</p>
      </section>

      <section aria-labelledby="tools-heading" className="border-t border-slate-200 py-10 sm:py-12">
        <div className="mb-6"><p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Made for your collection</p><h2 id="tools-heading" className="mt-1 text-2xl font-bold tracking-tight">A little curiosity. A lot to discover.</h2></div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{TOOLS.map((tool) => <Link key={tool.id} href={tool.href} prefetch={false} className={`${panel} ${hover} group overflow-hidden`}>
          <div className="h-36 border-b border-slate-100 bg-slate-50/80"><ToolPreview id={tool.id} data={data} /></div>
          <div className="p-5"><div className="flex items-center justify-between gap-3"><p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{tool.label}</p><span aria-hidden="true" className="text-slate-400 group-hover:text-emerald-600">↗</span></div><h3 className="mt-2 text-base font-bold">{tool.title}</h3><p className="mt-2 text-xs leading-relaxed text-slate-500">{tool.description}</p></div>
        </Link>)}</div>
        <div className="mt-5 flex flex-wrap gap-5 text-xs font-semibold text-slate-600"><Link href="/top-volume" className="hover:text-emerald-700 hover:underline">Trending & reported sales →</Link><Link href="/live-updates" className="hover:text-emerald-700 hover:underline">Latest price observations →</Link></div>
      </section>

      <section aria-labelledby="species-heading" className="border-t border-slate-200 py-10 sm:py-12">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3"><h2 id="species-heading" className="text-xl font-bold tracking-tight">Who’s your favorite?</h2><Link href="/pokedex" className="text-xs font-bold text-emerald-700 hover:underline">Explore the Pokédex →</Link></div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">{FEATURED_POKEMON.map((pokemon) => <Link key={pokemon.id} href={`/pokemon/${pokemon.id}`} prefetch={false} className={`${panel} ${hover} flex flex-col items-center p-4`}><Image src={pokemon.artwork} alt="" width={76} height={76} className="h-20 w-20 object-contain" unoptimized /><span className="mt-3 text-[10px] text-slate-400">#{String(pokemon.id).padStart(4, "0")}</span><h3 className="mt-1 text-xs font-bold">{pokemon.name}</h3></Link>)}</div>
      </section>

      <section aria-labelledby="coverage-heading" className="border-t border-slate-200 py-10 sm:py-12">
        <div className="mb-5"><h2 id="coverage-heading" className="text-lg font-bold">Behind the collection</h2><p className="mt-2 text-xs leading-relaxed text-slate-500">The sources behind the catalog, price comparisons, and Pokémon reference data.</p></div>
        <HomeLiveStats />
        <div className="mt-8 grid gap-5 text-xs leading-relaxed text-slate-500 sm:grid-cols-3"><p><strong className="block text-slate-700">Pokémon Price Tracker</strong>Catalog details and per-printing market prices. Availability and price dates vary by product.</p><p><strong className="block text-slate-700">eBay</strong>Matched active listings for price comparisons. Asking prices do not establish completed sales.</p><p><strong className="block text-slate-700">PokéAPI</strong>Species artwork and reference data for exploring the Pokémon behind your cards.</p></div>
      </section>
    </div>
  </div>;
}
