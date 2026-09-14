"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export type SupportedCurrency = "USD" | "JPY" | "EUR" | "GBP";

export const SUPPORTED_CURRENCIES: {
  code: SupportedCurrency;
  symbol: string;
  label: string;
}[] = [
  { code: "USD", symbol: "$", label: "USD ($)" },
  { code: "EUR", symbol: "€", label: "EUR (€)" },
  { code: "JPY", symbol: "¥", label: "JPY (¥)" },
  { code: "GBP", symbol: "£", label: "GBP (£)" },
];

const EXCHANGE_RATES: Record<SupportedCurrency, number> = {
  USD: 1.0,
  EUR: 0.92,
  JPY: 155.0,
  GBP: 0.79,
};

interface CurrencyContextType {
  currency: SupportedCurrency;
  setCurrency: (currency: SupportedCurrency) => void;
  rate: number;
  symbol: string;
  convertPrice: (usdValue: number | null | undefined) => number | null;
  formatPrice: (
    usdValue: number | null | undefined,
    options?: { showPending?: boolean; digits?: number }
  ) => string;
}

const CurrencyContext = createContext<CurrencyContextType>({
  currency: "USD",
  setCurrency: () => {},
  rate: 1.0,
  symbol: "$",
  convertPrice: (v) => v ?? null,
  formatPrice: (v) => (v != null ? `$${v.toFixed(2)}` : "—"),
});

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [currency, setCurrencyState] = useState<SupportedCurrency>("USD");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("cardboarddex_currency") as SupportedCurrency;
      if (saved && ["USD", "JPY", "EUR", "GBP"].includes(saved)) {
        setCurrencyState(saved);
      }
    } catch {
      // Ignore localStorage errors in restricted environments
    }
  }, []);

  const setCurrency = (c: SupportedCurrency) => {
    setCurrencyState(c);
    try {
      localStorage.setItem("cardboarddex_currency", c);
    } catch {
      // Ignore
    }
  };

  const rate = EXCHANGE_RATES[currency] || 1.0;
  const currDef = SUPPORTED_CURRENCIES.find((item) => item.code === currency);
  const symbol = currDef?.symbol || "$";

  const convertPrice = (usdValue: number | null | undefined): number | null => {
    if (usdValue === null || usdValue === undefined || isNaN(usdValue)) return null;
    return usdValue * rate;
  };

  const formatPrice = (
    usdValue: number | null | undefined,
    options: { showPending?: boolean; digits?: number } = {}
  ): string => {
    const { showPending = false, digits } = options;
    if (usdValue === null || usdValue === undefined || isNaN(usdValue)) {
      return showPending ? "Price pending" : "—";
    }

    const converted = usdValue * rate;
    const fractionDigits = digits !== undefined ? digits : currency === "JPY" ? 0 : 2;

    return new Intl.NumberFormat(currency === "JPY" ? "ja-JP" : "en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: fractionDigits,
      minimumFractionDigits: fractionDigits,
    }).format(converted);
  };

  return (
    <CurrencyContext.Provider
      value={{
        currency,
        setCurrency,
        rate,
        symbol,
        convertPrice,
        formatPrice,
      }}
    >
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency(): CurrencyContextType {
  return useContext(CurrencyContext);
}
