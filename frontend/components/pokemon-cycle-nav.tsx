"use client";

import { useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { formatDexNumber } from "@/lib/pokeapi";
import type { PokedexEntry } from "@/types/pokemon";

type ArrowDirection = "prev" | "next";

type PokemonArrowButtonProps = {
  direction: ArrowDirection;
  pokemon: PokedexEntry;
};

export function PokemonArrowButton({ direction, pokemon }: PokemonArrowButtonProps) {
  const isPrev = direction === "prev";
  const label = isPrev ? "Previous Pokémon" : "Next Pokémon";

  return (
    <div className="relative group">
      <Link
        href={`/pokemon/${pokemon.id}`}
        prefetch={true}
        aria-label={`${label}: ${pokemon.name} (${formatDexNumber(pokemon.id)})`}
        className={`flex h-11 w-11 sm:h-12 sm:w-12 items-center justify-center rounded-2xl border border-slate-200/90 bg-white/90 text-slate-700 shadow-sm backdrop-blur-xs transition-all duration-200 hover:border-emerald-400 hover:bg-white hover:text-emerald-800 hover:shadow-md hover:scale-105 active:scale-95 focus:outline-none focus:ring-2 focus:ring-emerald-500`}
      >
        {isPrev ? (
          <svg
            className="h-5 w-5 transition-transform duration-200 group-hover:-translate-x-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M15 19l-7-7 7-7" />
          </svg>
        ) : (
          <svg
            className="h-5 w-5 transition-transform duration-200 group-hover:translate-x-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M9 5l7 7-7 7" />
          </svg>
        )}
      </Link>

      {/* Rich Hover Preview Tooltip */}
      <div
        className={`pointer-events-none absolute bottom-full mb-3 z-30 hidden group-hover:flex items-center gap-2.5 rounded-xl border border-slate-800/90 bg-slate-950/95 px-3 py-2 text-white shadow-xl backdrop-blur-md transition-all duration-200 ${
          isPrev ? "left-0 sm:left-1/2 sm:-translate-x-1/2" : "right-0 sm:left-1/2 sm:-translate-x-1/2"
        }`}
      >
        <div className="relative h-8 w-8 flex-shrink-0">
          <Image
            src={pokemon.sprite || pokemon.artwork}
            alt={pokemon.name}
            fill
            sizes="32px"
            className="object-contain"
          />
        </div>
        <div className="whitespace-nowrap text-left">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] text-slate-400">{formatDexNumber(pokemon.id)}</span>
            <span className="text-[11px] font-bold text-white">{pokemon.name}</span>
          </div>
          <p className="text-[9px] font-mono uppercase tracking-wider text-emerald-400">
            {isPrev ? "← Prev (Left Arrow)" : "Next (Right Arrow) →"}
          </p>
        </div>
      </div>
    </div>
  );
}

type PokemonCycleHeaderProps = {
  currentPokemon: {
    id: number;
    name: string;
    region: string;
  };
  prevPokemon: PokedexEntry;
  nextPokemon: PokedexEntry;
};

export function PokemonCycleHeader({
  currentPokemon,
  prevPokemon,
  nextPokemon,
}: PokemonCycleHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      {/* Previous Pokemon Link */}
      <Link
        href={`/pokemon/${prevPokemon.id}`}
        prefetch={true}
        className="group inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        title={`Previous: ${prevPokemon.name} (${formatDexNumber(prevPokemon.id)})`}
      >
        <svg
          className="h-3.5 w-3.5 transition-transform duration-200 group-hover:-translate-x-0.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M15 19l-7-7 7-7" />
        </svg>
        <span className="font-mono text-slate-400">{formatDexNumber(prevPokemon.id)}</span>
        <span className="hidden sm:inline">{prevPokemon.name}</span>
      </Link>

      {/* Center: Back to Pokédex & Current Dex Info */}
      <div className="flex items-center gap-2.5">
        <Link
          href="/pokedex"
          onClick={() => {
            try {
              sessionStorage.setItem("cardboarddex_pokedex_return_from_profile", "true");
            } catch {}
          }}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
          <span>Pokédex</span>
        </Link>
        <div className="hidden sm:flex items-center gap-1.5 text-xs font-mono text-slate-400">
          <span>·</span>
          <span className="font-bold text-slate-700">{formatDexNumber(currentPokemon.id)}</span>
          <span>·</span>
          <span className="text-slate-500">{currentPokemon.region} Region</span>
        </div>
      </div>

      {/* Next Pokemon Link */}
      <Link
        href={`/pokemon/${nextPokemon.id}`}
        prefetch={true}
        className="group inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-2xs transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        title={`Next: ${nextPokemon.name} (${formatDexNumber(nextPokemon.id)})`}
      >
        <span className="hidden sm:inline">{nextPokemon.name}</span>
        <span className="font-mono text-slate-400">{formatDexNumber(nextPokemon.id)}</span>
        <svg
          className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M9 5l7 7-7 7" />
        </svg>
      </Link>
    </div>
  );
}

export function PokemonKeyboardCycle({
  prevId,
  nextId,
}: {
  prevId: number;
  nextId: number;
}) {
  const router = useRouter();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when user is typing in inputs or selects
      const activeElement = document.activeElement;
      if (
        activeElement &&
        (activeElement.tagName === "INPUT" ||
          activeElement.tagName === "TEXTAREA" ||
          activeElement.tagName === "SELECT" ||
          (activeElement as HTMLElement).isContentEditable)
      ) {
        return;
      }

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        router.push(`/pokemon/${prevId}`);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        router.push(`/pokemon/${nextId}`);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [prevId, nextId, router]);

  return null;
}
