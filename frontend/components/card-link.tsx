"use client";

import Link from "next/link";
import { useState, type ComponentProps } from "react";

/**
 * Link to a card page that prefetches only on intent (hover, focus or touch). Grids show
 * dozens of cards, and viewport prefetching would run an edge render per tile.
 * Pattern from the Next.js prefetching guide ("Hover-triggered prefetch").
 */
export function CardLink({ onMouseEnter, onFocus, onTouchStart, ...props }: Omit<ComponentProps<typeof Link>, "prefetch">) {
  const [active, setActive] = useState(false);
  return <Link {...props} prefetch={active ? null : false}
    onMouseEnter={(event) => { setActive(true); onMouseEnter?.(event); }}
    onFocus={(event) => { setActive(true); onFocus?.(event); }}
    onTouchStart={(event) => { setActive(true); onTouchStart?.(event); }} />;
}
