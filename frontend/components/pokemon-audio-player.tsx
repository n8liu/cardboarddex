"use client";

import { useRef, useState } from "react";

export function PokemonAudioPlayer({
  cryUrl,
  pokemonName,
}: {
  cryUrl: string | null;
  pokemonName: string;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  if (!cryUrl) return null;

  const playCry = () => {
    if (!audioRef.current) return;
    try {
      if (isPlaying) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
        setIsPlaying(false);
      } else {
        audioRef.current.currentTime = 0;
        audioRef.current.play();
        setIsPlaying(true);
      }
    } catch (err) {
      console.error("[AudioPlayer] Error playing cry:", err);
      setIsPlaying(false);
    }
  };

  return (
    <div className="inline-flex items-center">
      <audio
        ref={audioRef}
        src={cryUrl}
        preload="none"
        onEnded={() => setIsPlaying(false)}
        onError={() => setIsPlaying(false)}
      />
      <button
        type="button"
        onClick={playCry}
        title={`Play ${pokemonName}'s official cry`}
        className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-bold transition shadow-xs ${
          isPlaying
            ? "border-emerald-500 bg-emerald-50 text-emerald-800 ring-2 ring-emerald-400/30"
            : "border-slate-200 bg-white text-slate-700 hover:border-emerald-300 hover:bg-slate-50 hover:text-emerald-700"
        }`}
      >
        <span className="flex items-center">
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.757 3.63 8.25 4.51 8.25H6.75z" />
          </svg>
        </span>
        <span>{isPlaying ? "Playing Cry..." : "Play Cry"}</span>

        {isPlaying && (
          <span className="flex items-center gap-0.5 h-3 ml-0.5">
            <span className="w-0.5 h-full bg-emerald-600 animate-pulse rounded-full" />
            <span className="w-0.5 h-2/3 bg-emerald-600 animate-pulse delay-75 rounded-full" />
            <span className="w-0.5 h-full bg-emerald-600 animate-pulse delay-150 rounded-full" />
          </span>
        )}
      </button>
    </div>
  );
}
