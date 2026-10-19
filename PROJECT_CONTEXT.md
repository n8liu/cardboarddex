# CardboardDex project context

## Current handoff — 2026-10-19

The implementation retires tcgapi.dev and migrates active catalog/pricing work to Pokémon Price Tracker (**PPT**). Direct eBay asking-listing comparisons remain. Distinguish local fixes from the deployed release.

User-supplied production evidence (October 19): release `55c4ad9e92ed876036c3019c929b7baa230f0042`, backend image digest `4efb69d243958cf0cd856e81318e8e04c96f4b29c3fbabe764344ae8018582eb`, deployed successfully with schema `0012_market_history_transitions`. Projection backfill/verification covered 54,996 cards with no mismatches. Transition seeding processed 933 products; the before/after preservation audit passed at `/var/lib/cardboarddex/ppt-cutover-20261019T190118Z`. Deployment readiness and search probes passed; this is not full performance or stability validation.

Ingestion was resumed, but at 19:24 UTC `jobs.sync_ppt` repeatedly timed out while building the weekly priority pool through `rank_priority`, before reaching provider requests in those tasks. Live stats and PPT report publication succeeded. The installed host monitor still reports legacy TCGAPI coverage and needs its separately installed script updated. Re-pausing worker/Beat was requested; execution is not yet confirmed. The local ranking fix uses the verified v2 current-price projection independently of the public-read flag; deployments without a verified projection retain the historical fallback. Projected ranking uses current selected USD positive prices, without resurrecting older positive prices when the current quote is zero or non-USD. This fix is not deployed or benchmarked on production-sized PostgreSQL yet.

The last supplied full smoke suite still had a 15-second Trending timeout. The source/rollback host remains retained; deletion is not authorized. Earlier chronological evidence is in [the archived context](docs/archive/pre-ppt/PROJECT_CONTEXT.md).

## Implemented migration

- Active provider: PPT, with separate ingestion/public visibility gates, 20,000 daily credits and 55 weighted credits/minute. Scheduled and manual refresh share validation, quotas and ingestion. Retired client and queued task names are inert even if an old legacy flag is true.
- Data preservation: existing card/set IDs and schemas, price observations, daily history, provider state and image keys stay intact. Additive migration `0012_market_history_transitions` follows `0011_catalog_prices`. No bulk rename of stored provenance. Legacy field/index/task identifiers remain only for history and compatibility.
- Price charts: unified “Market price” continuation after an explicit per-series cutover. Earlier recorded values remain; separate PPT backfill is available. Printing, condition, currency, language and metric must match. Unknown condition remains separate. Missing dates stay missing.
- Price selection: matched PPT raw prices preferred when enabled; last-known prices retain source dates/stale status. Unmapped cards retain legacy values. Missing recent graded medians remain unavailable. Catalog projection version 2 requires backfill and verification.
- Trending: PPT graded sales activity replaces the retired sales-period panel. `salesByGrade` counts rank synced cards; no fixed window, dollar volume or raw-sales total is inferred. Partial raw refreshes preserve graded snapshot freshness independently.
- Consumers: catalog/home, movers, sealed, binder, Live Comps, provider coverage, images, diagnostics and active copy use PPT-aware behavior. Direct eBay remains asking-price evidence with existing title/image checks.
- Operations: explicit transition seeding, read-only preservation receipts, versioned caches and bounded PPT health publication. No public read triggers provider ingestion or creates a transition.

## Validation and release requirements

Local validation: 366 backend tests passed (30 skipped), all 153 frontend tests passed, TypeScript checks and the production frontend build passed, and `git diff --check` passed. Skipped infrastructure checks still need their configured disposable services. Isolated SQLite/unit checks are not production-sized PostgreSQL, public HTTP, browser-device or stability evidence.

Follow [docs/ppt-cutover.md](docs/ppt-cutover.md): restore backups off-host, audit identities/history, rehearse migrations, rebuild/verify projection v2, seed transitions, validate private PPT-on reads, then deploy visibility separately from any ingestion resumption. Keep the SQL five-second and public smoke 15-second deadlines unchanged. Production-sized performance, actual mapping coverage, bounded authenticated refresh and the 48-hour observation remain release checks.

Never run an extra Python process inside the 160 MiB serving API container. The earlier `docker exec` seed caused an OOM. Use the isolated worker-budget maintenance container and the existing deployment lock. Keep `/opt/cardboarddex/ingestion.paused` until the rollout checks and explicit operational decision to resume. Preserve quota/checkpoint Redis state and the existing rollback host.

## References

- [Architecture](ARCHITECTURE.md), [PPT contract](docs/pokemon-price-tracker.md), [cutover runbook](docs/ppt-cutover.md)
- [Projection](docs/catalog-price-projection.md), [performance](docs/performance.md), [eBay quality](docs/ebay-listing-quality.md)
- [Pre-migration context and operational evidence](docs/archive/pre-ppt/PROJECT_CONTEXT.md)
