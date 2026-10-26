import type { Metadata } from "next";
import { cache, Suspense, ViewTransition } from "react";
import { SectionLoadingBar } from "@/components/section-loading-bar";
import Image from "@/components/card-image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BackButton } from "@/components/back-button";
import { CardDetailClientFallback } from "@/components/card-detail-client-fallback";
import { RememberViewedCard } from "@/components/recently-viewed";
import { PriceDashboard } from "@/components/price-dashboard";
import { ShopOnEbayButton } from "@/components/shop-ebay-button";
import { StickyCardActions } from "@/components/sticky-card-actions";
import { AddToBinderButton } from "@/components/binder/add-to-binder-button";
import { HoloCard } from "@/components/ui/holo-card";
import { cardImageUrl, getCard, getCardPricing } from "@/lib/api";
import { formatDexNumber } from "@/lib/pokeapi";
import { findPokemonForCardName } from "@/lib/pokedex-data";

export const dynamic = "force-dynamic";
export const runtime = "edge";

type CardPageProps = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ ref?: string }>;
};

// One API read per request, shared by the page and its metadata.
const loadCard = cache((id: string, ref?: string) => getCard(id, { ref }));

export async function generateMetadata({ params, searchParams }: CardPageProps): Promise<Metadata> {
  const { id } = await params;
  const sp = searchParams ? await searchParams : undefined;
  try {
    const card = await loadCard(id, sp?.ref);
    if (!card) return { title: "Card not found · CardboardDex" };
    const number = card.printed_total ? `${card.number}/${card.printed_total}` : card.number;
    // Promo names often already carry the number ("Pikachu - 227/S-P").
    const label = card.number && card.name.includes(card.number) ? card.name : `${card.name} ${number}`;
    const title = `${label} · ${card.set_name} Price · CardboardDex`;
    const price = card.market_price != null
      ? ` Market price ${new Intl.NumberFormat("en-US", { style: "currency", currency: card.market_currency || "USD" }).format(card.market_price)}.`
      : "";
    const description = `${label} from ${card.set_name}.${price} Price history, graded comps and matched eBay listings.`;
    const image = card.image_url ? cardImageUrl(card.image_url) : undefined;
    return {
      title, description,
      alternates: { canonical: `/cards/${encodeURIComponent(card.id)}` },
      openGraph: { title, description, url: `/cards/${encodeURIComponent(card.id)}`, images: image ? [{ url: image, alt: card.name }] : undefined },
      twitter: { title, description, images: image ? [image] : undefined },
    };
  } catch (err) {
    console.error(`[CardPage] Metadata fetch failed for ${id}:`, err);
    return { title: "CardboardDex - Pokémon Card Price" };
  }
}

