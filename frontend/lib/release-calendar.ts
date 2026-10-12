import type { CardSetOption } from "@/types/card";
import { CONTENT_REVIEWED, sources, type Source } from "@/lib/learning-content";
import englishReleases from "@/lib/english-set-releases.json";

export const releaseDateSource: Source = {
  label: "TCGplayer · English set release dates",
  url: "https://www.tcgplayer.com/content/article/Every-Pok%C3%A9mon-TCG-Set-in-Order-Newest-to-Oldest/02f9330b-d44a-48d3-9162-f4ce1909f0f6/",
};
export const RELEASE_SOURCE_UPDATED = "2026-09-28";

export type Retailer = "target" | "walmart" | "pokemon-center";
export type CalendarEvent = {
  id: string; title: string; date: string | null;
  kind: "release" | "drop";
  retailer?: Retailer;
  confidence?: "reported" | "expected" | "reminder";
  language?: "pokemon" | "pokemon-japan";
  // Include a UTC offset. Expected windows must explicitly carry expected confidence.
  startsAt?: string;
  note: string; source: Source; reviewed: string;
};
export const retailers: { id: Retailer; name: string; url: string; note: string }[] = [
  { id: "target", name: "Target", url: "https://www.target.com/c/pokemon-collectibles/-/N-ehy89", note: "Check the product page for the seller and online availability." },
  { id: "walmart", name: "Walmart", url: "https://www.walmart.com/shop/trading-cards/pokemon/new-arrivals", note: "Check sold-by details; marketplace listings can be third-party offers." },
  { id: "pokemon-center", name: "Pokémon Center", url: "https://www.pokemoncenter.com/category/trading-card-game", note: "Support does not provide a future restock schedule." },
];

// Editorial records, not a live stock feed. Do not turn a general launch into a retailer drop.
export const calendarEvents: CalendarEvent[] = [
  { id: "celebration-decks", title: "30th Celebration · Espeon ex & Umbreon ex Battle Decks", date: "2026-10-30", kind: "release", retailer: "pokemon-center", note: "Announced product release, including Pokémon Center. An online checkout time has not been verified.", source: sources.showcase, reviewed: CONTENT_REVIEWED },
  ...retailers.map((retailer): CalendarEvent => ({ id: `${retailer.id}-unannounced`, title: `${retailer.name} · Next online drop`, date: null, kind: "drop", retailer: retailer.id, note: "No exact upcoming Pokémon TCG online drop date verified in this research. Check the retailer for new announcements.", source: retailer.id === "pokemon-center" ? sources.restocks : { label: `${retailer.name} Pokémon listings`, url: retailer.url }, reviewed: CONTENT_REVIEWED })),
];

// These are reported preorder opening dates, not article publication times used as checkout times.
export const pokemonCenterHistory = [
  { set: "Delta Reign", preorder: "2026-09-30", release: "2026-11-06", source: { label: "PokéBeach · Delta Reign preorder report", url: "https://www.pokebeach.com/2026/09/delta-reign-preorders-now-live-on-pokemon-center" } },
  { set: "Pitch Black", preorder: "2026-06-10", release: "2026-07-17", source: { label: "PokéBeach · Pitch Black preorder report", url: "https://www.pokebeach.com/2026/06/pitch-black-preorders-now-live-on-pokemon-center" } },
  { set: "Mega Evolution", preorder: "2025-07-15", release: "2025-09-26", source: { label: "PokéBeach · Mega Evolution preorder report", url: "https://www.pokebeach.com/2025/07/pokemon-center-mega-evolution-preorders-now-up" } },
  { set: "Destined Rivals", preorder: "2025-03-24", release: "2025-05-30", source: { label: "Dexerto · Destined Rivals preorder report", url: "https://www.dexerto.com/pokemon/pokemon-destined-rivals-has-already-sold-out-but-theres-good-news-for-team-rocket-fans-3169054/" } },
  { set: "Prismatic Evolutions", preorder: "2024-11-01", release: "2025-01-17", source: { label: "PokéBeach · Prismatic Evolutions announcement", url: "https://www.pokebeach.com/2024/11/prismatic-evolution-special-set-officially-revealed-for-january" } },
];

export function preorderLeadDays(preorder: string, release: string): number {
  return Math.round((parseDay(release)!.getTime() - parseDay(preorder)!.getTime()) / 86_400_000);
}

/** The user's schedule is explicitly PST, fixed UTC−8, not daylight-adjusted Pacific time. */
export function pstDay(date = new Date()): string {
  return new Date(date.getTime() - 8 * 3_600_000).toISOString().slice(0, 10);
}
export function formatEventTime(startsAt: string): string {
  return `${new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: "Etc/GMT+8" }).format(new Date(startsAt))} PST`;
}

