import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  PRICE_RANGE_MAX,
  PriceRangeSlider,
  positionToFilter,
  positionToPrice,
  priceToPosition,
} from "@/components/ui/price-range-slider";

vi.mock("@/context/currency-context", () => ({ useCurrency: () => ({ formatPrice: (value: number) => `$${value}` }) }));

describe("PriceRangeSlider continuous scale", () => {
  it("maps unset prices to the track ends", () => {
    expect(priceToPosition(null, false)).toBe(0);
    expect(priceToPosition(undefined, false)).toBe(0);
    expect(priceToPosition(null, true)).toBe(1);
    expect(priceToPosition(undefined, true)).toBe(1);
  });

  it("round-trips any whole-dollar price, not just fixed steps", () => {
    for (const price of [0, 1, 7, 28, 45, 137, 999, 2468, PRICE_RANGE_MAX]) {
      expect(positionToPrice(priceToPosition(price, false))).toBe(price);
    }
  });

  it("is monotonic and gives low prices proportionate room", () => {
    const prices = Array.from({ length: 101 }, (_, i) => positionToPrice(i / 100));
    expect(prices.every((price, i) => i === 0 || price >= prices[i - 1])).toBe(true);
    // Log scale: $100 sits a little past the middle rather than in the first 2% of the track.
    expect(priceToPosition(100, false)).toBeGreaterThan(0.5);
    expect(priceToPosition(100, false)).toBeLessThan(0.6);
  });

  it("clamps out-of-range positions and prices", () => {
    expect(positionToPrice(-1)).toBe(0);
    expect(positionToPrice(2)).toBe(PRICE_RANGE_MAX);
    expect(priceToPosition(-5, false)).toBe(0);
    expect(priceToPosition(99999, false)).toBe(1);
  });

  it("treats the max thumb at the end as unbounded", () => {
    expect(positionToFilter(1, true)).toBeNull();
    expect(positionToFilter(1, false)).toBe(PRICE_RANGE_MAX);
    expect(positionToFilter(0, false)).toBe(0);
  });

  it("moves by small continuous increments from the keyboard", () => {
    const onChange = vi.fn();
    render(<PriceRangeSlider minPrice={null} maxPrice={100} onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Maximum price range handle" }), { key: "ArrowRight" });
    const { min, max } = onChange.mock.calls[0][0];
    expect(min).toBe(0);
    // One percent of the track above $100: a few dollars, not the next fixed step ($150).
    expect(max).toBeGreaterThan(100);
    expect(max).toBeLessThan(115);
  });
});
