import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RecentlyViewed, RememberViewedCard } from "@/components/recently-viewed";
import { clearRecentCards, readRecentCards, rememberCard, RECENT_KEY } from "@/lib/recently-viewed";

vi.mock("@/components/card-image", () => ({ default: () => null }));
vi.mock("@/lib/api", () => ({ cardImageUrl: (s: string) => s }));
const card = (id: string) => ({ id, name: `Card ${id}`, set_name: "Test Set", image_url: `/cards/${id}/image` });
beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("deduplicates, caps at 12, expires entries and validates stored data", () => {
  const now = Date.now();
  vi.spyOn(Date, "now").mockReturnValue(now);
  for (let n = 0; n < 15; n++) rememberCard(card(String(n)));
  rememberCard(card("10"));
  expect(readRecentCards()).toHaveLength(12);
  expect(readRecentCards()[0].id).toBe("10");
  expect(readRecentCards().filter((c) => c.id === "10")).toHaveLength(1);
  localStorage.setItem(RECENT_KEY, JSON.stringify([
    { ...card("valid"), viewed_at: now },
    { ...card("expired"), viewed_at: now - 31 * 86400000 },
    { ...card("future"), viewed_at: now + 1000 },
    { ...card("bad"), image_url: "file:///secret", viewed_at: now },
    null,
  ]));
  expect(readRecentCards().map((c) => c.id)).toEqual(["valid"]);
});

it("records a successful card view and clears history without touching the binder", () => {
  localStorage.setItem("cardboarddex_binder", "keep");
  render(<><RememberViewedCard card={card("viewed")} /><RecentlyViewed /></>);
  expect(screen.getByText("Card viewed").closest("a")).toHaveAttribute("href", "/cards/viewed");
  fireEvent.click(screen.getByRole("button", { name: "Clear history" }));
  expect(screen.queryByRole("heading", { name: "Recently viewed" })).not.toBeInTheDocument();
  expect(localStorage.getItem(RECENT_KEY)).toBeNull();
  expect(localStorage.getItem("cardboarddex_binder")).toBe("keep");
});

it("refreshes when another tab clears storage", () => {
  rememberCard(card("one"));
  render(<RecentlyViewed />);
  localStorage.removeItem(RECENT_KEY);
  fireEvent(window, new StorageEvent("storage", { key: RECENT_KEY }));
  expect(screen.queryByText("Card one")).not.toBeInTheDocument();
});

it("handles corrupt or unavailable browser storage without breaking navigation", () => {
  const log = vi.spyOn(console, "warn").mockImplementation(() => {});
  localStorage.setItem(RECENT_KEY, "invalid JSON");
  expect(readRecentCards()).toEqual([]);
  vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new Error("restricted"); });
  expect(() => rememberCard(card("one"))).not.toThrow();
  expect(clearRecentCards()).toBe(false);
  expect(log).toHaveBeenCalled();
});
