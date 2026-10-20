# CardboardDex project context

## Current handoff — 2026-10-19

The implementation retires tcgapi.dev and migrates active catalog/pricing work to Pokémon Price Tracker (**PPT**). Direct eBay asking-listing comparisons remain. Distinguish local fixes from the deployed release.

User-supplied production evidence (October 19): release `55c4ad9e92ed876036c3019c929b7baa230f0042`, backend image digest `4efb69d243958cf0cd856e81318e8e04c96f4b29c3fbabe764344ae8018582eb`, deployed successfully with schema `0012_market_history_transitions`. Projection backfill/verification covered 54,996 cards with no mismatches. Transition seeding processed 933 products; the before/after preservation audit passed at `/var/lib/cardboarddex/ppt-cutover-20261019T190118Z`. Deployment readiness and search probes passed; this is not full performance or stability validation.

Later on October 19, ingestion was resumed and at 19:24 UTC `jobs.sync_ppt` repeatedly timed out while ranking the weekly priority pool inline, before making any provider requests. Fixes since then, all deployed as release `3c54983` with `PPT_INGESTION_ENABLED=true` and `PPT_PRIMARY_ENABLED=true`:

- **Ranking decoupled from sync (`09c57ff`, `3c54983`).** `jobs.sync_ppt.build_priority_pool` runs on its own Beat schedule (every 900s, 240s time limit, Redis lease, 120s statement timeout) and writes checkpoint `priority:<monday>`. `sync_ppt` never ranks: it uses this week's pool, falls back to the latest earlier pool with a warning, or rotates with no priority lane. Ranking uses the verified v2 projection (current selected USD positive prices) when available.
- **Trending served from a worker snapshot (`7214f7a`).** `jobs.refresh_trending` publishes `cardboarddex:{ppt|legacy}:trending-snapshot:v1` every 60s under a lease (about 8.5s on the host). Public `/cards/trending` without `q` never computes: a missing or stale (>30 min) snapshot returns 503 with `Retry-After: 60`. Image URLs are resolved at read time. `release.sh` seeds it in a worker-budget `run` container (non-fatal). While paused, the host `cardboarddex-live-stats.service` also publishes Trending and must be reinstalled from the release.
- **Unified history (`69df9f6`).** Only seeded PPT continuations count as legacy-prefix candidates.
- **Live Comps** polls every 15s and prepends newly ingested rows (frontend test added). PPT feed rows appear only when price or `price_date` changes, at most one fetch per product per UTC day.

Production evidence at 01:03 UTC on October 20: worker and Beat running, `sync_ppt` completing 8 requests per run (from fallback pool `priority:2026-10-12`), new PPT feed rows with `price_date` 2026-10-19, live stats `total_ppt_updates` 1,584, and Trending refreshed. Open checks:

- Confirm `/opt/cardboarddex/ingestion.paused` was actually removed. The `rm` prompt may have declined it, and if it is still present the next release leaves worker/Beat stopped.
- One live-stats refresh hit the 5s statement timeout as ingestion started. If it repeats under write load, optimize the count query rather than raising the deadline.
- Confirm `PPT priority pool built key=priority:2026-10-19` (or diagnose a build failure) and its duration on production-sized PostgreSQL.
- Confirm eBay collection resumed producing rows (the last seen was 19:23 UTC on October 19), and that host memory stays above about 150 MB available.
- The installed host monitor still reports legacy TCGAPI coverage and needs its separately installed script updated.

The source/rollback host remains retained; deletion is not authorized. Earlier chronological evidence is in [the archived context](docs/archive/pre-ppt/PROJECT_CONTEXT.md).

## Local uncommitted changes — 2026-10-20

These are on `main` in the working tree only. They are not committed or deployed.

- **Card page.** The "Historical performance" panel (`MarketHistoryPanel`, `getMarketHistory`) is removed. The price chart defaults to 3M, has printing toggles (on by default) and PSA/CGC/TAG toggles (off by default; PSA also controls the eBay PSA 10/9 lines). Lines are step lines that carry the last recorded value forward through today, display-only (`carryForward` in `frontend/lib/provider-history.ts`); the tooltip shows "since <date>" for carried values.
- **Catalog.** `getCardSets` always sends `game` (the backend defaults to English only), so Japanese sets appear in the catalog and search autocomplete. The price slider is a continuous log scale from $0 to $5,000+ that commits on release.
- **Trending and Graded Sales.** Full views are tile grids. Graded Sales drops per-grade counts.
- **Dev-only Trending fallback.** `TRENDING_ON_DEMAND_FALLBACK` (default false) lets `get_trending_dashboard` compute the snapshot once when it is missing, for local runs without a worker. Never enable it in production. `backend/tests/conftest.py` forces it off in tests.
- **UI.** Nav is centered when zoomed. Card hover is shared (`frontend/lib/card-hover.ts`: tile lift plus at most a 2% image zoom) so images are no longer clipped.

