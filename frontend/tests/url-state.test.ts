import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { writeUrlFilters } from "@/lib/url-state";

let push: ReturnType<typeof vi.spyOn>;
let replace: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  window.history.replaceState(null, "", "/catalog?set=sv8");
  push = vi.spyOn(window.history, "pushState");
  replace = vi.spyOn(window.history, "replaceState");
});
afterEach(() => vi.restoreAllMocks());

it("pushes discrete filter changes so Back restores them", () => {
  writeUrlFilters({ set: "sv8", sort: "price_asc" }, ["q"]);
  expect(push).toHaveBeenCalledWith(null, "", "/catalog?set=sv8&sort=price_asc");
  expect(replace).not.toHaveBeenCalled();
});

it("replaces while typing and removes empty values", () => {
  writeUrlFilters({ q: "char", set: "sv8" }, ["q"]);
  expect(replace).toHaveBeenCalledWith(null, "", "/catalog?set=sv8&q=char");
  writeUrlFilters({ q: "", set: null }, ["q"]);
  expect(push).toHaveBeenLastCalledWith(null, "", "/catalog");
});

it("does nothing when the URL already matches (popstate restores)", () => {
  writeUrlFilters({ set: "sv8", q: null }, ["q"]);
  expect(push).not.toHaveBeenCalled();
  expect(replace).not.toHaveBeenCalled();
});
