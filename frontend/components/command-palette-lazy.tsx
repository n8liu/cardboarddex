"use client";

import dynamic from "next/dynamic";

export const CommandPalette = dynamic(
  () => import("@/components/command-palette").then((mod) => mod.CommandPalette),
  { ssr: false }
);
