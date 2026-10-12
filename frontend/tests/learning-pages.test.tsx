import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import FaqPage from "@/app/faq/page";
import { FaqHub } from "@/components/faq-hub";
import { ReleaseCalendar } from "@/components/release-calendar";
import { getCardSets } from "@/lib/api";
import { faqs, guides } from "@/lib/learning-content";
import { calendarEvents, mergeSets, monthDays, parseDay, printStatus, relativeRelease, shiftMonth, type PrintEvidence, type ReleaseSet } from "@/lib/release-calendar";
import englishReleases from "@/lib/english-set-releases.json";
import { eventsForCalendar, expectedRetailerWindows, formatEventTime, pokemonCenterReminders, previousCalendarMonth, pstDay, setReleaseEvents } from "@/lib/release-calendar";

vi.mock("@/lib/api", () => ({ getCardSets: vi.fn() }));
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-12T12:00:00Z"));
  vi.mocked(getCardSets).mockReset().mockImplementation(async (game) => game === "pokemon-japan" ? [
    { id: "jp", name: "Japanese sample", series: "Pokemon Japan", release_date: "2026-10-11" },
  ] : [
    { id: "base", name: "Base Set", series: "Base", release_date: "1999-01-09" },
    { id: "unknown", name: "Undated Set", series: null, release_date: null },
    { id: "30th", name: "30th Celebration", series: "Mega Evolution", release_date: "2026-09-16" },
  ]);
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

it("builds calendar releases from all directory dates, deduplicates aliases and keeps languages separate", () => {
  const result = setReleaseEvents([
    { id: "en1", name: "SV01: Scarlet & Violet Base Set", language: "pokemon", date: "2023-03-31" },
    { id: "en2", name: "Scarlet & Violet", language: "pokemon", date: "2023-03-31" },
    { id: "jp", name: "Scarlet & Violet", language: "pokemon-japan", date: "2023-01-20" },
    { id: "bad", name: "Bad", language: "pokemon", date: "2026-02-30" },
  ]);
  expect(result).toHaveLength(2);
  expect(result.map((event) => event.date)).toEqual(["2023-03-31", "2023-01-20"]);
  expect(result.every((event) => event.kind === "release" && !event.startsAt)).toBe(true);
  const all = eventsForCalendar(mergeSets([]), "2026-09", "2026-10-12");
  expect(all.filter((event) => event.title.includes("30th Celebration") && event.date === "2026-09-16")).toHaveLength(2);
});

it("generates only future Tuesday/Thursday midnight and Wednesday evening PST windows", () => {
  const events = expectedRetailerWindows("2026-10", "2026-10-12");
  expect(events.filter((event) => event.retailer === "target").map((event) => event.date)).toEqual(["2026-10-13", "2026-10-15", "2026-10-20", "2026-10-22", "2026-10-27", "2026-10-29"]);
  const walmart = events.find((event) => event.retailer === "walmart")!;
  expect(walmart.date).toBe("2026-10-14");
  expect(new Date(walmart.startsAt!).toISOString()).toBe("2026-10-15T02:00:00.000Z");
  expect(formatEventTime(walmart.startsAt!)).toBe("6:00 PM PST");
  expect(formatEventTime(events[0].startsAt!)).toBe("12:00 AM PST");
  expect(events.every((event) => event.confidence === "expected")).toBe(true);
  expect(expectedRetailerWindows("2025-01", "2026-10-12")).toHaveLength(0);
  // Fixed PST is explicit even during the summer daylight-saving season.
  expect(pstDay(new Date("2026-07-01T07:30:00Z"))).toBe("2026-06-30");
  expect(pstDay(new Date("2026-12-01T08:00:00Z"))).toBe("2026-12-01");
});

