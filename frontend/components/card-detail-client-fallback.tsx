"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";

import { BackButton } from "@/components/back-button";
import { PriceDashboard } from "@/components/price-dashboard";
import { ShopOnEbayButton } from "@/components/shop-ebay-button";
import { AddToBinderButton } from "@/components/binder/add-to-binder-button";
import { HoloCard } from "@/components/ui/holo-card";
import { cardImageUrl, getCard, getCardPricing } from "@/lib/api";
import { formatDexNumber } from "@/lib/pokeapi";
import { findPokemonForCardName } from "@/lib/pokedex-data";
import type { CardDetail, CardPricing } from "@/types/card";

type Props = {
  cardId: string;
  refParam?: string;
};

function formatDate(value: string | null): string {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function CardDetailClientFallback({ cardId, refParam }: Props) {
  const [card, setCard] = useState<CardDetail | null>(null);
  const [pricing, setPricing] = useState<CardPricing | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isNotFound, setIsNotFound] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fetchCardData = async () => {
    setIsLoading(true);
    setIsNotFound(false);
    setErrorMsg(null);

    try {
      const [fetchedCard, fetchedPricing] = await Promise.all([
        getCard(cardId, { ref: refParam }),
        getCardPricing(cardId).catch((err) => {
          console.warn("[CardFallback] Pricing fetch non-fatal error:", err);
          return null;
        }),
      ]);

      if (!fetchedCard) {
        setIsNotFound(true);
      } else {
        setCard(fetchedCard);
        setPricing(fetchedPricing);
      }
    } catch (err) {
      console.error("[CardFallback] Failed fetching card data:", err);
      setErrorMsg(err instanceof Error ? err.message : "Failed to load card profile");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchCardData();
  }, [cardId, refParam]);

  if (isLoading) {
    return (
      <main className="mx-auto min-h-[70vh] max-w-7xl px-5 py-9 sm:px-8 sm:py-12">
        <BackButton />
        <div className="mt-8 grid items-start gap-8 rounded-3xl border border-stone-200 bg-white p-5 shadow-[0_18px_55px_rgba(33,45,25,0.06)] md:grid-cols-[320px_1fr] md:gap-12 md:p-8 animate-pulse">
          <div className="h-[430px] rounded-2xl bg-slate-100" />
          <div className="space-y-4 pt-4">
            <div className="h-6 w-32 rounded bg-slate-100" />
            <div className="h-10 w-3/4 rounded bg-slate-100" />
            <div className="h-4 w-20 rounded bg-slate-100" />
            <div className="h-12 w-48 rounded-xl bg-slate-100 mt-6" />
            <div className="h-40 rounded-xl bg-slate-100 mt-8" />
          </div>
        </div>
      </main>
    );
  }

  if (isNotFound) {
    return (
      <main className="mx-auto min-h-[70vh] max-w-2xl px-5 py-20 text-center sm:px-8">
        <p className="text-sm font-medium text-zinc-500">404</p>
        <h1 className="mt-3 text-2xl font-semibold text-zinc-950">Card not found</h1>
        <p className="mt-2 text-sm text-slate-500">
          The requested card could not be located in the catalog database.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link
            className="rounded-xl bg-slate-900 px-5 py-2.5 text-xs font-bold text-white shadow-xs transition hover:bg-slate-800"
            href="/catalog"
          >
            Return to the catalog
          </Link>
          <button
            type="button"
            onClick={() => void fetchCardData()}
            className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50"
          >
            Try again
          </button>
        </div>
      </main>
    );
  }

  if (errorMsg && !card) {
    return (
      <main className="mx-auto min-h-[70vh] max-w-2xl px-5 py-20 text-center sm:px-8">
        <p className="text-sm font-medium text-red-500">Connection Error</p>
        <h1 className="mt-3 text-2xl font-semibold text-zinc-950">Unable to load card profile</h1>
        <p className="mt-2 text-sm text-slate-500">{errorMsg}</p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={() => void fetchCardData()}
            className="rounded-xl bg-slate-900 px-5 py-2.5 text-xs font-bold text-white shadow-xs transition hover:bg-slate-800"
          >
            Retry
          </button>
          <Link
            className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50"
            href="/catalog"
          >
            Return to catalog
          </Link>
        </div>
      </main>
    );
  }

  if (!card) return null;

  const number = card.printed_total ? `${card.number}/${card.printed_total}` : card.number;
  const setCatalogUrl = `/catalog?set=${encodeURIComponent(card.set_id)}${
    card.series === "Pokemon Japan" ? "&game=pokemon-japan" : ""
  }`;
  const species = findPokemonForCardName(card.name);

  return (
    <main className="mx-auto min-h-[70vh] max-w-7xl px-5 py-9 sm:px-8 sm:py-12">
      <BackButton />

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

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <ShopOnEbayButton card={card} variant="hero" />
            <AddToBinderButton cardId={card.id} cardName={card.name} />
          </div>

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
      {pricing ? <PriceDashboard pricing={pricing} cardMeta={card} /> : null}
    </main>
  );
}
