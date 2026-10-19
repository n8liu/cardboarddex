# CardboardDex project context

## Current handoff — 2026-10-19

The local implementation retires tcgapi.dev and migrates active catalog/pricing work to Pokémon Price Tracker (**PPT**). Direct eBay asking-listing comparisons remain. No production deployment, provider activation, database migration or credential change has been performed by this implementation. Preserve unrelated work and do not infer deployment from local code or test success.

Latest recorded production evidence (October 18, not reverified today): release `8cb6301`, migrations confirmed through `0010_ppt_query_indexes`, PPT public visibility disabled, worker/Beat stopped under the ingestion pause. Live Comps totals recovered through the isolated maintenance timer. The last supplied smoke suite still had a 15-second Trending timeout. The source/rollback host remains retained; deletion is not authorized. Detailed chronological evidence is preserved in [the archived context](docs/archive/pre-ppt/PROJECT_CONTEXT.md).

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
