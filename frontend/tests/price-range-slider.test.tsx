import { describe, it, expect } from "vitest";
import {
  PRICE_RANGE_STEPS,
  priceToStepIndex,
  stepIndexToPrice,
} from "@/components/ui/price-range-slider";

describe("PriceRangeSlider step index mapping", () => {
  it("converts null or undefined price to boundary indices", () => {
    expect(priceToStepIndex(null, false)).toBe(0);
    expect(priceToStepIndex(undefined, false)).toBe(0);
    expect(priceToStepIndex(null, true)).toBe(PRICE_RANGE_STEPS.length - 1);
    expect(priceToStepIndex(undefined, true)).toBe(PRICE_RANGE_STEPS.length - 1);
  });

  it("maps exact step prices to corresponding index", () => {
    expect(priceToStepIndex(1, false)).toBe(0);
    expect(priceToStepIndex(10, false)).toBe(1);
    expect(priceToStepIndex(25, false)).toBe(2);
    expect(priceToStepIndex(50, false)).toBe(3);
    expect(priceToStepIndex(100, false)).toBe(4);
    expect(priceToStepIndex(5000, true)).toBe(11);
  });

  it("maps intermediate prices to the closest step index", () => {
    // 28 is closer to 25 than 50
    expect(priceToStepIndex(28, false)).toBe(2);
    // 45 is closer to 50 than 25
    expect(priceToStepIndex(45, false)).toBe(3);
  });

  it("converts step index to price values correctly", () => {
    // Min slider at index 0 allows cards down to 0
    expect(stepIndexToPrice(0, false)).toBe(0);
    expect(stepIndexToPrice(2, false)).toBe(25);
    expect(stepIndexToPrice(4, false)).toBe(100);

    // Max slider at last index is unbounded (null)
    expect(stepIndexToPrice(PRICE_RANGE_STEPS.length - 1, true)).toBeNull();
    // Max slider below last index returns exact price
    expect(stepIndexToPrice(4, true)).toBe(100);
  });
});
