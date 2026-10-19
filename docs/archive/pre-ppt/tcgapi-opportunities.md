> Historical record, archived before the PPT retirement cutover. Commands and activation claims are superseded by [the current runbook](../../ppt-cutover.md).

# TCG API opportunities for CardboardDex

Reviewed 2026-10-11 against the official documentation and current integration. Recommendations 1/2/3/6/7 from the API review are now implemented locally; see [market-data rollout](market-data.md). Printing/condition holdings, imports, and bulk upgrades remain deferred.

## Highest-value updates

1. **Use explicit sealed-product identity.** The pricing documentation identifies sealed products through `product_type: "Sealed Products"`, shipping categories, and unopened listings. The current sealed service infers candidates from missing rarity and product names. Verify stored provider payloads and ingest these explicit identifiers to reduce false matches. Any Cards/Sets schema changes require approval.
2. **Show the age of the price itself.** `market_price_as_of` dates the underlying market value, while `last_updated_at` describes the provider check. A recently checked product can still have an old price. Surface both appropriately rather than implying every refreshed result has a fresh valuation.
3. **Keep printing-specific values separate.** Normal, Holofoil, Reverse Holofoil, and edition variants have distinct prices. Preserve the selected variant through card details, binder holdings, and valuation.

These fields and the sealed-only top-movers filter are documented in the [Prices API](https://tcgapi.dev/api/prices/). Its 24h/7d/30d changes are percentages, with null indicating insufficient data; they do not establish future ROI or returns against a user's purchase price.

## Efficiency and collection features

- Extend the existing bulk-price integration to bulk history and collection import resolution where supported. The docs describe TCGPlayer-ID/name resolution and batch price/history access. Check the actual subscription first: resolve starts at Starter, while other bulk endpoints require Pro or Business. Local context already records a past bulk-pricing tier restriction. See the [Bulk API](https://tcgapi.dev/api/bulk/).
- Use game/set counts and synchronization timestamps for an admin catalog-coverage view and new-set discovery. Set release dates support age grouping, but do not prove that a product is out of print. Follow pagination rather than hardcoding counts. See the [Games API](https://tcgapi.dev/api/games/).

Start with explicit product identity and price freshness. Expand to multiple games only after reviewing the Pokémon-specific navigation and data assumptions. The Games and Prices documentation describe different update schedules, so use actual timestamps rather than treating either schedule as a guaranteed freshness promise.