Open items:

- TAG grades never ingest: `backend/app/services/ppt_ingestion.py` accepts only psa/cgc/bgs/sgc, so the TAG toggle is always disabled. BGS/SGC have data but no toggle.
- Grading-profit shows bogus eBay asking prices (e.g. a $17.5M PSA 10); no outlier cap yet.
- Five Trending tests fail when a local Redis is running (pre-existing; they pass in CI).
- Locally, Trending needs a seeded snapshot (`python -m jobs.refresh_trending`) or the fallback flag, graded sales need `ppt_products`, and grading-profit needs `listing_assessments` (`python -m jobs.check_listing_images`, stored data only).

## Implemented migration

- Active provider: PPT, with separate ingestion/public visibility gates, 20,000 daily credits and 55 weighted credits/minute. Scheduled and manual refresh share validation, quotas and ingestion. Retired client and queued task names are inert even if an old legacy flag is true.
- Data preservation: existing card/set IDs and schemas, price observations, daily history, provider state and image keys stay intact. Additive migration `0012_market_history_transitions` follows `0011_catalog_prices`. No bulk rename of stored provenance. Legacy field/index/task identifiers remain only for history and compatibility.
- Price charts: unified “Market price” continuation after an explicit per-series cutover. Earlier recorded values remain; the card chart uses one PPT continuation view rather than a separate backfill toggle. Printing, condition, currency, language and metric must match. An unknown-condition legacy prefix joins a unique matching PPT series with point-level condition metadata; ambiguous or conflicting history stays separate. Missing dates stay missing in the data; the chart draws step lines that hold the last recorded value through today (display-only).
- Price selection: matched PPT raw prices preferred when enabled; last-known prices retain source dates/stale status. Unmapped cards retain legacy values. Missing recent graded medians remain unavailable. Catalog projection version 2 requires backfill and verification.
- Trending: PPT graded sales activity replaces the retired sales-period panel. `salesByGrade` counts rank synced cards; no fixed window, dollar volume or raw-sales total is inferred. Partial raw refreshes preserve graded snapshot freshness independently. The default dashboard is a worker-published snapshot; only search (`q`) computes on request, under the five-second deadline.
- Consumers: catalog/home, movers, sealed, binder, Live Comps, provider coverage, images, diagnostics and active copy use PPT-aware behavior. Direct eBay remains asking-price evidence with existing title/image checks.
- Operations: explicit transition seeding, read-only preservation receipts, versioned caches and bounded PPT health publication. No public read triggers provider ingestion or creates a transition.

## Validation and release requirements

Local validation: 366 backend tests passed (30 skipped), all 153 frontend tests passed, TypeScript checks and the production frontend build passed, and `git diff --check` passed. Skipped infrastructure checks still need their configured disposable services. Isolated SQLite/unit checks are not production-sized PostgreSQL, public HTTP, browser-device or stability evidence. These counts predate the Trending snapshot, priority-pool and Live Comps polling tests added since. With the uncommitted October 20 changes: 384 backend passed (30 skipped), 162 frontend passed, TypeScript clean; no production build or browser check was run. Run backend tests with `PPT_PRIMARY_ENABLED=false MARKET_HISTORY_ENABLED=false` to match CI, because the local `backend/.env` enables both.

Follow [docs/ppt-cutover.md](docs/ppt-cutover.md): restore backups off-host, audit identities/history, rehearse migrations, rebuild/verify projection v2, seed transitions, validate private PPT-on reads, then deploy visibility separately from any ingestion resumption. Keep the SQL five-second and public smoke 15-second deadlines unchanged. Production-sized performance, actual mapping coverage, bounded authenticated refresh and the 48-hour observation remain release checks.

Never run an extra Python process inside the 160 MiB serving API container. The earlier `docker exec` seed caused an OOM. Use the isolated worker-budget maintenance container and the existing deployment lock. Ingestion is now resumed. `/opt/cardboarddex/ingestion.paused` makes `release.sh` skip worker/Beat, so only recreate it to deliberately pause. Preserve quota/checkpoint Redis state and the existing rollback host.

## References

- [Architecture](ARCHITECTURE.md), [PPT contract](docs/pokemon-price-tracker.md), [cutover runbook](docs/ppt-cutover.md)
- [Projection](docs/catalog-price-projection.md), [performance](docs/performance.md), [eBay quality](docs/ebay-listing-quality.md)
- [Pre-migration context and operational evidence](docs/archive/pre-ppt/PROJECT_CONTEXT.md)
