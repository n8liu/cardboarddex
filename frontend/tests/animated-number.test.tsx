import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnimatedNumber } from "@/components/ui/animated-number";

let enter: (entries: { isIntersecting: boolean }[]) => void;
let frame: FrameRequestCallback;
const disconnect = vi.fn();
const requestFrame = vi.fn((callback: FrameRequestCallback) => { frame = callback; return 1; });
const cancelFrame = vi.fn();
let reduced = false;

beforeEach(() => {
  reduced = false;
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: typeof enter) { enter = callback; }
    observe() {}
    disconnect = disconnect;
  });
  vi.stubGlobal("matchMedia", () => ({ matches: reduced, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.stubGlobal("requestAnimationFrame", requestFrame);
  vi.stubGlobal("cancelAnimationFrame", cancelFrame);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

const visible = (container: HTMLElement) => container.querySelectorAll('[aria-hidden="true"]')[1].textContent;
const tick = (time: number) => act(() => frame(time));
const reveal = () => act(() => enter([{ isIntersecting: true }]));

describe("AnimatedNumber", () => {
  it("waits for visibility, counts from zero, and exposes the final value accessibly", () => {
    const { container } = render(<AnimatedNumber value={100} duration={1000} />);
    expect(visible(container)).toBe("0");
    expect(container.querySelector('.sr-only')).toHaveTextContent("100");
    expect(requestFrame).not.toHaveBeenCalled();
    act(() => enter([{ isIntersecting: false }]));
    expect(requestFrame).not.toHaveBeenCalled();
    reveal(); tick(0); tick(500);
    expect(visible(container)).toBe("88");
    tick(1000);
    expect(visible(container)).toBe("100");
    const calls = requestFrame.mock.calls.length;
    reveal();
    expect(requestFrame).toHaveBeenCalledTimes(calls);
  });

  it("animates data that arrives later, preserving negative percentages", () => {
    const format = (n: number) => `${n.toFixed(1)}%`;
    const { container, rerender } = render(<AnimatedNumber value={0} format={format} />);
    rerender(<AnimatedNumber value={-25.5} format={format} />);
    expect(visible(container)).toBe("0.0%");
    reveal(); tick(0); tick(900);
    expect(visible(container)).toBe("-25.5%");
  });

  it("does not restart when a parent recreates a formatter", () => {
    const { rerender } = render(<AnimatedNumber value={12} format={(n) => `$${n.toFixed(2)}`} />);
    reveal(); tick(0);
    const calls = requestFrame.mock.calls.length;
    rerender(<AnimatedNumber value={12} format={(n) => `$${n.toFixed(2)}`} />);
    expect(requestFrame).toHaveBeenCalledTimes(calls);
    expect(cancelFrame).not.toHaveBeenCalled();
  });

  it("shows final values immediately for reduced motion", () => {
    reduced = true;
    const { container } = render(<AnimatedNumber value={42} />);
    expect(visible(container)).toBe("42");
    expect(requestFrame).not.toHaveBeenCalled();
  });

  it("falls back to final values without IntersectionObserver", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    const { container } = render(<AnimatedNumber value={42} />);
    expect(visible(container)).toBe("42");
  });

  it("cancels frames and disconnects on unmount", () => {
    const { unmount } = render(<AnimatedNumber value={42} />);
    reveal();
    unmount();
    expect(cancelFrame).toHaveBeenCalledWith(1);
    expect(disconnect).toHaveBeenCalled();
  });
});
