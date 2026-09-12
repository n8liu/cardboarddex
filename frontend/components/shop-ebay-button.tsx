import type { CardDetail } from "@/types/card";

export type EbaySearchCardTarget = {
  name: string;
  number?: string | null;
  printed_total?: number | null;
  set_name?: string | null;
};

/**
 * Builds an optimized, high-intent eBay search URL for single cards or sealed products.
 */
export function buildEbaySearchUrl(card: EbaySearchCardTarget): string {
  const parts: string[] = [];

  // Check if "Pokemon" / "Pokémon" is already present in card name or set name
  const hasPokemon =
    /pok[eé]mon/i.test(card.name) ||
    (card.set_name ? /pok[eé]mon/i.test(card.set_name) : false);

  if (!hasPokemon) {
    parts.push("Pokemon");
  }

  // Card or sealed product name
  if (card.name) {
    parts.push(card.name);
  }

  // Card number (omit dummy markers like '#' or 'N/A' often found on sealed products)
  if (card.number) {
    const cleanNum = card.number.trim();
    if (cleanNum && cleanNum !== "#" && !/^n\/?a$/i.test(cleanNum)) {
      if (card.printed_total) {
        parts.push(`${cleanNum}/${card.printed_total}`);
      } else {
        parts.push(cleanNum);
      }
    }
  }

  // Set name (avoid duplicating if already part of card or product name)
  if (card.set_name && !card.name.toLowerCase().includes(card.set_name.toLowerCase())) {
    parts.push(card.set_name);
  }

  const query = parts.join(" ").replace(/\s+/g, " ").trim();
  return `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(query)}`;
}

/**
 * Renders the iconic 4-color eBay vector logo.
 */
export function EbayLogo({ className = "h-4 w-auto" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 54 22"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <text
        x="0"
        y="17"
        fontFamily="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        fontWeight="800"
        fontSize="21"
        letterSpacing="-1.2px"
      >
        <tspan fill="#E53238">e</tspan>
        <tspan fill="#0064D2">b</tspan>
        <tspan fill="#F5AF02">a</tspan>
        <tspan fill="#86B817">y</tspan>
      </text>
    </svg>
  );
}

type ShopOnEbayButtonProps = {
  card: EbaySearchCardTarget;
  variant?: "hero" | "compact";
  className?: string;
};

export function ShopOnEbayButton({
  card,
  variant = "hero",
  className = "",
}: ShopOnEbayButtonProps) {
  const url = buildEbaySearchUrl(card);

  if (variant === "compact") {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={`group inline-flex items-center gap-1.5 rounded-lg border border-black bg-white px-2.5 py-1.5 font-mono text-xs font-bold text-slate-950 shadow-2xs transition hover:bg-slate-50 active:scale-95 ${className}`}
        title={`Search live listings for ${card.name} on eBay`}
      >
        <EbayLogo className="h-3.5 w-auto" />
        <span>Shop on eBay</span>
        <span className="text-[11px] text-slate-400 transition-transform duration-150 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-black">
          ↗
        </span>
      </a>
    );
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`group inline-flex items-center gap-2.5 rounded-xl border border-black bg-white px-4 py-2.5 font-mono text-xs font-bold text-slate-950 shadow-xs transition-all duration-150 hover:bg-slate-50 hover:shadow-sm active:scale-95 sm:px-5 sm:py-3 sm:text-sm ${className}`}
      title={`Search live listings for ${card.name} on eBay`}
    >
      <EbayLogo className="h-4 w-auto" />
      <span>Shop on eBay</span>
      <svg
        className="h-3.5 w-3.5 text-slate-400 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-black sm:h-4 sm:w-4"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2.5}
          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
        />
      </svg>
    </a>
  );
}
