import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { getPokemonByIdOrSlug } from "@/lib/pokedex-data";
import { getPokemonDetail, TYPE_THEMES, formatDexNumber } from "@/lib/pokeapi";
import { getPokemonCards } from "@/lib/api";
import { PokemonAudioPlayer } from "@/components/pokemon-audio-player";
import { PokemonCardsView } from "@/components/pokemon-cards-view";
import {
  PokemonCycleHeader,
  PokemonArrowButton,
  PokemonKeyboardCycle,
} from "@/components/pokemon-cycle-nav";
import type { PokemonType } from "@/types/pokemon";

export const dynamic = "force-dynamic";
export const runtime = "edge";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ ref?: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const pokemon = getPokemonByIdOrSlug(id);
  if (!pokemon) {
    return { title: "Pokémon Not Found | CardboardDex" };
  }
  return {
    title: `${pokemon.name} (${formatDexNumber(pokemon.id)}) Cards & Pokédex | CardboardDex`,
    description: `Browse all trading cards, verified market prices, PSA graded comps, and official Pokédex data for ${pokemon.name} (${formatDexNumber(pokemon.id)}).`,
  };
}

export default async function PokemonDetailPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const sp = searchParams ? await searchParams : undefined;
  const basePokemon = getPokemonByIdOrSlug(id);
  if (!basePokemon) {
    notFound();
  }

  // Calculate adjacent Pokémon for cycling (wrap-around 1 <-> 1025)
  const prevId = basePokemon.id > 1 ? basePokemon.id - 1 : 1025;
  const nextId = basePokemon.id < 1025 ? basePokemon.id + 1 : 1;
  const prevPokemon = getPokemonByIdOrSlug(prevId) ?? basePokemon;
  const nextPokemon = getPokemonByIdOrSlug(nextId) ?? basePokemon;

  // Fetch live PokeAPI detail & CardboardDex cards in parallel
  const [detail, cardsData] = await Promise.all([
    getPokemonDetail(basePokemon.id),
    getPokemonCards(basePokemon.name, { limit: 100, ref: sp?.ref }).catch((err) => {
      console.error(`[PokemonPage] Error fetching cards for ${basePokemon.name}:`, err);
      return {
        pokemon_name: basePokemon.name,
        total_cards: 0,
        highest_price: null,
        lowest_price: null,
        available_sets: [],
        cards: [],
      };
    }),
  ]);

  const pokemon = detail ?? {
    id: basePokemon.id,
    name: basePokemon.name,
    slug: basePokemon.slug,
    types: basePokemon.types,
    height: 1.0,
    weight: 20.0,
    genus: "Pokémon",
    flavorText: `${basePokemon.name} is a Pokémon from the ${basePokemon.region} region.`,
    stats: [],
    baseStatTotal: 0,
    abilities: [],
    cryUrl: null,
    artwork: basePokemon.artwork,
  };

  const primaryType: PokemonType = pokemon.types[0] || "normal";
  const theme = TYPE_THEMES[primaryType];

  return (
    <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] py-8 text-slate-950">
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 lg:px-8">
        {/* Navigation Breadcrumb & Pokédex Quick Cycling Header */}
        <PokemonCycleHeader
          currentPokemon={{
            id: pokemon.id,
            name: pokemon.name,
            region: basePokemon.region,
          }}
          prevPokemon={prevPokemon}
          nextPokemon={nextPokemon}
        />
        <PokemonKeyboardCycle prevId={prevPokemon.id} nextId={nextPokemon.id} />

        {/* Hero Showcase Card */}
        <section className="relative mb-8 overflow-hidden rounded-3xl border border-slate-200/90 bg-white p-6 shadow-sm sm:p-8 lg:p-10">
          {/* Subtle Ambient Glow */}
          <div
            className="pointer-events-none absolute -right-16 -top-16 h-96 w-96 rounded-full opacity-20 blur-3xl"
            style={{ background: theme.glow }}
          />

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:gap-12 items-center">
            {/* Artwork Column (Left) with Left and Right Cycling Arrows */}
            <div className="lg:col-span-4 flex flex-col items-center justify-center">
              <div className="relative flex w-full items-center justify-center gap-2 sm:gap-3">

                <div
                  className="relative flex h-60 w-60 sm:h-72 sm:w-72 items-center justify-center rounded-3xl p-5 sm:p-6"
                  style={{
                    background: `radial-gradient(circle, ${theme.glow} 0%, rgba(255,255,255,0) 70%)`,
                  }}
                >
                  <Image
                    src={pokemon.artwork}
                    alt={pokemon.name}
                    fill
                    priority
                    sizes="(max-width: 640px) 240px, 300px"
                    className="object-contain drop-shadow-xl transition-transform duration-300 hover:scale-105"
                  />
                </div>
              </div>

              {/* Audio Cry Button */}
              {pokemon.cryUrl && (
                <div className="mt-4">
                  <PokemonAudioPlayer cryUrl={pokemon.cryUrl} pokemonName={pokemon.name} />
                </div>
              )}
            </div>

            {/* Information Column (Right) */}
            <div className="lg:col-span-8">
              {/* Top Meta: Dex number & Genus */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-bold text-slate-400">
                  {formatDexNumber(pokemon.id)}
                </span>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                  {pokemon.genus}
                </span>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                  Gen {basePokemon.generation} · {basePokemon.region}
                </span>
              </div>

              {/* Title & Type Badges */}
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <h1 className="text-3xl font-black tracking-tight text-slate-900 sm:text-4xl lg:text-5xl">
                  {pokemon.name}
                </h1>
                <div className="flex items-center gap-1.5">
                  {pokemon.types.map((t) => {
                    const tTheme = TYPE_THEMES[t];
                    return (
                      <span
                        key={t}
                        className={`rounded-lg px-2.5 py-1 text-xs font-bold uppercase tracking-wider text-white shadow-2xs ${tTheme.badge}`}
                      >
                        {tTheme.name}
                      </span>
                    );
                  })}
                </div>
              </div>

              {/* Physical Attributes Bar */}
              <div className="mt-4 flex flex-wrap items-center gap-4 text-xs font-semibold text-slate-600 border-y border-slate-100 py-2.5">
                <div>
                  <span className="text-slate-400">Height:</span>{" "}
                  <span className="font-bold text-slate-800">
                    {pokemon.height} m ({(pokemon.height * 3.28084).toFixed(1)} ft)
                  </span>
                </div>
                <div>
                  <span className="text-slate-400">Weight:</span>{" "}
                  <span className="font-bold text-slate-800">
                    {pokemon.weight} kg ({(pokemon.weight * 2.20462).toFixed(1)} lbs)
                  </span>
                </div>
                {pokemon.abilities && pokemon.abilities.length > 0 && (
                  <div>
                    <span className="text-slate-400">Abilities:</span>{" "}
                    <span className="font-bold text-slate-800">
                      {pokemon.abilities.join(", ")}
                    </span>
                  </div>
                )}
              </div>

              {/* Flavor Text Quote */}
              <div className="mt-4 rounded-2xl bg-slate-50/80 p-4 border border-slate-100 text-xs sm:text-sm italic text-slate-700 leading-relaxed">
                &ldquo;{pokemon.flavorText}&rdquo;
              </div>

              {/* Base Stats Breakdown */}
              {pokemon.stats.length > 0 && (
                <div className="mt-5">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-600 mb-2">
                    <span className="uppercase tracking-wider">Base Stats</span>
                    <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-emerald-800 font-mono">
                      BST: {pokemon.baseStatTotal}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    {pokemon.stats.map((s) => {
                      const statName = formatStatName(s.name);
                      const pct = Math.min(100, Math.round((s.baseStat / 180) * 100));
                      const barColor =
                        s.baseStat >= 90
                          ? "bg-emerald-500"
                          : s.baseStat >= 65
                          ? "bg-amber-500"
                          : "bg-slate-400";

                      return (
                        <div key={s.name} className="rounded-xl border border-slate-100 bg-slate-50 p-2 text-xs">
                          <div className="flex items-center justify-between font-semibold">
                            <span className="text-slate-500 text-[10px] uppercase font-bold">{statName}</span>
                            <span className="font-mono font-bold text-slate-900">{s.baseStat}</span>
                          </div>
                          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                            <div
                              className={`h-full rounded-full ${barColor}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
          
        </section>

        {/* Section Header: Trading Cards */}
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-black tracking-tight text-slate-900 sm:text-2xl">
              {pokemon.name} Trading Cards
            </h2>
            <p className="text-xs text-slate-500">
              Verified cards, real-time market prices, and historical comps from CardboardDex.
            </p>
          </div>
        </div>

        {/* Interactive Cards Component */}
        <PokemonCardsView
          pokemonName={pokemon.name}
          initialCards={cardsData.cards}
          availableSets={cardsData.available_sets}
          totalCards={cardsData.total_cards}
          highestPrice={cardsData.highest_price}
          lowestPrice={cardsData.lowest_price}
        />
      </div>
    </main>
  );
}

function formatStatName(name: string): string {
  switch (name) {
    case "hp":
      return "HP";
    case "attack":
      return "ATK";
    case "defense":
      return "DEF";
    case "special-attack":
      return "SP. ATK";
    case "special-defense":
      return "SP. DEF";
    case "speed":
      return "SPD";
    default:
      return name;
  }
}
