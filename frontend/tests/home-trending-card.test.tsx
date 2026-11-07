import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HomeTrendingCard } from "@/components/home-trending-card";
import { getTrendingDashboard } from "@/lib/api";
import type { TrendingCardItem } from "@/types/card";

vi.mock("@/components/ui/holo-card", () => ({
  HoloCard: ({ children }: { children: React.ReactNode }) => <div data-testid="holo-card">{children}</div>,
}));

vi.mock("@/lib/api", () => ({
  getTrendingDashboard: vi.fn(),
  cardImageUrl: (s: string) => s,
}));

function mockCard(partial: Partial<TrendingCardItem>): TrendingCardItem {
  return {
    rank: 1,
    card_id: "test-card",
    name: "Test Card",
    set_name: "Test Set",
    set_id: "test-set",
    number: "001",
    rarity: "Rare",
    image_url: "https://img.test/card.jpg",
    clicks_count: 10,
    trend_score: 50,
    trend_direction: "up",
    ...partial,
  };
}

beforeEach(() => {
  vi.mocked(getTrendingDashboard).mockReset();
});

afterEach(cleanup);

it("filters out sealed products and cards without valid images", async () => {
  const cards: TrendingCardItem[] = [
    mockCard({ card_id: "sealed-1", name: "151 Booster Box", rarity: null, image_url: "https://img.test/box.jpg" }),
    mockCard({ card_id: "sealed-2", name: "Elite Trainer Box", rarity: "None", image_url: "https://img.test/etb.jpg" }),
    mockCard({ card_id: "no-img-1", name: "Card No Image", rarity: "Rare", image_url: "" }),
    mockCard({ card_id: "placeholder-1", name: "Card Placeholder", rarity: "Rare", image_url: "https://images.cardboarddex.app/placeholder.svg" }),
    mockCard({ card_id: "pending-1", name: "Card Pending", rarity: "Rare", image_url: "/image-pending.svg" }),
    mockCard({ card_id: "valid-card", name: "Charizard", rarity: "Rare Holo", image_url: "https://img.test/charizard.jpg" }),
  ];

  vi.mocked(getTrendingDashboard).mockResolvedValue({
    timeframe: "7d",
    trending_cards: cards,
    trending_pokemon: [],
    volume_pokemon: [],
    total_volume_usd: 0,
    total_sales_count: 0,
    updated_at: "2026-10-26",
  });

  render(<HomeTrendingCard />);

  // Should only pick the valid card
  const img = await screen.findByRole("img");
  expect(img).toHaveAttribute("alt", "Charizard");
  expect(img.getAttribute("src")).toContain("charizard.jpg");
});

it("cycles to the next valid candidate if current card image triggers onError", async () => {
  const cards: TrendingCardItem[] = [
    mockCard({ card_id: "card-1", name: "First Card", rarity: "Rare", image_url: "https://img.test/broken.jpg" }),
    mockCard({ card_id: "card-2", name: "Second Card", rarity: "Rare", image_url: "https://img.test/working.jpg" }),
  ];

  // Prevent random shuffle from changing order in this test
  vi.spyOn(Math, "random").mockReturnValue(0.99);

  vi.mocked(getTrendingDashboard).mockResolvedValue({
    timeframe: "7d",
    trending_cards: cards,
    trending_pokemon: [],
    volume_pokemon: [],
    total_volume_usd: 0,
    total_sales_count: 0,
    updated_at: "2026-10-26",
  });

  render(<HomeTrendingCard />);

  const img = await screen.findByRole("img");
  const initialAlt = img.getAttribute("alt");

  // Trigger error on image load
  fireEvent.error(img);

  await waitFor(() => {
    const updatedImg = screen.getByRole("img");
    expect(updatedImg.getAttribute("alt")).not.toBe(initialAlt);
  });

  vi.spyOn(Math, "random").mockRestore();
});

it("shows retry button when no valid card candidates exist", async () => {
  const cards: TrendingCardItem[] = [
    mockCard({ card_id: "box-1", name: "Scarlet & Violet Booster Box", rarity: null, image_url: "https://img.test/box.jpg" }),
  ];

  vi.mocked(getTrendingDashboard).mockResolvedValue({
    timeframe: "7d",
    trending_cards: cards,
    trending_pokemon: [],
    volume_pokemon: [],
    total_volume_usd: 0,
    total_sales_count: 0,
    updated_at: "2026-10-26",
  });

  render(<HomeTrendingCard />);

  expect(await screen.findByRole("button", { name: "Retry artwork" })).toBeInTheDocument();
});
