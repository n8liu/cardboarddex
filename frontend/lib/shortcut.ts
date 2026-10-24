"use client";

import { useEffect, useState } from "react";

/** "⌘K" on Apple platforms, "Ctrl K" elsewhere. Starts as "⌘K" so server and first client render match. */
export function usePaletteShortcutLabel(): string {
  const [label, setLabel] = useState("⌘K");
  useEffect(() => {
    const platform = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform
      ?? navigator.platform ?? navigator.userAgent;
    if (!/mac|iphone|ipad|ipod/i.test(platform)) setLabel("Ctrl K");
  }, []);
  return label;
}
