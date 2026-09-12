import type { PokemonDetail, PokemonStat, PokemonType } from "@/types/pokemon";
import { getPokemonByIdOrSlug } from "./pokedex-data";

export type TypeTheme = {
  name: string;
  bg: string;
  text: string;
  border: string;
  badge: string;
  gradient: string;
  glow: string;
};

export const TYPE_THEMES: Record<PokemonType, TypeTheme> = {
  normal: {
    name: "Normal",
    bg: "bg-stone-100",
    text: "text-stone-700",
    border: "border-stone-300",
    badge: "bg-stone-200/80 text-stone-800 border-stone-300",
    gradient: "from-stone-400 to-stone-500",
    glow: "rgba(168, 168, 120, 0.35)",
  },
  fire: {
    name: "Fire",
    bg: "bg-orange-50",
    text: "text-orange-700",
    border: "border-orange-300",
    badge: "bg-orange-500 text-white border-orange-600",
    gradient: "from-orange-500 via-amber-500 to-red-600",
    glow: "rgba(240, 128, 48, 0.4)",
  },
  water: {
    name: "Water",
    bg: "bg-sky-50",
    text: "text-sky-700",
    border: "border-sky-300",
    badge: "bg-sky-500 text-white border-sky-600",
    gradient: "from-sky-500 via-blue-500 to-cyan-600",
    glow: "rgba(104, 144, 240, 0.4)",
  },
  grass: {
    name: "Grass",
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    border: "border-emerald-300",
    badge: "bg-emerald-500 text-white border-emerald-600",
    gradient: "from-emerald-500 via-green-500 to-teal-600",
    glow: "rgba(120, 200, 80, 0.4)",
  },
  electric: {
    name: "Electric",
    bg: "bg-amber-50",
    text: "text-amber-800",
    border: "border-amber-300",
    badge: "bg-amber-400 text-amber-950 border-amber-500 font-bold",
    gradient: "from-amber-400 via-yellow-400 to-amber-500",
    glow: "rgba(248, 208, 48, 0.45)",
  },
  ice: {
    name: "Ice",
    bg: "bg-cyan-50",
    text: "text-cyan-700",
    border: "border-cyan-300",
    badge: "bg-cyan-400 text-cyan-950 border-cyan-500",
    gradient: "from-cyan-400 via-teal-300 to-blue-400",
    glow: "rgba(152, 216, 216, 0.4)",
  },
  fighting: {
    name: "Fighting",
    bg: "bg-rose-50",
    text: "text-rose-800",
    border: "border-rose-300",
    badge: "bg-rose-600 text-white border-rose-700",
    gradient: "from-rose-600 via-red-600 to-amber-700",
    glow: "rgba(192, 48, 40, 0.4)",
  },
  poison: {
    name: "Poison",
    bg: "bg-purple-50",
    text: "text-purple-700",
    border: "border-purple-300",
    badge: "bg-purple-600 text-white border-purple-700",
    gradient: "from-purple-600 via-fuchsia-600 to-violet-700",
    glow: "rgba(160, 64, 160, 0.4)",
  },
  ground: {
    name: "Ground",
    bg: "bg-amber-50/70",
    text: "text-amber-900",
    border: "border-amber-400",
    badge: "bg-amber-600 text-white border-amber-700",
    gradient: "from-amber-600 via-yellow-600 to-stone-600",
    glow: "rgba(224, 192, 104, 0.4)",
  },
  flying: {
    name: "Flying",
    bg: "bg-indigo-50",
    text: "text-indigo-700",
    border: "border-indigo-300",
    badge: "bg-indigo-400 text-white border-indigo-500",
    gradient: "from-indigo-400 via-sky-400 to-blue-500",
    glow: "rgba(168, 144, 240, 0.4)",
  },
  psychic: {
    name: "Psychic",
    bg: "bg-pink-50",
    text: "text-pink-700",
    border: "border-pink-300",
    badge: "bg-pink-500 text-white border-pink-600",
    gradient: "from-pink-500 via-rose-500 to-purple-600",
    glow: "rgba(248, 88, 136, 0.4)",
  },
  bug: {
    name: "Bug",
    bg: "bg-lime-50",
    text: "text-lime-800",
    border: "border-lime-300",
    badge: "bg-lime-600 text-white border-lime-700",
    gradient: "from-lime-500 via-emerald-500 to-green-600",
    glow: "rgba(168, 184, 32, 0.4)",
  },
  rock: {
    name: "Rock",
    bg: "bg-stone-100",
    text: "text-stone-800",
    border: "border-stone-400",
    badge: "bg-stone-500 text-white border-stone-600",
    gradient: "from-stone-500 via-amber-700 to-stone-700",
    glow: "rgba(184, 160, 56, 0.4)",
  },
  ghost: {
    name: "Ghost",
    bg: "bg-violet-50",
    text: "text-violet-800",
    border: "border-violet-300",
    badge: "bg-violet-700 text-white border-violet-800",
    gradient: "from-violet-700 via-purple-700 to-slate-800",
    glow: "rgba(112, 88, 152, 0.45)",
  },
  dragon: {
    name: "Dragon",
    bg: "bg-purple-50",
    text: "text-purple-900",
    border: "border-purple-400",
    badge: "bg-purple-700 text-white border-purple-800 font-bold",
    gradient: "from-purple-700 via-indigo-600 to-blue-700",
    glow: "rgba(112, 56, 248, 0.45)",
  },
  steel: {
    name: "Steel",
    bg: "bg-slate-100",
    text: "text-slate-700",
    border: "border-slate-300",
    badge: "bg-slate-400 text-slate-900 border-slate-500 font-medium",
    gradient: "from-slate-400 via-zinc-400 to-slate-500",
    glow: "rgba(184, 184, 208, 0.35)",
  },
  dark: {
    name: "Dark",
    bg: "bg-zinc-100",
    text: "text-zinc-900",
    border: "border-zinc-400",
    badge: "bg-zinc-800 text-zinc-100 border-zinc-900",
    gradient: "from-zinc-800 via-neutral-900 to-stone-900",
    glow: "rgba(112, 88, 72, 0.4)",
  },
  fairy: {
    name: "Fairy",
    bg: "bg-rose-50",
    text: "text-rose-700",
    border: "border-rose-300",
    badge: "bg-pink-400 text-pink-950 border-pink-500",
    gradient: "from-pink-400 via-rose-300 to-fuchsia-400",
    glow: "rgba(238, 153, 172, 0.4)",
  },
};

