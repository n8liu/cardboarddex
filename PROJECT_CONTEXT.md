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

- ~~Confirm the pause marker was removed~~ and ~~live-stats timeout~~: both happened on October 20; see "Production incidents — 2026-10-20".
- Confirm `PPT priority pool built key=priority:2026-10-19` (or diagnose a build failure) and its duration on production-sized PostgreSQL.
- eBay collection resumed producing rows (19:04 UTC on October 20). Keep host memory above about 150 MB available and iowait under 10%.
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

## Catalog 503 fix — 2026-10-20 (local, not deployed)

Production `/cards/search` returned 503 (`Results temporarily unavailable`) for the default catalog request. Uncached broad price sorts took 4.0–4.6s against the 5s rebuild `statement_timeout`, and `number_asc` exceeded it; each timeout also triggers the 30s failure cooldown. Fix, keeping the deadline unchanged:

- Migration `0013_catalog_price_selected` adds `catalog_price_candidates.selected`, which marks each card's PPT-primary price (computed on write by `mark_selected`, backfilled by the migration), plus partial index `ix_catalog_price_selected(price)`. `Cards`/`Sets` are untouched.
- Broad price sorts read priced cards in index order, then unpriced cards by name (`NOT EXISTS`). Number/set sorts pick the page before looking up prices. `search_cards` serves stale results for up to 30 minutes (was 5).
- Synthetic 55k-card PostgreSQL 17 with production memory settings: default catalog 71→2ms, `number_asc` 215→38ms; results identical to the old code in all nine cases. The deepest price page is slower (106→174ms). Production still needs an `EXPLAIN (ANALYZE, BUFFERS)` check.
- Deploy: stop worker/Beat **before** `alembic upgrade head` (the backfill assumes no concurrent candidate writes), then run `python -m jobs.catalog_prices verify` (or `repair`) in the worker-budget container before releasing. Confirm `CATALOG_CURRENT_PRICES_ENABLED=true` in production; the legacy path barely speeds up.

## PPT daily pacing — 2026-10-21 (local, not deployed)

Production Live Comps stopped receiving PPT rows after about 8,000 calls each day. Suspected cause (from code; production confirmation pending): each refresh costs 2–3 credits, so 20,000 credits is about 8,000 requests. The 15s Beat at 8 per batch (about 32 a minute, under the 55 weight limit) spends them by about 04:00 UTC, then every reservation is `PPTBlocked("daily")` until 00:00 UTC, which `sync_ppt` swallowed silently.

- `PPTQuota.reserve` now also enforces `pacing_allowance` atomically in the Lua reservation: daytime cap × elapsed/22h + one hour of burst. Returns `paced`. Retry and ≥22:00 UTC are unpaced; the hard cap still reports `daily`. `PPT_DAILY_PACING_ENABLED=false` restores the old behavior.
- `sync_ppt` logs `PPT batch yielded reason=… lane=…` and returns `blocked`; the health report adds `quota.pacing_allowance`.
- Before deploying, confirm on the host: Redis `cardboarddex:ppt:v1:credits:<epoch//86400>` near 19,500–20,000 early in the UTC day, and PPT `price_observations` per hour dropping to zero after the first hours. After deploying, PPT rows should arrive in all 24 hours.

**Actual production stop (confirmed October 22, 05:46 UTC):** the ingestion monitor paused ingestion again at 01:55:03 UTC on October 21 ("Memory/swap/I/O pressure persisted for five minutes"). Worker and Beat had been `Exited` for 28 hours, and Redis had no PPT counters for day 20748. Memory (178–287 MB available) and swap (<0.7 MiB/s) were fine and the API was healthy; iowait sat at 9.3–11.8% (limit 10%, `monitor_ingestion.py:35`) and peaked at 15.0%. The 10% iowait threshold trips on this host's normal load.

