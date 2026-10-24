"use client";

import Image from "@/components/card-image";
import { usePathname, useRouter } from "next/navigation";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useBinder } from "@/context/binder-context";
import { SUPPORTED_CURRENCIES, SupportedCurrency, useCurrency } from "@/context/currency-context";
import { cardImageUrl, getCardSets, searchCards } from "@/lib/api";
import { POKEDEX_DATA } from "@/lib/pokedex-data";
import { shimmerBlurDataUrl } from "@/lib/shimmer";
import type { CardSetOption, CardSummary } from "@/types/card";

export function openCommandPalette() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  }
}

interface PaletteActionItem {
  id: string;
  category: "Navigation" | "Binder" | "Sets" | "Pokémon" | "Cards" | "Currency";
  title: string;
  subtitle?: string;
  badge?: string;
  image?: string | null;
  onSelect: () => void;
}

export function CommandPalette() {
  const router = useRouter();
  const pathname = usePathname();
  const { currency, setCurrency, formatPrice } = useCurrency();
  const { quickAddCard, isCardInBinder, isHydrated: binderReady } = useBinder();
  const [sets, setSets] = useState<CardSetOption[] | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [cardResults, setCardResults] = useState<CardSummary[]>([]);
  const [isSearchingCards, setIsSearchingCards] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  // Listen for global shortcut Cmd+K / Ctrl+K and custom event
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsOpen(false);
      }
    };

    const handleOpenEvent = () => setIsOpen(true);

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("open-command-palette", handleOpenEvent);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("open-command-palette", handleOpenEvent);
    };
  }, []);

  // Handle modal open/close transitions and focus
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      setTimeout(() => inputRef.current?.focus(), 50);
      setSelectedIndex(0);
    } else {
      document.body.style.overflow = "";
      setSearch("");
      setCardResults([]);
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // Sets load once, the first time the palette opens (24h cached by getCardSets).
  useEffect(() => {
    if (!isOpen || sets !== null) return;
    let cancelled = false;
    getCardSets("all").then((result) => { if (!cancelled) setSets(result); }).catch((err) => {
      console.error("[CommandPalette] Failed loading sets:", err);
      if (!cancelled) setSets([]);
    });
    return () => { cancelled = true; };
  }, [isOpen, sets]);

  // Debounce search cards via API
  useEffect(() => {
    const query = search.trim();
    if (!query || query.length < 2) {
      setCardResults([]);
      setIsSearchingCards(false);
      return;
    }

    let isCancelled = false;
    setIsSearchingCards(true);

    const timer = setTimeout(async () => {
      try {
        const cards = await searchCards(query, { limit: 5 });
        if (!isCancelled) {
          setCardResults(cards);
        }
      } catch {
        if (!isCancelled) setCardResults([]);
      } finally {
        if (!isCancelled) setIsSearchingCards(false);
      }
    }, 180);

    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [search]);

  const closeAndNavigate = useCallback(
    (url: string) => {
      setIsOpen(false);
      router.push(url);
    },
    [router]
  );

  // Compute all actionable items matching current query
  const items = useMemo<PaletteActionItem[]>(() => {
    const q = search.toLowerCase().trim();
    const result: PaletteActionItem[] = [];

    // 1. Navigation Pages
    const pages = [
      { name: "Pokédex", path: "/pokedex", desc: "Browse all Pokémon species & dex numbers" },
      { name: "Card Catalog", path: "/catalog", desc: "Browse all sets, cards, and singles" },
      { name: "Market Movers", path: "/market-movers", desc: "24h, 7d, 30d momentum gainers & drops" },
      { name: "Sealed Signals", path: "/sealed-signals", desc: "Sealed booster boxes, ETBs & packs" },
      { name: "Grading Profit", path: "/grading-profit", desc: "PSA 10 vs Raw grading arbitrage" },
      { name: "Trending Top 50", path: "/top-volume", desc: "Highest volume cards and search radar" },
      { name: "Live Comps", path: "/live-updates", desc: "Real-time stream of verified sold comps" },
      { name: "Compare Cards", path: "/compare", desc: "Up to four cards' price history on one chart" },
      { name: "Release Calendar", path: "/faq#calendar", desc: "Set release dates, retailer drops, and print status" },
      { name: "FAQ & Guides", path: "/faq", desc: "Collecting help, website questions, and Pokémon TCG history" },
    ];

    pages.forEach((page) => {
      if (!q || page.name.toLowerCase().includes(q) || page.desc.toLowerCase().includes(q)) {
        result.push({
          id: `nav-${page.path}`,
          category: "Navigation",
          title: page.name,
          subtitle: page.desc,
          badge: "Page",
          onSelect: () => closeAndNavigate(page.path),
        });
      }
    });

    // 2. Binder actions
    const currentCardId = pathname?.startsWith("/cards/") ? decodeURIComponent(pathname.slice("/cards/".length).split("/")[0]) : null;
    const binderActions: PaletteActionItem[] = [{
      id: "binder-open", category: "Binder", title: "Open my binder", subtitle: "Your collection and its value", badge: "Page",
      onSelect: () => closeAndNavigate("/binder"),
    }];
    if (currentCardId && binderReady) {
      const owned = isCardInBinder(currentCardId);
      binderActions.unshift({
        id: "binder-add-current", category: "Binder",
        title: owned ? "This card is in your binder" : "Add this card to my binder",
        subtitle: owned ? "Open the binder to see it" : "Places it in the first empty slot",
        badge: owned ? "Owned" : "Add",
        onSelect: () => {
          if (owned) closeAndNavigate("/binder");
          else { quickAddCard(currentCardId); setIsOpen(false); }
        },
      });
    }
    binderActions.forEach((action) => {
      if (!q || `${action.title} binder collection`.toLowerCase().includes(q)) result.push(action);
    });

    // 3. Currencies
    SUPPORTED_CURRENCIES.forEach((curr) => {
      if (
        !q ||
        curr.code.toLowerCase().includes(q) ||
        curr.label.toLowerCase().includes(q) ||
        curr.symbol.includes(q) ||
        "currency".includes(q)
      ) {
        result.push({
          id: `curr-${curr.code}`,
          category: "Currency",
          title: `Switch Currency to ${curr.label}`,
          subtitle: curr.code === currency ? "Currently Active" : undefined,
          badge: curr.code === currency ? "Active" : "Switch",
          onSelect: () => {
            setCurrency(curr.code as SupportedCurrency);
            setIsOpen(false);
          },
        });
      }
    });

    // 4. Sets
    if (q && sets) {
      sets.filter((set) => set.name.toLowerCase().includes(q) || (set.series ?? "").toLowerCase().includes(q) || set.id.toLowerCase() === q)
        .slice(0, 5)
        .forEach((set) => {
          const japanese = set.series === "Pokemon Japan";
          result.push({
            id: `set-${set.id}`,
            category: "Sets",
            title: set.name,
            subtitle: [set.series, set.release_date?.slice(0, 4)].filter(Boolean).join(" · "),
            badge: japanese ? "Japan" : "Set",
            image: set.image_url || null,
            onSelect: () => closeAndNavigate(`/catalog?set=${encodeURIComponent(set.id)}${japanese ? "&game=pokemon-japan" : ""}`),
          });
        });
    }

    // 5. Pokémon Species
    if (q) {
      const matchedPokemon = POKEDEX_DATA.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.slug.toLowerCase().includes(q) ||
          p.id.toString() === q
      ).slice(0, 4);

      matchedPokemon.forEach((pokemon) => {
        result.push({
          id: `poke-${pokemon.id}`,
          category: "Pokémon",
          title: pokemon.name,
          subtitle: `#${pokemon.id.toString().padStart(3, "0")} · Generation ${pokemon.generation}`,
          badge: pokemon.types.join(" / "),
          image: pokemon.artwork || pokemon.sprite,
          onSelect: () => closeAndNavigate(`/pokemon/${pokemon.id}`),
        });
      });
    }

    // 6. Cards from Live Search
    cardResults.forEach((card) => {
      result.push({
        id: `card-${card.id}`,
        category: "Cards",
        title: card.name,
        subtitle: `${card.set_name} · ${card.rarity || "Standard"} · #${card.number}`,
        badge: formatPrice(card.market_price, { showPending: true }),
        image: card.image_url ? cardImageUrl(card.image_url) : null,
        onSelect: () => closeAndNavigate(`/cards/${encodeURIComponent(card.id)}`),
      });
    });

    return result;
  }, [search, cardResults, currency, setCurrency, formatPrice, closeAndNavigate, pathname, binderReady, isCardInBinder, quickAddCard, sets]);

  // Adjust selected index if it exceeds list length
  useEffect(() => {
    if (selectedIndex >= items.length) {
      setSelectedIndex(Math.max(0, items.length - 1));
    }
  }, [items.length, selectedIndex]);

  // Keyboard navigation inside list
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < items.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : items.length - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (items[selectedIndex]) {
        items[selectedIndex].onSelect();
      }
    }
  };

  // Scroll active item into view
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const activeEl = list.querySelector(`[data-index="${selectedIndex}"]`) as HTMLElement;
    if (activeEl) {
      activeEl.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  if (!isOpen) return null;

  return (
    <div
      aria-modal="true"
      role="dialog"
      aria-label="Command Palette"
      className="fixed inset-0 z-50 flex items-start justify-center p-3 pt-[10vh] sm:p-4 sm:pt-[14vh] bg-slate-950/40 backdrop-blur-xs transition-opacity animate-in fade-in duration-150"
      onClick={() => setIsOpen(false)}
    >
      <div
        className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-2xl font-mono text-slate-900 transition-all transform animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Header Bar */}
        <div className="relative flex items-center border-b border-slate-100 px-4 py-3.5">
          <span className="mr-3 text-slate-400 text-lg">⌕</span>
          <input
            ref={inputRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-results"
            aria-activedescendant={items[selectedIndex] ? `palette-option-${selectedIndex}` : undefined}
            aria-label="Search cards, sets, Pokémon and pages"
            placeholder="Search cards, sets, Pokémon, pages (e.g. Charizard, Surging Sparks)..."
            className="w-full bg-transparent text-sm font-medium text-slate-900 placeholder:text-slate-400 focus:outline-none"
          />
          {isSearchingCards && (
            <span className="mr-2 text-xs text-slate-400 animate-pulse">Searching…</span>
          )}
          <kbd className="hidden sm:inline-flex items-center rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
            ESC
          </kbd>
        </div>

        {/* Scrollable Results List */}
        <div ref={listRef} id="command-palette-results" role="listbox" aria-label="Results" className="max-h-[58vh] overflow-y-auto p-2 space-y-1">
          {items.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">
              No matching pages, sets, Pokémon, or cards found.
            </div>
          ) : (
            items.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={item.id}
                  id={`palette-option-${idx}`}
                  role="option"
                  aria-selected={isSelected}
                  data-index={idx}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  onClick={item.onSelect}
                  className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2.5 transition text-xs ${
                    isSelected
                      ? "bg-slate-900 text-white"
                      : "text-slate-800 hover:bg-slate-100/70"
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {/* Thumbnail Image or Icon */}
                    {item.image ? (
                      <div className="relative h-9 w-9 shrink-0 overflow-hidden rounded-lg border border-slate-200/60 bg-slate-50">
                        <Image
                          src={item.image}
                          alt={item.title}
                          fill
                          className="object-contain p-0.5"
                          placeholder="blur"
                          blurDataURL={shimmerBlurDataUrl(36, 36)}
                          sizes="36px"
                        />
                      </div>
                    ) : (
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
                          isSelected
                            ? "bg-slate-800 text-slate-200"
                            : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {item.category === "Navigation"
                          ? "↗"
                          : item.category === "Binder"
                          ? "▣"
                          : item.category === "Sets"
                          ? "◫"
                          : item.category === "Currency"
                          ? "¤"
                          : "★"}
                      </span>
                    )}

                    <div className="min-w-0">
                      <div className="flex items-center gap-2 truncate">
                        <span className="font-bold truncate">{item.title}</span>
                        <span
                          className={`text-[10px] px-1.5 py-0.2 rounded font-semibold uppercase tracking-wider ${
                            isSelected
                              ? "bg-slate-800 text-slate-300"
                              : "bg-slate-100 text-slate-400"
                          }`}
                        >
                          {item.category}
                        </span>
                      </div>
                      {item.subtitle && (
                        <p
                          className={`truncate text-[11px] mt-0.5 ${
                            isSelected ? "text-slate-300" : "text-slate-500"
                          }`}
                        >
                          {item.subtitle}
                        </p>
                      )}
                    </div>
                  </div>

                  {item.badge && (
                    <span
                      className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-bold ${
                        isSelected
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-400/30"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer Navigation Hints */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-2 text-[10px] text-slate-400">
          <div className="flex items-center gap-3">
            <span>
              <kbd className="font-bold">↑</kbd> <kbd className="font-bold">↓</kbd> navigate
            </span>
            <span>
              <kbd className="font-bold">↵</kbd> select
            </span>
            <span>
              <kbd className="font-bold">esc</kbd> close
            </span>
          </div>
          <span className="hidden sm:inline">CardboardDex Spotlight</span>
        </div>
      </div>
    </div>
  );
}
