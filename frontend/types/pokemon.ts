import type { CardSummary } from "./card";

export type PokemonType =
  | "normal"
  | "fire"
  | "water"
  | "grass"
  | "electric"
  | "ice"
  | "fighting"
  | "poison"
  | "ground"
  | "flying"
  | "psychic"
  | "bug"
  | "rock"
  | "ghost"
  | "dragon"
  | "steel"
  | "dark"
  | "fairy";

export type PokedexEntry = {
  id: number;
  name: string;
  slug: string;
  types: PokemonType[];
  generation: number;
  region: string;
  artwork: string;
  sprite: string;
};

export type PokemonStat = {
  name: string;
  baseStat: number;
  effort: number;
};

export type PokemonDetail = {
  id: number;
  name: string;
  slug: string;
  types: PokemonType[];
  height: number; // in meters
  weight: number; // in kg
  genus: string;
  flavorText: string;
  stats: PokemonStat[];
  baseStatTotal: number;
  abilities: string[];
  cryUrl: string | null;
  artwork: string;
};

export type PokemonSetCount = {
  id: string;
  name: string;
  count: number;
};

export type PokemonCardsResponse = {
  pokemon_name: string;
  total_cards: number;
  highest_price: number | null;
  lowest_price: number | null;
  available_sets: PokemonSetCount[];
  cards: CardSummary[];
};
