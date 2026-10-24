import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { EmptyState } from "@/components/ui/empty-state";

afterEach(cleanup);

it("announces unavailable data and offers retry and reset", () => {
  const retry = vi.fn(), reset = vi.fn();
  render(<EmptyState role="alert" variant="unavailable" title="Could not load" onRetry={retry} onReset={reset} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Could not load");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  fireEvent.click(screen.getByRole("button", { name: "Reset Filters" }));
  expect(retry).toHaveBeenCalledOnce();
  expect(reset).toHaveBeenCalledOnce();
});

it("compact boxes drop the tall page minimum", () => {
  const { container } = render(<EmptyState compact title="Nothing yet" />);
  expect(container.firstChild).not.toHaveClass("min-h-[320px]");
});
