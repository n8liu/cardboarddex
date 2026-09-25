import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
vi.mock("next/image", () => ({ default: ({ unoptimized, ...props }: {unoptimized?: boolean}) => <img data-direct={String(unoptimized)} {...props} /> }));
import CardImage, { isDirectCardImage } from "@/components/card-image";

describe("CDN card images", () => {
  it("recognizes CDN and legacy card routes only", () => {
    expect(isDirectCardImage("https://images.cardboarddex.app/cards/a/x.png")).toBe(true);
    expect(isDirectCardImage("https://api.cardboarddex.app/cards/a/image")).toBe(true);
    expect(isDirectCardImage("https://evil.invalid/cards/a/image")).toBe(false);
  });
  it("bypasses optimization and falls back locally without an API retry", () => {
    const { getByAltText, rerender } = render(<CardImage src="https://images.cardboarddex.app/cards/a/x.png" alt="Card" width={40} height={56} />);
    const image = getByAltText("Card");
    expect(image.getAttribute("data-direct")).toBe("true");
    fireEvent.error(image);
    expect(image.getAttribute("src")).toBe("/image-pending.svg");
    rerender(<CardImage src="https://images.cardboarddex.app/cards/b/y.png" alt="Card" width={40} height={56} />);
    expect(image.getAttribute("src")).toContain("cards/b/y.png");
  });
});