export function setReleaseEvents(sets: ReleaseSet[]): CalendarEvent[] {
  const seen = new Set<string>();
  return sets.flatMap((set): CalendarEvent[] => {
    if (!parseDay(set.date)) return [];
    const key = `${set.language}:${normalizedName(set.name)}:${set.date}`;
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ id: `set-release:${key}`, title: `${set.name} · ${set.language === "pokemon" ? "EN" : "JP"} set release`, date: set.date, kind: "release", language: set.language,
      note: "Set release date, not a retailer checkout time. Promotional dates mark the collection's initial release.",
      source: set.source ?? { label: "CardboardDex · Catalog release date", url: `/catalog?${new URLSearchParams({ game: set.language, ...(set.catalogId ? { set: set.catalogId } : { q: set.name }) })}` }, reviewed: CONTENT_REVIEWED }];
  });
}

export function expectedRetailerWindows(month: string, today: string): CalendarEvent[] {
  return monthDays(month).flatMap((date): CalendarEvent[] => {
    if (!date || date < today || date < CONTENT_REVIEWED) return [];
    const day = parseDay(date)!.getUTCDay();
    const retailer = day === 2 || day === 4 ? "target" : day === 3 ? "walmart" : null;
    if (!retailer) return [];
    const hour = retailer === "target" ? "00" : "18";
    return [{ id: `expected:${retailer}:${date}`, title: `${retailer === "target" ? "Target" : "Walmart"} · Expected restock window`, date, kind: "drop", retailer, confidence: "expected", startsAt: `${date}T${hour}:00:00-08:00`,
      note: "Recurring window supplied by the site owner, not a retailer-confirmed drop. Inventory and timing can vary. Midnight means the start of the labeled day.", source: { label: "Schedule assumptions", url: "/faq#drop-patterns" }, reviewed: CONTENT_REVIEWED }];
  });
}

export function previousCalendarMonth(date: string): string | null {
  const parsed = parseDay(date);
  if (!parsed) return null;
  const month = shiftMonth(date.slice(0, 7), -1);
  const lastDay = monthDays(month).filter((day): day is string => Boolean(day)).at(-1)!;
  return `${month}-${String(Math.min(parsed.getUTCDate(), Number(lastDay.slice(-2)))).padStart(2, "0")}`;
}

export function pokemonCenterReminders(sets: ReleaseSet[], today: string): CalendarEvent[] {
  const expansionSeries = new Set(["Mega Evolution", "Scarlet & Violet", "Sword & Shield", "Sun & Moon", "XY", "Black & White", "HeartGold & SoulSilver", "Platinum", "Diamond & Pearl", "EX", "e-Card", "Legendary Collection", "Neo", "Original"]);
  return sets.flatMap((set): CalendarEvent[] => {
    if (set.language !== "pokemon" || !set.series || !expansionSeries.has(set.series) || !parseDay(set.date) || set.date! <= today) return [];
    // A known preorder date supersedes a heuristic reminder for that release.
    if (pokemonCenterHistory.some((record) => normalizedName(record.set) === normalizedName(set.name) && record.release === set.date)) return [];
    return [{ id: `pc-reminder:${set.id}`, title: `${set.name} · Pokémon Center watch reminder`, date: previousCalendarMonth(set.date!), kind: "drop", retailer: "pokemon-center", confidence: "reminder", language: "pokemon",
      note: `Planning reminder one calendar month before ${formatDay(set.date)}. Not a predicted or announced drop; recent reported openings were 37 days early and older ones varied.`, source: { label: "Pokémon Center preorder history & assumptions", url: "/faq#drop-patterns" }, reviewed: CONTENT_REVIEWED }];
  });
}

export function eventsForCalendar(sets: ReleaseSet[], month: string, today: string, showExpected = true): CalendarEvent[] {
  const history: CalendarEvent[] = pokemonCenterHistory.map((record) => ({ id: `pc-history:${record.set}`, title: `${record.set} · Pokémon Center preorders`, date: record.preorder, kind: "drop", retailer: "pokemon-center", confidence: "reported", language: "pokemon", note: `Reported preorder opening, ${preorderLeadDays(record.preorder, record.release)} days before the ${formatDay(record.release)} release. Exact checkout time not verified; this does not indicate current stock.`, source: record.source, reviewed: CONTENT_REVIEWED }));
  return [...calendarEvents, ...setReleaseEvents(sets), ...history, ...(showExpected ? [...expectedRetailerWindows(month, today), ...pokemonCenterReminders(sets, today)] : [])];
}

