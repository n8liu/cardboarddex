import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StickyCardActions } from "@/components/sticky-card-actions";
import type { CardDetail } from "@/types/card";

vi.mock("@/components/binder/add-to-binder-button", () => ({ AddToBinderButton: () => <button>Add to binder</button> }));
vi.mock("@/components/shop-ebay-button", () => ({ ShopOnEbayButton: () => <a href="#">eBay</a> }));
vi.mock("@/context/currency-context", () => ({ useCurrency: () => ({ formatPrice: (v: number) => `$${v}` }) }));

let report: (entry: Partial<IntersectionObserverEntry>) => void = () => {};
beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: IntersectionObserverCallback) {
      report = (entry) => callback([entry as IntersectionObserverEntry], this as unknown as IntersectionObserver);
    }
    observe() {}
    disconnect() {}
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const card = { id: "base1-4", name: "Charizard", market_price: 420 } as CardDetail;

it("shows the bar only after the hero actions scroll above the viewport", () => {
  render(<StickyCardActions card={card}><button>Hero action</button></StickyCardActions>);
  const bar = screen.getByTestId("sticky-card-actions");
  expect(bar).toHaveAttribute("inert");
  act(() => report({ isIntersecting: false, boundingClientRect: { top: -40 } as DOMRectReadOnly }));
  expect(bar).not.toHaveAttribute("inert");
  expect(bar).toHaveTextContent("$420");
  // Below the viewport (not yet reached) keeps it hidden.
  act(() => report({ isIntersecting: false, boundingClientRect: { top: 900 } as DOMRectReadOnly }));
  expect(bar).toHaveAttribute("inert");
});
