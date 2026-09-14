import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { CurrencyProvider, useCurrency } from "@/context/currency-context";

describe("CurrencyContext", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <CurrencyProvider>{children}</CurrencyProvider>
  );

  it("defaults to USD with $ symbol and rate 1.0", () => {
    const { result } = renderHook(() => useCurrency(), { wrapper });
    expect(result.current.currency).toBe("USD");
    expect(result.current.symbol).toBe("$");
    expect(result.current.rate).toBe(1.0);
  });

  it("converts and formats USD prices properly", () => {
    const { result } = renderHook(() => useCurrency(), { wrapper });
    expect(result.current.convertPrice(50)).toBe(50);
    expect(result.current.formatPrice(50)).toBe("$50.00");
    expect(result.current.formatPrice(null)).toBe("—");
  });

  it("switches to JPY and formats with correct symbol and zero decimals", () => {
    const { result } = renderHook(() => useCurrency(), { wrapper });

    act(() => {
      result.current.setCurrency("JPY");
    });

    expect(result.current.currency).toBe("JPY");
    expect(result.current.symbol).toBe("¥");
    expect(result.current.rate).toBe(155.0);
    // 100 USD = 15,500 JPY
    expect(result.current.convertPrice(100)).toBe(15500);
    expect(result.current.formatPrice(100)).toBe("￥15,500");
  });

  it("switches to EUR and formats with € symbol", () => {
    const { result } = renderHook(() => useCurrency(), { wrapper });

    act(() => {
      result.current.setCurrency("EUR");
    });

    expect(result.current.currency).toBe("EUR");
    expect(result.current.symbol).toBe("€");
    expect(result.current.rate).toBe(0.92);
    expect(result.current.convertPrice(100)).toBe(92);
    expect(result.current.formatPrice(100)).toBe("€92.00");
  });

  it("persists currency selection in localStorage", () => {
    const { result } = renderHook(() => useCurrency(), { wrapper });

    act(() => {
      result.current.setCurrency("GBP");
    });

    expect(localStorage.getItem("cardboarddex_currency")).toBe("GBP");
  });
});
