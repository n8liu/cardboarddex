> Historical record, archived before the PPT retirement cutover. Commands and activation claims are superseded by [the current runbook](../../ppt-cutover.md).

# Provider history, sales activity, and catalog coverage

Implemented locally; deployment and provider population are separate steps. No Cards or Sets columns, indexes, constraints, or existing migrations change. Printing/condition selection, collection imports, and bulk API upgrades are not part of this release.

## What ships

- Sealed rankings support 30/90-day comparisons. Explicit `product_type` in retained TCG API metadata overrides the old missing-rarity fallback. Both direct and nested card payload shapes work, and price-only syncs preserve the metadata.
- Price dates use `market_price_as_of`. The provider check timestamp is displayed separately. Dates over seven days old are marked stale; absent or invalid price dates remain unknown.
- Sealed rows and card details show cached historical price charts, actual coverage, and an optional purchase-cost return calculation. That estimate is unrealized, before selling fees/taxes, and uses the current displayed price; it is not a forecast. Costs are entered in USD and are not persisted.
- History returns require positive starting/ending prices exactly the selected number of calendar days apart, with an ending price no more than seven days old. There is no historical backfill from current prices. The 30-day sealed ranking can fall back to the provider's reported 30-day change; 90-day rankings cannot substitute weekly or monthly changes. Missing returns sort last.
- The Trending UI uses provider-reported sales counts from cached history, grouped by product across printings. Repeated syncs update the same product/printing/day instead of counting another sale. Null sales remain unknown; zero is a recorded zero. Data covers synced products only; recent 1–3 days may have delayed sales fields. Legacy observation-volume endpoints remain compatible, but the new dashboard opts out of computing those aggregates.
- The authenticated admin dashboard has an expandable catalog coverage panel. It compares paginated provider snapshots with local products, lists missing sets, and links imported recent sets back to the catalog. Discovery never imports catalog rows automatically.

## Rollout

1. Back up the database and validate the backup using the existing deployment runbook.
2. Apply `backend/alembic/versions/0007_market_data.py` using the new backend release (`alembic upgrade head`). It creates only `market_history` and `catalog_snapshots`. The history sync status uses the existing provider-state table under provider `tcgapi_history`.
3. Deploy the new backend before the frontend. New reads require those tables even when automated history ingestion is disabled.
4. Run a bounded provider pilot with the intended server-side credentials and inspect results:

   ```bash
   # From backend/, in the intended environment; consumes provider quota.
   .venv/bin/python -m jobs.sync_market_data --card-id CARD_ID --limit 1
   # Discover English/Japanese sets and refresh up to five products.
   .venv/bin/python -m jobs.sync_market_data --discover --limit 5
   ```

5. Verify `/cards/CARD_ID/market-history?days=30`, `/cards/sealed-signals?era=newer&period=90`, `/market/sales-activity?days=30`, and authenticated `/admin/catalog-health`. Confirm zero versus unknown, date coverage, and price dates with the provider response.
6. Only when host capacity permits, opt in with `MARKET_HISTORY_ENABLED=true` and reload worker/Beat configuration. The default is false. The opt-in schedule refreshes up to five oldest/unsynced products hourly and refreshes catalog discovery daily. Do not remove the production ingestion pause marker or start another scheduler merely to enable this feature.

There were no paid provider calls, production migrations, deployments, or ingestion restarts during implementation. Subscription access has not been verified live. The history endpoint requests one year, but the provider applies the subscription's available window. Authentication/tier/rate/server failures stop the batch; invalid individual responses are logged and reported as failures without erasing prior history. Successful rows are retained for 372 days. Run one history collector at a time; use targeted IDs for products that need early coverage.

Public page loads read the database and never call the provider. Sealed charts use one page-scoped history query; ranking reads bounded baseline windows. Source freshness and synchronization timestamps remain visible rather than being replaced by page request time.

## Sources

- [TCG API history and card fields](https://tcgapi.dev/api/cards/)
- [Price freshness and percentage semantics](https://tcgapi.dev/api/prices/)
- [Game/set discovery](https://tcgapi.dev/api/games/)
