"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavHeader() {
  const pathname = usePathname();
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const isPokedex = pathname.startsWith("/pokedex") || pathname.startsWith("/pokemon");
  const isCatalog =
    pathname.startsWith("/catalog") ||
    (pathname.startsWith("/cards") && !pathname.startsWith("/cards/"));
  const isMovers = pathname.startsWith("/market-movers");
  const isLiveUpdates = pathname.startsWith("/live-updates");
  const isTopVolume = pathname.startsWith("/top-volume");
  const isGrading = pathname.startsWith("/grading-profit");
  const isSealed = pathname.startsWith("/sealed-signals");

  const navLinks = [
    { href: "/pokedex", label: "Pokédex", active: isPokedex },
    { href: "/catalog", label: "Catalog", active: isCatalog },
    { href: "/market-movers", label: "Movers", active: isMovers },
    { href: "/sealed-signals", label: "Sealed", active: isSealed },
    { href: "/grading-profit", label: "Grading", active: isGrading },
    { href: "/top-volume", label: "Trending", active: isTopVolume },
    { href: "/live-updates", label: "Live Comps", active: isLiveUpdates },
  ];

  const handleNavClick = (linkHref: string) => {
    try {
      sessionStorage.removeItem("cardboarddex_pokedex_last_viewed");
      sessionStorage.removeItem("cardboarddex_pokedex_scroll");
      sessionStorage.removeItem("cardboarddex_pokedex_in_profile");
      sessionStorage.removeItem("cardboarddex_pokedex_return_from_profile");
      sessionStorage.setItem("cardboarddex_pokedex_nav_reset", "true");
    } catch {}
    if (linkHref === "/pokedex") {
      if (typeof window !== "undefined") {
        window.scrollTo({ top: 0, behavior: pathname === "/pokedex" ? "smooth" : "instant" });
      }
    }
  };

  return (
    <header
      className={`sticky top-0 z-40 transition-all duration-200 border-b ${
        isScrolled
          ? "border-slate-200 bg-white/92 shadow-2xs backdrop-blur-md"
          : "border-slate-200/80 bg-white"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Left: Logo */}
        <div className="flex shrink-0 items-center">
          <Link
            className="flex items-center gap-2.5 text-sm font-bold tracking-tight text-slate-950 transition hover:opacity-90"
            href="/"
            onClick={() => handleNavClick("/")}
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 font-mono text-[11px] font-black text-white shadow-xs tracking-tighter">
              CD
            </span>
            <span className="font-mono tracking-tight font-bold">CardboardDex</span>
          </Link>
        </div>

        {/* Center: Navigation Bar (Centered, no emojis, renamed, IBM Plex Mono theme) */}
        <nav
          className="hidden md:flex items-center gap-1 rounded-xl bg-slate-100/90 p-1 text-xs font-mono"
          aria-label="Main Navigation"
        >
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => handleNavClick(link.href)}
              className={`rounded-lg px-3 py-1.5 transition uppercase tracking-wider font-semibold ${
                link.active
                  ? "bg-slate-900 text-white shadow-xs font-bold"
                  : "text-slate-600 hover:text-slate-950 hover:bg-slate-200/60"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Right: Live Market Tag */}
        <div className="flex shrink-0 items-center gap-3">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-mono text-slate-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            TCG & eBay Comps
          </span>
        </div>
      </div>

      {/* Mobile Navigation Row (Centered on small screens) */}
      <div className="flex md:hidden overflow-x-auto border-t border-slate-200/60 bg-slate-50/90 backdrop-blur-md p-2 scrollbar-none justify-start sm:justify-center">
        <nav className="flex items-center gap-1 text-xs font-mono" aria-label="Mobile Navigation">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => handleNavClick(link.href)}
              className={`rounded-lg px-2.5 py-1 text-[11px] whitespace-nowrap transition uppercase tracking-wider font-semibold ${
                link.active
                  ? "bg-slate-900 text-white font-bold"
                  : "text-slate-600 hover:text-slate-950"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