Fix (local, not deployed):
- `monitor_ingestion.py`: memory/swap keep the five-minute rule; iowait now pauses only above 25% for 15 minutes (`iowait_since` in `latest.json`). The monitor runs from `/opt/cardboarddex/operations/scripts/lightsail/` and must be reinstalled there; a release does not update it.
- `live_stats.py`: retired-provider (tcgapi) totals are counted once a day (`cardboarddex:live_stats:legacy:v1` in the cache Redis, 24h TTL, 15s statement timeout). Each minute only PPT (exact provider match) and matched eBay rows are recounted, with the same totals.

## Production incidents — 2026-10-20

- **Worker left stopped after release `16edaa2`.** `/opt/cardboarddex/ingestion.paused` (from Oct 19) was never removed, so `release.sh` stopped worker/Beat and skipped restarting them. Restarting by hand needs `export BACKEND_IMAGE=$(cat $r/image.txt)` first; the stale `app.env` image fails with ECR "pull access denied" (see `scripts/lightsail/recover_services.sh`). eBay resumed at 19:04 UTC.
- **PPT due products not syncing is by design.** All 92 due products had `failures > 0`; only the retry lane takes them, and it was full (500/500). Lanes may borrow up to the daily cap after 22:00 UTC, and they reset at 00:00 UTC. `PPTBlocked("lane")` is swallowed without logging in the `jobs/sync_ppt.py` loop.
- **Live stats timed out.** `refresh_live_stats` hit the 5s statement timeout every minute from about 18:57 UTC, and `/cards/live-updates/stats` returned 503 from about 19:27. `EXPLAIN (ANALYZE, BUFFERS)`: 5.66s, almost all in the index-only scan of `ix_price_observations_provider_feed`, with 59,069 heap fetches and 15,319 blocks read from disk. `price_observations` (insert-only, about 400k rows) had not been vacuumed since Oct 16, so the visibility map was stale. PostgreSQL 16 triggers an insert-only vacuum only after about 20% growth. Fixed by `VACUUM (ANALYZE) price_observations` plus `cards` (0.99s; prod `psql` sessions need `SET statement_timeout = 0` first, because the server default is 12s). A manual refresh in the worker-budget container then published a fresh snapshot.
- **Monitor re-paused ingestion at 19:16 UTC** for "Memory/swap/I/O pressure persisted for five minutes". Memory was fine (180–300 MB available) and swap-in was under 1 MiB/s; iowait stayed at 12–18% (limit 10%), consistent with the live-stats scan reading about 120 MB per minute. A pause recreates the marker, sets worker/Beat to `--restart no` and stops them. Resume with `rm` of the marker, `$C up -d --no-deps celery-worker celery-beat`, then `docker update --restart unless-stopped app-celery-worker-1 app-celery-beat-1`. Worker/Beat were restarted after the vacuum. Live-stats publishing and iowait under the restarted worker are not yet confirmed. The reason for a pause is logged once in the `cardboarddex-ingestion-monitor` journal and saved in `/var/lib/cardboarddex/ingestion-monitor/latest.json`.
- The host `cardboarddex-live-stats.timer` was disabled (it only publishes while paused); the README requires reinstalling it from the release.

Open items:

- ~~Confirm `ALTER TABLE price_observations SET (autovacuum_vacuum_insert_*)`~~: confirmed applied on October 23. Autovacuum ran at 02:51 UTC with 4,035 inserts pending, so the visibility map was current. Live stats at 4.5–5.5s on 431k rows comes from growth and contention, not vacuum lag.
- Durable live-stats fix (needs a plan first): stop recounting all observations every minute. The tcgapi total is frozen at 347,454, so count it once and add only new PPT/eBay rows.
- If iowait stays above 10% after the vacuum, find the next heavy reader (Trending refresh about 8.5s, PPT/eBay jobs) with `pg_stat_statements` or per-task timings.
- The catalog 503 fix above is still local and not deployed.

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
- [Fixes and pitfalls](docs/fixes-and-pitfalls.md): incident causes, recovery steps and errors to avoid
- [Pre-migration context and operational evidence](docs/archive/pre-ppt/PROJECT_CONTEXT.md)
