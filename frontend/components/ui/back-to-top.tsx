"use client";

import { useEffect, useState } from "react";

export function BackToTop({ threshold = 400 }: { threshold?: number }) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setShow(window.scrollY > threshold);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [threshold]);

  if (!show) return null;

  return (
    <button
      type="button"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      className="fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full border border-slate-200/90 bg-white/95 text-slate-800 shadow-xl backdrop-blur-md transition-all duration-200 hover:scale-110 hover:bg-emerald-600 hover:text-white hover:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
      aria-label="Back to top"
      title="Back to top"
    >
      <span className="text-lg font-bold leading-none select-none">↑</span>
    </button>
  );
}
