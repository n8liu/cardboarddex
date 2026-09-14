import { describe, it, expect } from "vitest";
import { buildEbaySearchUrl } from "@/components/shop-ebay-button";

describe("buildEbaySearchUrl", () => {
  it("builds an eBay query for a standard card with set name and card number", () => {
    const url = buildEbaySearchUrl({
      name: "Charizard",
      number: "4",
      printed_total: 102,
      set_name: "Base Set",
    });

    expect(url).toContain("https://www.ebay.com/sch/i.html?_nkw=");
    const decoded = decodeURIComponent(url);
    expect(decoded).toBe("https://www.ebay.com/sch/i.html?_nkw=Pokemon Charizard 4/102 Base Set");
  });

  it("does not duplicate 'Pokemon' if already in card name or set name", () => {
    const url = buildEbaySearchUrl({
      name: "Pokémon Breeder",
      number: "76",
      printed_total: 102,
      set_name: "Base Set",
    });

    const decoded = decodeURIComponent(url);
    expect(decoded).toBe("https://www.ebay.com/sch/i.html?_nkw=Pokémon Breeder 76/102 Base Set");
    // Ensure "Pokemon Pokémon" is not created
    expect(decoded).not.toMatch(/Pokemon\s+Pok[eé]mon/i);
  });

  it("omits dummy number markers like '#' or 'N/A' for sealed products", () => {
    const url = buildEbaySearchUrl({
      name: "151 Booster Bundle",
      number: "N/A",
      printed_total: null,
      set_name: "151",
    });

    const decoded = decodeURIComponent(url);
    expect(decoded).toBe("https://www.ebay.com/sch/i.html?_nkw=Pokemon 151 Booster Bundle");
  });

  it("does not duplicate set name if card name already includes it", () => {
    const url = buildEbaySearchUrl({
      name: "Pokemon 151 Booster Box",
      number: null,
      printed_total: null,
      set_name: "151",
    });

    const decoded = decodeURIComponent(url);
    expect(decoded).toBe("https://www.ebay.com/sch/i.html?_nkw=Pokemon 151 Booster Box");
  });
});