export type PrintEvidence = { status: "in-print" | "out-of-print"; source: Source; reviewed: string; expires: string; note: string };
// Key by language + catalog set ID. No blanket claims based on age or tournament rotation.
export const printEvidence: Record<string, PrintEvidence> = {};
export type ReleaseSet = { id: string; name: string; series?: string; language: "pokemon" | "pokemon-japan"; date: string | null; catalogId?: string; source?: Source };
export const researchedSets: ReleaseSet[] = [
  ...englishReleases.map((set): ReleaseSet => ({ ...set, id: `tcgplayer-${normalizedName(set.name)}`, language: "pokemon", source: releaseDateSource })),
  { id: "research-30th-jp", name: "30th Celebration", language: "pokemon-japan", date: "2026-09-16", source: sources.anniversary },
];

const DAY = 86_400_000;
export function parseDay(value?: string | null): Date | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? date : null;
}
export function utcDay(date = new Date()): string { return date.toISOString().slice(0, 10); }
export function formatDay(value: string | null): string {
  const date = parseDay(value);
  return date ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(date) : "Date unknown";
}
export function relativeRelease(value: string | null, today: string): string {
  const date = parseDay(value), now = parseDay(today);
  if (!date || !now) return "Date unknown";
  const days = Math.round((now.getTime() - date.getTime()) / DAY);
  if (days === 0) return "Releases today";
  return days < 0 ? `In ${(-days).toLocaleString("en-US")} day${days === -1 ? "" : "s"}` : `${days.toLocaleString("en-US")} day${days === 1 ? "" : "s"} ago`;
}
export function monthDays(month: string): (string | null)[] {
  const first = parseDay(`${month}-01`);
  if (!first) return [];
  const count = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
  const days: (string | null)[] = Array(first.getUTCDay()).fill(null);
  for (let i = 1; i <= count; i++) days.push(`${month}-${String(i).padStart(2, "0")}`);
  while (days.length % 7) days.push(null);
  return days;
}
export function shiftMonth(month: string, delta: number): string {
  const date = parseDay(`${month}-01`);
  if (!date) return month;
  date.setUTCMonth(date.getUTCMonth() + delta);
  return date.toISOString().slice(0, 7);
}
export function printStatus(set: ReleaseSet, today: string, evidence = printEvidence) {
  const record = evidence[`${set.language}:${set.catalogId ?? set.id}`];
  if (record && parseDay(record.reviewed) && parseDay(record.expires) && record.reviewed <= today && record.expires >= today) {
    return { label: record.status === "in-print" ? "In print · sourced" : "Out of print · sourced", evidence: record };
  }
  return { label: "Unknown", evidence: null };
}
function normalizedName(name: string): string {
  const key = name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/^pokemon tcg:\s*/, "")
    .replace(/^(?:sv\d*|swsh\d*|me\d*|sm|xy)\s*[:—–-]\s*/, "")
    .replace(/^(?:mega evolution|scarlet & violet|sword & shield|sun & moon)\s*[—–:-]\s*/, "")
    .replace(/^ex\s+(?!trainer kit)/, "")
    .replace(/\band\b/g, "&").replace(/[^a-z0-9]/g, "");
  const aliases: Record<string, string> = {
    scarletvioletbaseset: "scarletviolet", swordshieldbaseset: "swordshield", smbaseset: "sunmoon", xybaseset: "xy",
    scarletviolet151: "151", expeditionbaseset: "expedition", tradingcardgameclassic: "pokemontradingcardgameclassic",
    wotcpromo: "wizardofthecoastpromos", wotcpromos: "wizardofthecoastpromos", smpromos: "sunmoonpromos", hgsspromos: "heartgoldsoulsilverpromos",
    megaevolutionpromo: "megaevolutionpromos",
    scarletvioletpromocards: "scarletvioletpromos", swordshieldpromocards: "swordshieldpromos",
    mcdonalds25thanniversarypromos: "mcdonaldscollection2021",
    trickortradeboosterbundle: "trickortrade2022", trickortradeboosterbundle2023: "trickortrade2023", trickortradeboosterbundle2024: "trickortrade2024",
    battleacademy: "battleacademy2020",
  };
  return aliases[key] ?? key;
}
export function mergeSets(catalog: { language: ReleaseSet["language"]; sets: CardSetOption[] }[]): ReleaseSet[] {
  const rows: ReleaseSet[] = catalog.flatMap(({ language, sets }) => sets.map((set) => ({ id: `${language}:${set.id}`, name: set.name, series: set.series ?? undefined, language, date: parseDay(set.release_date) ? set.release_date! : null, catalogId: set.id })));
  for (const set of researchedSets) {
    const match = rows.find((row) => row.language === set.language && normalizedName(row.name) === normalizedName(set.name));
    if (match) { match.date = set.date; match.source = set.source; match.series = set.series ?? match.series; }
    else rows.push({ ...set });
  }
  return rows.sort((a, b) => (b.date ?? "").localeCompare(a.date ?? "") || a.name.localeCompare(b.name));
}
