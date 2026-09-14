"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { openCommandPalette } from "@/components/command-palette";
import { useBinder } from "@/context/binder-context";
import { SUPPORTED_CURRENCIES, useCurrency } from "@/context/currency-context";

export function NavHeader() {
  const pathname = usePathname();
  const [isScrolled, setIsScrolled] = useState(false);
  const { currency, setCurrency } = useCurrency();
  const { totalCardCount, isHydrated } = useBinder();

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
  const isBinder = pathname.startsWith("/binder");

  const navLinks = useMemo(
    () => [
      { href: "/pokedex", label: "Pokédex", active: isPokedex },
      { href: "/catalog", label: "Catalog", active: isCatalog },
      { href: "/market-movers", label: "Movers", active: isMovers },
      { href: "/sealed-signals", label: "Sealed", active: isSealed },
      { href: "/grading-profit", label: "Grading", active: isGrading },
      { href: "/top-volume", label: "Trending", active: isTopVolume },
      { href: "/live-updates", label: "Live Comps", active: isLiveUpdates },
    ],
    [isPokedex, isCatalog, isMovers, isSealed, isGrading, isTopVolume, isLiveUpdates]
  );

  const activeLink = navLinks.find((l) => l.active) || null;
  const [clickedHref, setClickedHref] = useState<string | null>(null);

  // Active target is the clicked item or the current route's link
  const currentTargetHref = clickedHref || activeLink?.href || null;

  useEffect(() => {
    setClickedHref(null);
  }, [pathname]);

  // Desktop slider measurements
  const desktopNavRef = useRef<HTMLElement | null>(null);
  const desktopLinkRefs = useRef<Map<string, HTMLAnchorElement>>(new Map());
  const [desktopPill, setDesktopPill] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
    opacity: number;
  }>({
    left: 0,
    top: 0,
    width: 0,
    height: 0,
    opacity: 0,
  });

  // Mobile slider measurements
  const mobileNavRef = useRef<HTMLElement | null>(null);
  const mobileLinkRefs = useRef<Map<string, HTMLAnchorElement>>(new Map());
  const [mobilePill, setMobilePill] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
    opacity: number;
  }>({
    left: 0,
    top: 0,
    width: 0,
    height: 0,
    opacity: 0,
  });

  const updatePills = useCallback(() => {
    if (!currentTargetHref) {
      setDesktopPill((prev) => ({ ...prev, opacity: 0 }));
      setMobilePill((prev) => ({ ...prev, opacity: 0 }));
      return;
    }

    // Update desktop
    const dEl = desktopLinkRefs.current.get(currentTargetHref);
    if (dEl) {
      setDesktopPill({
        left: dEl.offsetLeft,
        top: dEl.offsetTop,
        width: dEl.offsetWidth,
        height: dEl.offsetHeight,
        opacity: 1,
      });
    }

    // Update mobile
    const mEl = mobileLinkRefs.current.get(currentTargetHref);
    if (mEl) {
      setMobilePill({
        left: mEl.offsetLeft,
        top: mEl.offsetTop,
        width: mEl.offsetWidth,
        height: mEl.offsetHeight,
        opacity: 1,
      });
    }
  }, [currentTargetHref]);

  useEffect(() => {
    updatePills();
    if (typeof document !== "undefined" && document.fonts) {
      document.fonts.ready.then(updatePills);
    }
    window.addEventListener("resize", updatePills);
    return () => window.removeEventListener("resize", updatePills);
  }, [updatePills]);

  const handleNavClick = (linkHref: string) => {
    setClickedHref(linkHref);

    // Immediately glide pill to the target link
    const dEl = desktopLinkRefs.current.get(linkHref);
    if (dEl) {
      setDesktopPill({
        left: dEl.offsetLeft,
        top: dEl.offsetTop,
        width: dEl.offsetWidth,
        height: dEl.offsetHeight,
        opacity: 1,
      });
    }

    const mEl = mobileLinkRefs.current.get(linkHref);
    if (mEl) {
      setMobilePill({
        left: mEl.offsetLeft,
        top: mEl.offsetTop,
        width: mEl.offsetWidth,
        height: mEl.offsetHeight,
        opacity: 1,
      });
    }

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
            prefetch={false}
            onClick={() => handleNavClick("/")}
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 font-mono text-[11px] font-black text-white shadow-xs tracking-tighter">
              CD
            </span>
            <span className="font-mono tracking-tight font-bold">CardboardDex</span>
          </Link>
        </div>

        {/* Center: Navigation Bar with Animated Sliding Pill */}
        <nav
          ref={desktopNavRef}
          className="relative hidden md:flex items-center gap-1 rounded-xl bg-slate-100/90 p-1 text-xs font-mono"
          aria-label="Main Navigation"
        >
          {/* Animated Sliding Pill Background */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-0 top-0 rounded-lg bg-slate-900 shadow-xs transition-all duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
            style={{
              transform: `translate3d(${desktopPill.left}px, ${desktopPill.top}px, 0)`,
              width: `${desktopPill.width}px`,
              height: `${desktopPill.height}px`,
              opacity: desktopPill.opacity,
            }}
          />

          {navLinks.map((link) => {
            const isCurrent = link.href === currentTargetHref;
            return (
              <Link
                key={link.href}
                href={link.href}
                ref={(el) => {
                  if (el) desktopLinkRefs.current.set(link.href, el);
                  else desktopLinkRefs.current.delete(link.href);
                }}
                prefetch={false}
                onClick={() => handleNavClick(link.href)}
                className={`relative z-10 inline-flex items-center justify-center rounded-lg px-3 py-1.5 text-center text-xs font-mono uppercase font-bold tracking-normal transition-colors duration-200 ${
                  isCurrent
                    ? "text-white"
                    : "text-slate-600 hover:text-slate-950 hover:bg-slate-200/40"
                }`}
              >
                <span>{link.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Right: Search, Currency Switcher & Portfolio Binder Button */}
        <div className="flex shrink-0 items-center gap-2 sm:gap-2.5">
          {/* Spotlight Search Trigger */}
          <button
            type="button"
            onClick={openCommandPalette}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2 sm:px-2.5 py-1 text-xs font-mono font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-1 focus:ring-slate-900"
            title="Open spotlight search (Cmd+K)"
            aria-label="Open command palette search"
          >
            <span className="text-slate-400">⌕</span>
            <span className="hidden lg:inline text-[11px] text-slate-500">Search</span>
            <kbd className="rounded border border-slate-200 bg-white px-1 py-0.2 text-[10px] font-bold text-slate-400">
              ⌘K
            </kbd>
          </button>

          {/* Currency Switcher */}
          <div className="relative inline-flex items-center rounded-lg border border-slate-200 bg-slate-50 px-1 py-0.5 text-xs font-mono transition hover:border-slate-300">
            <span className="sr-only">Select display currency</span>
            <select
              aria-label="Display currency"
              value={currency}
              onChange={(e) => setCurrency(e.target.value as any)}
              className="cursor-pointer appearance-none bg-transparent pl-1.5 pr-5 py-1 font-mono text-xs font-bold text-slate-800 outline-none hover:text-slate-950 focus:ring-1 focus:ring-emerald-500 rounded"
            >
              {SUPPORTED_CURRENCIES.map((curr) => (
                <option key={curr.code} value={curr.code}>
                  {curr.symbol} {curr.code}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-[9px] text-slate-400">
              ▼
            </span>
          </div>

          {/* Portfolio Binder Button (Replacing "TCG & eBay Comps") */}
          <Link
            href="/binder"
            prefetch={false}
            onClick={() => handleNavClick("/binder")}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 sm:px-3 py-1 text-xs font-mono font-bold transition focus:outline-none focus:ring-1 focus:ring-slate-900 shadow-2xs ${
              isBinder
                ? "border-slate-900 bg-slate-900 text-white shadow-xs"
                : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
            }`}
            title="Open Pokémon Portfolio Binder"
            aria-label="Open portfolio binder"
          >
            <svg
              className="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
              <path d="M6 2v20" strokeDasharray="1 2" />
              <path d="M10 7h7" />
              <path d="M10 12h7" />
              <path d="M10 17h7" />
            </svg>
            <span>Binder</span>
            <span
              className={`inline-flex items-center justify-center rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                isBinder
                  ? "bg-emerald-500 text-white"
                  : totalCardCount > 0
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-100 text-slate-500 border border-slate-200"
              }`}
            >
              {isHydrated ? totalCardCount : "0"}
            </span>
          </Link>
        </div>
      </div>

      {/* Mobile Navigation Row (Centered on small screens) with Animated Sliding Pill */}
      <div className="flex md:hidden overflow-x-auto border-t border-slate-200/60 bg-slate-50/90 backdrop-blur-md p-2 scrollbar-none justify-start sm:justify-center">
        <nav
          ref={mobileNavRef}
          className="relative flex items-center gap-1 text-xs font-mono p-1 rounded-xl bg-slate-100/70"
          aria-label="Mobile Navigation"
        >
          {/* Animated Sliding Pill Background for Mobile */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-0 top-0 rounded-lg bg-slate-900 shadow-xs transition-all duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
            style={{
              transform: `translate3d(${mobilePill.left}px, ${mobilePill.top}px, 0)`,
              width: `${mobilePill.width}px`,
              height: `${mobilePill.height}px`,
              opacity: mobilePill.opacity,
            }}
          />

          {navLinks.map((link) => {
            const isCurrent = link.href === currentTargetHref;
            return (
              <Link
                key={link.href}
                href={link.href}
                ref={(el) => {
                  if (el) mobileLinkRefs.current.set(link.href, el);
                  else mobileLinkRefs.current.delete(link.href);
                }}
                prefetch={false}
                onClick={() => handleNavClick(link.href)}
                className={`relative z-10 inline-flex items-center justify-center rounded-lg px-2.5 py-1 text-[11px] whitespace-nowrap text-center text-xs font-mono uppercase font-bold tracking-normal transition-colors duration-200 ${
                  isCurrent
                    ? "text-white"
                    : "text-slate-600 hover:text-slate-950"
                }`}
              >
                <span>{link.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

