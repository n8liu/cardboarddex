import type { CardSummary } from "@/types/card";

export const RECENT_KEY = "cardboarddex_recently_viewed_v1";
export const RECENT_EVENT = "cardboarddex:recently-viewed";
const MAX_ITEMS = 12;
const MAX_AGE = 30 * 24 * 60 * 60 * 1000;
export type RecentCard = Pick<CardSummary, "id" | "name" | "set_name" | "image_url"> & { viewed_at: number };

function valid(value: unknown): value is RecentCard {
  if (!value || typeof value !== "object") return false;
  const row = value as RecentCard;
  return typeof row.id === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(row.id)
    && typeof row.name === "string" && row.name.length > 0 && row.name.length <= 255
    && typeof row.set_name === "string" && row.set_name.length <= 255
    && typeof row.image_url === "string" && row.image_url.length <= 2048
    && (/^https?:\/\//.test(row.image_url) || /^\/cards\/[A-Za-z0-9_-]+\/image$/.test(row.image_url))
    && Number.isFinite(row.viewed_at) && row.viewed_at <= Date.now() && row.viewed_at >= Date.now() - MAX_AGE;
}

export function readRecentCards(): RecentCard[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw || raw.length > 50_000) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const ids = new Set<string>();
    return parsed.filter(valid).sort((a, b) => b.viewed_at - a.viewed_at).filter((row) => {
      if (ids.has(row.id)) return false;
      ids.add(row.id); return true;
    }).slice(0, MAX_ITEMS);
  } catch (error) {
    console.warn("Could not read recently viewed cards:", error);
    return [];
  }
}

export function rememberCard(card: Pick<CardSummary, "id" | "name" | "set_name" | "image_url">): void {
  const entry = { id: card.id, name: card.name, set_name: card.set_name, image_url: card.image_url, viewed_at: Date.now() };
  if (!valid(entry)) return;
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify([entry, ...readRecentCards().filter((r) => r.id !== card.id)].slice(0, MAX_ITEMS)));
    window.dispatchEvent(new Event(RECENT_EVENT));
  } catch (error) {
    console.warn("Could not save recently viewed card:", error);
  }
}

export function clearRecentCards(): boolean {
  try {
    window.localStorage.removeItem(RECENT_KEY);
    window.dispatchEvent(new Event(RECENT_EVENT));
    return true;
  } catch (error) {
    console.warn("Could not clear recently viewed cards:", error);
    return false;
  }
}
