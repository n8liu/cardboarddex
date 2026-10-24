import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CardLink } from "@/components/card-link";

vi.mock("next/link", () => ({
  default: ({ prefetch, children, ...props }: { prefetch?: boolean | null; children: React.ReactNode }) =>
    <a data-prefetch={String(prefetch)} {...props}>{children}</a>,
}));
afterEach(cleanup);

it.each(["mouseEnter", "focus", "touchStart"] as const)("prefetches only after %s and keeps caller handlers", (event) => {
  const handler = vi.fn();
  const handlerProp = { mouseEnter: "onMouseEnter", focus: "onFocus", touchStart: "onTouchStart" }[event];
  render(<CardLink href="/cards/base1-4" {...{ [handlerProp]: handler }}>Charizard</CardLink>);
  const link = screen.getByRole("link", { name: "Charizard" });
  expect(link).toHaveAttribute("data-prefetch", "false");
  fireEvent[event](link);
  expect(link).toHaveAttribute("data-prefetch", "null");
  expect(handler).toHaveBeenCalledTimes(1);
});