function formatDate(value: string | null): string {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export default async function CardPage({ params, searchParams }: CardPageProps) {
  const { id } = await params;
  const sp = searchParams ? await searchParams : undefined;
  return (
    <main className="mx-auto min-h-[70vh] max-w-7xl px-5 py-9 sm:px-8 sm:py-12">
      <BackButton />
      <Suspense fallback={<SectionLoadingBar className="mt-8" label="Loading card details…" />}>
        {/* Card details rise in once when they arrive (.card-reveal in globals.css); "none"
            keeps later in-page transitions, like chart range changes, from re-animating it. */}
        <ViewTransition enter="card-reveal" default="none">
          <CardContent id={id} refParam={sp?.ref} />
        </ViewTransition>
      </Suspense>
    </main>
  );
}

async function CardContent({ id, refParam }: { id: string; refParam?: string }) {
  // Start both reads together, but let card details render before pricing resolves.
  const pricing = getCardPricing(id).catch((err) => {
    console.error(`[CardPage] Failed loading pricing for ${id}:`, err);
    return null;
  });
  let card = null;
  let fetchFailed = false;

  try {
    card = await loadCard(id, refParam);
  } catch (err) {
    console.error(`[CardPage] Failed fetching card ${id} data on Edge SSR:`, err);
    fetchFailed = true;
  }

  if (fetchFailed) {
    return <CardDetailClientFallback cardId={id} refParam={refParam} />;
  }

  if (!card) notFound();
  const number = card.printed_total ? `${card.number}/${card.printed_total}` : card.number;
  const setCatalogUrl = `/catalog?set=${encodeURIComponent(card.set_id)}${
    card.series === "Pokemon Japan" ? "&game=pokemon-japan" : ""
  }`;
  const species = findPokemonForCardName(card.name);

  return (
    <>
      <div className="mt-8 grid items-start gap-8 rounded-3xl border border-stone-200 bg-white p-5 shadow-[0_18px_55px_rgba(33,45,25,0.06)] md:grid-cols-[320px_1fr] md:gap-12 md:p-8">
        <div className="self-start overflow-hidden rounded-2xl bg-[radial-gradient(circle_at_top,_#f1fee7,_#f5f5f4_70%)] p-5">
          <HoloCard maxTilt={14} rarity={card.rarity} className="mx-auto block w-full rounded-xl">
            <Image
              alt={`${card.name} from ${card.set_name}`}
              className="mx-auto block h-auto w-full rounded-xl drop-shadow-[0_18px_18px_rgba(15,23,42,0.18)]"
              height={440}
              priority
              quality={75}
              src={cardImageUrl(card.image_url)}
              sizes="(max-width: 768px) 80vw, 320px"
              width={320}
            />
          </HoloCard>
        </div>

        <section className="pt-1 md:pt-2">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={setCatalogUrl}
              className="group inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-bold uppercase tracking-[0.14em] text-emerald-800 transition hover:bg-emerald-100 hover:text-emerald-950 border border-emerald-200/60"
              title={`View all cards in ${card.set_name}`}
            >
              <svg className="h-3.5 w-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <span>{card.set_name}</span>
              <span className="text-emerald-500 transition-transform duration-200 group-hover:translate-x-0.5">→</span>
            </Link>

            {species && (
              <Link
                href={`/pokemon/${species.id}`}
                className="group inline-flex items-center gap-1.5 rounded-lg bg-indigo-50 px-2.5 py-1 text-xs font-bold uppercase tracking-[0.14em] text-indigo-800 transition hover:bg-indigo-100 hover:text-indigo-950 border border-indigo-200/60"
                title={`View ${species.name} in Pokédex`}
              >
                <span className="font-mono text-[11px] text-indigo-500 font-bold">{formatDexNumber(species.id)}</span>
                <span>{species.name}</span>
                <span className="text-indigo-400 transition-transform duration-200 group-hover:translate-x-0.5">→</span>
              </Link>
            )}
          </div>

          <h1 className="mt-2.5 text-3xl font-bold tracking-[-0.035em] text-slate-950 sm:text-4xl md:text-5xl">
            {card.name}
          </h1>
          <p className="mt-2 font-mono text-sm text-slate-500">#{number}</p>

          <StickyCardActions card={card}>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <ShopOnEbayButton card={card} variant="hero" />
              <AddToBinderButton cardId={card.id} cardName={card.name} />
              <Link href={`/compare?ids=${encodeURIComponent(card.id)}`} prefetch={false}
                className="rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:text-slate-950">
                Compare
              </Link>
            </div>
          </StickyCardActions>

          <dl className="mt-6 divide-y divide-stone-200 border-y border-stone-200">
            {species && (
              <div className="grid grid-cols-2 gap-4 py-2.5 sm:py-3">
                <dt className="text-sm text-zinc-500">Pokédex Species</dt>
                <dd className="text-right text-sm font-medium">
                  <Link
                    href={`/pokemon/${species.id}`}
                    className="group inline-flex items-center gap-1.5 font-semibold text-indigo-700 hover:text-indigo-800 hover:underline"
                    title={`View ${species.name} in Pokédex`}
                  >
                    <span className="font-mono text-xs text-indigo-500">{formatDexNumber(species.id)}</span>
                    <span>{species.name}</span>
                    <span className="text-indigo-400 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true">→</span>
                  </Link>
                </dd>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4 py-2.5 sm:py-3">
              <dt className="text-sm text-zinc-500">Set</dt>
              <dd className="text-right text-sm font-medium">
                <Link
                  href={setCatalogUrl}
                  className="group inline-flex items-center gap-1 font-semibold text-emerald-700 hover:text-emerald-800 hover:underline"
                  title={`View all cards in ${card.set_name}`}
                >
                  <span>{card.set_name}</span>
                  <span className="text-emerald-500 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true">→</span>
                </Link>
              </dd>
            </div>

            <div className="grid grid-cols-2 gap-4 py-2.5 sm:py-3">
              <dt className="text-sm text-zinc-500">Series</dt>
              <dd className="text-right text-sm font-medium text-zinc-950">
                {card.series ?? "Not provided"}
              </dd>
            </div>
            <div className="grid grid-cols-2 gap-4 py-2.5 sm:py-3">
              <dt className="text-sm text-zinc-500">Rarity</dt>
              <dd className="text-right text-sm font-medium text-zinc-950">
                {card.rarity || "None"}
              </dd>
            </div>
            <div className="grid grid-cols-2 gap-4 py-2.5 sm:py-3">
              <dt className="text-sm text-zinc-500">Release date</dt>
              <dd className="text-right text-sm font-medium text-zinc-950">
                {formatDate(card.release_date)}
              </dd>
            </div>
          </dl>
        </section>
      </div>
      <RememberViewedCard card={card} />
      <Suspense fallback={<SectionLoadingBar label="Loading prices and market comparisons…" />}>
        <CardPrices card={card} pricing={pricing} />
      </Suspense>
    </>
  );
}

async function CardPrices({ card, pricing }: {
  card: NonNullable<Awaited<ReturnType<typeof getCard>>>;
  pricing: Promise<Awaited<ReturnType<typeof getCardPricing>> | null>;
}) {
  const data = await pricing;
  return data ? <PriceDashboard pricing={data} cardMeta={card} /> : <p role="alert">Pricing could not be loaded. Refresh to try again.</p>;
}
