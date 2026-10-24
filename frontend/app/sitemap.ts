import type { MetadataRoute } from "next";
import { getCardSets } from "@/lib/api";
import { guides } from "@/lib/learning-content";
import { POKEDEX_DATA } from "@/lib/pokedex-data";

// Built on request like every other data route on Cloudflare Pages, so a build without
// API access never bakes in a sitemap missing its sets.
export const dynamic = "force-dynamic";
export const runtime = "edge";

const SITE = "https://cardboarddex.app";
const PAGES = ["", "/catalog", "/market-movers", "/top-volume", "/sealed-signals", "/grading-profit",
  "/live-updates", "/pokedex", "/calendar", "/faq"];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    ...PAGES.map((path) => ({ url: `${SITE}${path}`, changeFrequency: "daily" as const, priority: path ? 0.8 : 1 })),
    ...guides.map(({ slug }) => ({ url: `${SITE}/faq/guides/${slug}`, changeFrequency: "monthly" as const, priority: 0.5 })),
    ...POKEDEX_DATA.map(({ id }) => ({ url: `${SITE}/pokemon/${id}`, changeFrequency: "weekly" as const, priority: 0.6 })),
  ];
  try {
    const sets = await getCardSets("all");
    for (const set of sets) {
      const game = set.series === "Pokemon Japan" ? "&game=pokemon-japan" : "";
      entries.push({ url: `${SITE}/catalog?set=${encodeURIComponent(set.id)}${game}`, changeFrequency: "daily", priority: 0.7 });
    }
  } catch (err) {
    console.error("[sitemap] Card sets unavailable; serving pages only:", err);
  }
  return entries;
}