export function formatDexNumber(id: number): string {
  return `#${String(id).padStart(4, "0")}`;
}

export async function getPokemonDetail(idOrSlug: string | number): Promise<PokemonDetail | null> {
  const baseEntry = getPokemonByIdOrSlug(idOrSlug);
  const identifier = baseEntry?.id ?? idOrSlug;

  try {
    const [pokeRes, speciesRes] = await Promise.all([
      fetch(`https://pokeapi.co/api/v2/pokemon/${identifier}`, {
        next: { revalidate: 86400 },
      }),
      fetch(`https://pokeapi.co/api/v2/pokemon-species/${identifier}`, {
        next: { revalidate: 86400 },
      }),
    ]);

    if (!pokeRes.ok) {
      console.error(
        `[PokeAPI] Failed to fetch pokemon/${identifier}: HTTP ${pokeRes.status} ${pokeRes.statusText}`
      );
      if (baseEntry) {
        return createFallbackDetail(baseEntry);
      }
      return null;
    }

    const pokeData = await pokeRes.json();
    let speciesData: any = null;
    if (speciesRes.ok) {
      try {
        speciesData = await speciesRes.json();
      } catch (err) {
        console.error(
          `[PokeAPI] Error parsing species/${identifier} JSON: ${err instanceof Error ? err.message : String(err)}`
        );
      }
    }

    const stats: PokemonStat[] = (pokeData.stats || []).map((s: any) => ({
      name: s.stat.name,
      baseStat: s.base_stat,
      effort: s.effort,
    }));
    const baseStatTotal = stats.reduce((acc, s) => acc + s.baseStat, 0);

    const types: PokemonType[] = (pokeData.types || []).map(
      (t: any) => t.type.name as PokemonType
    );

    const abilities: string[] = (pokeData.abilities || [])
      .map((a: any) => a.ability.name.replace("-", " ").replace(/\b\w/g, (c: string) => c.toUpperCase()));

    let genus = "Pokémon";
    let flavorText = "A mysterious Pokémon awaiting your collection.";
    if (speciesData) {
      const enGenus = (speciesData.genera || []).find((g: any) => g.language.name === "en");
      if (enGenus?.genus) {
        genus = enGenus.genus;
      }
      const enFlavors = (speciesData.flavor_text_entries || []).filter(
        (f: any) => f.language.name === "en"
      );
      if (enFlavors.length > 0) {
        flavorText = enFlavors[enFlavors.length - 1].flavor_text
          .replace(/[\n\f]/g, " ")
          .replace(/\s+/g, " ")
          .trim();
      }
    }

    const artwork =
      pokeData.sprites?.other?.["official-artwork"]?.front_default ||
      `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/${pokeData.id}.png`;

    const cryUrl =
      pokeData.cries?.latest ||
      `https://raw.githubusercontent.com/PokeAPI/cries/main/cries/pokemon/latest/${pokeData.id}.ogg`;

    const enSpeciesName = (speciesData?.names || []).find((n: any) => n.language?.name === "en")?.name;

    return {
      id: pokeData.id,
      name: baseEntry?.name || enSpeciesName || pokeData.name.replace("-", " ").replace(/\b\w/g, (c: string) => c.toUpperCase()),
      slug: pokeData.name,
      types: types.length > 0 ? types : (baseEntry?.types || ["normal"]),
      height: (pokeData.height || 0) / 10, // decimeters to meters
      weight: (pokeData.weight || 0) / 10, // hectograms to kg
      genus,
      flavorText,
      stats,
      baseStatTotal,
      abilities,
      cryUrl,
      artwork,
    };
  } catch (error) {
    console.error(
      `[PokeAPI] Exception fetching details for ${identifier}: ${error instanceof Error ? error.stack || error.message : String(error)}`
    );
    if (baseEntry) {
      return createFallbackDetail(baseEntry);
    }
    return null;
  }
}

function createFallbackDetail(entry: NonNullable<ReturnType<typeof getPokemonByIdOrSlug>>): PokemonDetail {
  return {
    id: entry.id,
    name: entry.name,
    slug: entry.slug,
    types: entry.types,
    height: 1.0,
    weight: 25.0,
    genus: "Pokémon",
    flavorText: `${entry.name} is a Pokémon from the ${entry.region} region.`,
    stats: [
      { name: "hp", baseStat: 70, effort: 0 },
      { name: "attack", baseStat: 75, effort: 0 },
      { name: "defense", baseStat: 70, effort: 0 },
      { name: "special-attack", baseStat: 75, effort: 0 },
      { name: "special-defense", baseStat: 70, effort: 0 },
      { name: "speed", baseStat: 70, effort: 0 },
    ],
    baseStatTotal: 430,
    abilities: [],
    cryUrl: `https://raw.githubusercontent.com/PokeAPI/cries/main/cries/pokemon/latest/${entry.id}.ogg`,
    artwork: entry.artwork,
  };
}
