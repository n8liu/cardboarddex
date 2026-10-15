import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MobileSearchFocus } from "@/components/mobile-search-focus";
import { SearchInput } from "@/components/ui/search-input";

let viewport: EventTarget & { height: number; offsetTop: number };
const scroll = vi.fn();
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("innerWidth", 390);
  vi.stubGlobal("scrollY", 100);
  vi.stubGlobal("scrollTo", scroll);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 16));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => window.clearTimeout(id));
  viewport = Object.assign(new EventTarget(), { height: 700, offsetTop: 0 });
  vi.stubGlobal("visualViewport", viewport);
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); scroll.mockClear(); });

function setup() {
  const result = render(<><MobileSearchFocus /><header data-site-header /><div data-mobile-search-container><SearchInput value="" onChange={() => {}} placeholder="Search cards" /></div></>);
  const input = screen.getByPlaceholderText("Search cards");
  vi.spyOn(input, "getBoundingClientRect").mockReturnValue({ top: 300, height: 52 } as DOMRect);
  vi.spyOn(result.container.querySelector("header")!, "getBoundingClientRect").mockReturnValue({ bottom: 64 } as DOMRect);
  return { ...result, input };
}
const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));

it("aligns the shared mobile search below the header and sizes suggestions above the keyboard", () => {
  const { input, container } = setup();
  act(() => input.focus()); advance(16);
  expect(scroll).toHaveBeenLastCalledWith({ top: 328, behavior: "instant" });
  viewport.height = 350;
  viewport.dispatchEvent(new Event("resize")); advance(100);
  expect(container.querySelector<HTMLElement>("[data-mobile-search-container]")!.style.getPropertyValue("--search-results-max-height")).toBe("210px");
});

it("does not move desktop searches", () => {
  vi.stubGlobal("innerWidth", 1280);
  const { input } = setup();
  act(() => input.focus()); advance(1000);
  expect(scroll).not.toHaveBeenCalled();
});

it("cancels deferred alignment when focus leaves", () => {
  const { input } = setup();
  act(() => { input.focus(); input.blur(); }); advance(1000);
  expect(scroll).not.toHaveBeenCalled();
});

it("does not keep scrolling after the keyboard settles", () => {
  const { input } = setup();
  act(() => input.focus()); advance(1000);
  scroll.mockClear();
  viewport.dispatchEvent(new Event("resize")); advance(1000);
  expect(scroll).not.toHaveBeenCalled();
});

it("ignores modal searches", () => {
  render(<><MobileSearchFocus /><div role="dialog"><input data-mobile-search aria-label="Modal search" /></div></>);
  act(() => screen.getByLabelText("Modal search").focus()); advance(1000);
  expect(scroll).not.toHaveBeenCalled();
});

it("cleans up listeners and scheduled positioning on unmount", () => {
  const { input, unmount } = setup();
  act(() => input.focus());
  unmount(); advance(1000);
  viewport.dispatchEvent(new Event("resize")); advance(100);
  expect(scroll).not.toHaveBeenCalled();
});
