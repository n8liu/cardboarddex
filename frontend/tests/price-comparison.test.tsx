import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { PriceComparison } from "@/components/price-comparison";

afterEach(cleanup);

it("labels estimated previous prices and shows the monetary increase", () => {
  render(<PriceComparison value={{ previous_price: 100, comparison_price: 120, price_change_amount: 20, comparison_source: "estimated" }} period="7d" />);
  expect(screen.getByText("Est. previous: $100.00 → $120.00")).toBeInTheDocument();
  expect(screen.getByText("+$20.00 (7d)")).toBeInTheDocument();
});

it("shows historical drops with the selected period", () => {
  render(<PriceComparison value={{ previous_price: 100, comparison_price: 50, price_change_amount: -50, comparison_source: "history" }} period="90d" />);
  expect(screen.getByText("Previous: $100.00 → $50.00")).toBeInTheDocument();
  expect(screen.getByText(/\$-50.00 \(90d\)/)).toBeInTheDocument();
  expect(screen.getByText("· Historical prices")).toBeInTheDocument();
});

it("does not turn a missing baseline into zero", () => {
  render(<PriceComparison value={{}} period="30d" />);
  expect(screen.getByText("Previous price unavailable")).toBeInTheDocument();
});