it("clamps one-month reminders and suppresses them for known preorders, Japanese sets and promos", () => {
  expect(previousCalendarMonth("2027-03-31")).toBe("2027-02-28");
  expect(previousCalendarMonth("2024-03-31")).toBe("2024-02-29");
  expect(previousCalendarMonth("2027-01-15")).toBe("2026-12-15");
  const future: ReleaseSet = { id: "new", name: "Future example", language: "pokemon", series: "Mega Evolution", date: "2027-03-31" };
  const reminders = pokemonCenterReminders([future, { ...future, id: "jp", language: "pokemon-japan" }, { ...future, id: "promo", series: "Black Star Promos" }, { ...future, id: "delta", name: "ME06: Delta Reign", date: "2026-11-06" }], "2026-10-12");
  expect(reminders).toHaveLength(1);
  expect(reminders[0]).toMatchObject({ date: "2027-02-28", confidence: "reminder" });
  expect(reminders[0].startsAt).toBeUndefined();
});

it("shows historical set dates and researched preorders in the calendar, with independent language filtering", async () => {
  render(<ReleaseCalendar />);
  await waitFor(() => expect(screen.queryByText("Loading catalog sets…")).not.toBeInTheDocument());
  const month = screen.getByLabelText("Jump to month");
  fireEvent.change(month, { target: { value: "1999-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Jan 9, 1999, 1 event" }));
  expect(screen.getByRole("heading", { name: "Base Set · EN set release" })).toBeInTheDocument();
  fireEvent.change(month, { target: { value: "2026-09" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Retailer" }), { target: { value: "pokemon-center" } });
  fireEvent.click(screen.getByRole("button", { name: "Sep 30, 2026, 1 event" }));
  expect(screen.getByText("Reported preorder opening")).toBeInTheDocument();
  expect(screen.getByText(/Reported preorder opening, 37 days before/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Calendar language" }), { target: { value: "pokemon-japan" } });
  expect(screen.queryByRole("heading", { name: "Delta Reign · Pokémon Center preorders" })).not.toBeInTheDocument();
  expect(getCardSets).toHaveBeenCalledTimes(2);
});

it("places the calendar before FAQ questions and keeps section navigation on the combined page", async () => {
  render(<FaqPage />);
  await waitFor(() => expect(screen.queryByText("Loading catalog sets…")).not.toBeInTheDocument());
  const calendar = screen.getByRole("heading", { name: "Release & drop calendar" });
  const questions = screen.getByRole("heading", { name: "Frequently asked questions" });
  expect(calendar.compareDocumentPosition(questions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const navigation = within(screen.getByRole("navigation", { name: "Learning pages" }));
  expect(navigation.getByRole("link", { name: "Calendar" })).toHaveAttribute("href", "/faq#calendar");
  expect(navigation.getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "/faq#questions");
});

it("imports dated English sets across all article series and matches catalog prefixes without touching Japanese dates", () => {
  expect(englishReleases).toHaveLength(187);
  expect(new Set(englishReleases.map((set) => set.series)).size).toBe(22);
  for (const set of englishReleases) expect(parseDay(set.date)).not.toBeNull();
  const rows = mergeSets([
    { language: "pokemon", sets: [
      { id: "sv", name: "SV01: Scarlet & Violet Base Set", series: null, release_date: "2023-01-01" },
      { id: "ex", name: "EX Ruby and Sapphire", series: null },
      { id: "151", name: "SV: Scarlet & Violet 151", series: null },
      { id: "subset", name: "SWSH12: Silver Tempest Trainer Gallery", series: null },
    ] },
    { language: "pokemon-japan", sets: [{ id: "jp", name: "Scarlet & Violet", series: "Pokemon Japan", release_date: "2023-01-20" }] },
  ]);
  expect(rows.find((set) => set.catalogId === "sv")).toMatchObject({ date: "2023-03-31", series: "Scarlet & Violet", source: { label: "TCGplayer · English set release dates" } });
  expect(rows.find((set) => set.catalogId === "ex")?.date).toBe("2003-07-18");
  expect(rows.find((set) => set.catalogId === "151")?.date).toBe("2023-09-22");
  expect(rows.find((set) => set.catalogId === "subset")?.source).toBeUndefined();
  expect(rows.find((set) => set.catalogId === "jp")?.date).toBe("2023-01-20");
  expect(rows.filter((set) => set.name === "Scarlet & Violet" && set.language === "pokemon")).toHaveLength(0);
});

it("filters the release directory by series and can search older sets without catalog data", async () => {
  render(<ReleaseCalendar />);
  await waitFor(() => expect(screen.queryByText("Loading catalog sets…")).not.toBeInTheDocument());
  fireEvent.change(screen.getByRole("combobox", { name: "Series / collection" }), { target: { value: "Original" } });
  const table = within(screen.getByRole("table", { name: "Set release dates, time since release, and sourced print status" }));
  expect(table.getByText("Base Set ↗")).toBeInTheDocument();
  expect(table.getByText("Jan 9, 1999")).toBeInTheDocument();
  expect(table.queryByText("Delta Reign ↗")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "Search sets" }), { target: { value: "Jungle" } });
  expect(table.getByText("Jun 16, 1999")).toBeInTheDocument();
  expect(table.queryByText("Base Set ↗")).not.toBeInTheDocument();
});

it("searches FAQ answers and guides, filters categories, and resets empty results", () => {
  render(<FaqHub />);
  fireEvent.change(screen.getByRole("searchbox", { name: "Search questions and guides" }), { target: { value: "binder" } });
  expect(screen.getByText("Do I need an account, and where is my binder saved?")).toBeInTheDocument();
  expect(screen.queryByText("Is my set still in print?")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Releases & shopping" }));
  expect(screen.getByText("No questions match these filters.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Reset search and category" }));
  expect(screen.getByText("Is my set still in print?")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /A short history of the Pokémon TCG/ })).toHaveAttribute("href", "/faq/guides/pokemon-tcg-history");
});

it("keeps all FAQ guide links valid and all article section anchors unique", () => {
  const slugs = new Set(guides.map((guide) => guide.slug));
  expect(slugs.size).toBe(guides.length);
  for (const faq of faqs) if (faq.link?.href.startsWith("/faq/guides/")) expect(slugs.has(faq.link.href.split("/").at(-1)!)).toBe(true);
  for (const guide of guides) {
    expect(new Set(guide.sections.map((s) => s.id)).size).toBe(guide.sections.length);
    expect(guide.sections.length).toBeGreaterThanOrEqual(3);
    for (const source of guide.sources) expect(new URL(source.url).protocol).toBe("https:");
  }
});

it("handles leap days, invalid dates, month boundaries and UTC elapsed days", () => {
  expect(parseDay("2026-02-29")).toBeNull();
  expect(parseDay("2024-02-29")).not.toBeNull();
  expect(parseDay("bad")).toBeNull();
  expect(monthDays("2024-02").filter(Boolean)).toHaveLength(29);
  expect(monthDays("2026-10").indexOf("2026-10-01")).toBe(4);
  expect(shiftMonth("2026-12", 1)).toBe("2027-01");
  expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  expect(relativeRelease("2026-10-11", "2026-10-12")).toBe("1 day ago");
  expect(relativeRelease("2026-10-13", "2026-10-12")).toBe("In 1 day");
  expect(relativeRelease("2026-10-12", "2026-10-12")).toBe("Releases today");
  expect(relativeRelease(null, "2026-10-12")).toBe("Date unknown");
});

it("does not infer printing from release age and expires dated evidence", () => {
  const set: ReleaseSet = { id: "base", catalogId: "base", name: "Base", language: "pokemon", date: "1999-01-09" };
  expect(printStatus(set, "2026-10-12").label).toBe("Unknown");
  const evidence: Record<string, PrintEvidence> = { "pokemon:base": { status: "out-of-print", reviewed: "2026-10-01", expires: "2026-10-20", note: "Test evidence", source: { label: "Example", url: "https://example.com" } } };
  expect(printStatus(set, "2026-10-12", evidence).label).toBe("Out of print · sourced");
  expect(printStatus(set, "2026-10-21", evidence).label).toBe("Unknown");
  expect(printStatus(set, "2026-09-30", evidence).label).toBe("Unknown");
  expect(printStatus({ ...set, language: "pokemon-japan" }, "2026-10-12", evidence).label).toBe("Unknown");
});

it("merges announcement dates without duplicating a matching catalog set or losing its link", () => {
  const result = mergeSets([{ language: "pokemon", sets: [
    { id: "ann", name: "30th Celebration", series: "Mega", release_date: null },
    { id: "bad", name: "Bad date", series: null, release_date: "2026-02-31" },
  ] }]);
  expect(result.filter((s) => s.name === "30th Celebration" && s.language === "pokemon")).toHaveLength(1);
  expect(result.find((s) => s.catalogId === "ann")).toMatchObject({ date: "2026-09-16", source: expect.any(Object) });
  expect(result.find((s) => s.catalogId === "bad")?.date).toBeNull();
});

it("shows calendar release events, navigates months and selects a date", async () => {
  render(<ReleaseCalendar />);
  await waitFor(() => expect(screen.queryByText("Loading catalog sets…")).not.toBeInTheDocument());
  expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Oct 30, 2026, 1 event" }));
  expect(screen.getByRole("heading", { name: "Oct 30, 2026 · 1 dated event" })).toBeInTheDocument();
  expect(screen.getByText("Announced release")).toBeInTheDocument();
  expect(screen.getByText("Oct 30, 2026 · Time not announced")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next month" }));
  expect(screen.getByRole("heading", { name: "November 2026" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Delta Reign · EN set release" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "list" }));
  expect(screen.queryByRole("button", { name: "Nov 6, 2026, 1 event" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
});

it("separates unannounced retailer drops from release dates and filters each retailer", async () => {
  render(<ReleaseCalendar />);
  await waitFor(() => expect(screen.queryByText("Loading catalog sets…")).not.toBeInTheDocument());
  fireEvent.change(screen.getByRole("combobox", { name: "Retailer" }), { target: { value: "target" } });
  expect(screen.getAllByText("Expected window · unconfirmed").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("checkbox", { name: "Show expected windows & reminders" }));
  expect(screen.getByText(/No dated events match/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Target · Next online drop" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Walmart · Next online drop" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Event type" }), { target: { value: "release" } });
  expect(screen.getByText("No undated online drops match your filters.")).toBeInTheDocument();
  for (const event of calendarEvents) {
    expect(event.reviewed).toBeTruthy();
    expect(new URL(event.source.url).protocol).toBe("https:");
    if (event.date) expect(parseDay(event.date)).not.toBeNull();
    if (event.kind === "drop") expect(event.date).toBeNull();
  }
});

it("lists catalog sets with age, language, unknown dates and honest printing filters", async () => {
  render(<ReleaseCalendar />);
  await waitFor(() => expect(screen.queryByText("Loading catalog sets…")).not.toBeInTheDocument());
  const table = within(screen.getByRole("table", { name: "Set release dates, time since release, and sourced print status" }));
  expect(table.getByText("1 day ago")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "Search sets" }), { target: { value: "Undated Set" } });
  expect(table.getAllByText("Date unknown")).toHaveLength(2);
  fireEvent.change(screen.getByRole("searchbox", { name: "Search sets" }), { target: { value: "" } });
  expect(table.getByRole("link", { name: "Japanese sample ↗" })).toHaveAttribute("href", "/catalog?game=pokemon-japan&set=jp");
  fireEvent.change(screen.getByRole("combobox", { name: "Set language" }), { target: { value: "pokemon-japan" } });
  expect(table.queryByText("Base Set ↗")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Print status" }), { target: { value: "in-print" } });
  expect(screen.getByText(/No sets match these filters/)).toBeInTheDocument();
  expect(getCardSets).toHaveBeenCalledTimes(2);
});

it("preserves announcements and the successful language when catalog loading fails, then retries", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(getCardSets).mockRejectedValueOnce(new Error("English unavailable"));
  render(<ReleaseCalendar />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load English catalog sets");
  expect(screen.getByText("Japanese sample ↗")).toBeInTheDocument();
  expect(screen.getAllByText("30th Celebration ↗")).toHaveLength(2);
  expect(log).toHaveBeenCalledWith(expect.stringContaining("pokemon sets"), expect.any(Error));
  fireEvent.click(screen.getByRole("button", { name: "Retry sets" }));
  await waitFor(() => expect(screen.queryByText("Loading catalog sets…")).not.toBeInTheDocument());
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});
