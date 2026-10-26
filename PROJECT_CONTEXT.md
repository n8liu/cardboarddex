# CardboardDex project context

## Integrated market snapshots and final fixes — 2026-10-26 (local, uncommitted, not deployed)

Integrated the source changes from `fix-movers-snapshot` commits `4a91076` and `2492f18` into the existing Phase 1–3 checkout. This is a source integration, not a Git merge/commit. The separate worktree is untouched. Existing frontend motion edits are preserved. No migrations or Cards/Sets changes.

- Movers, Sealed and Grading Profit publish shared snapshots every twelve hours; Beat checks every fifteen minutes and repairs missing snapshots. Retention is thirty-six hours. Movers/Grading reads filter stored rankings without rebuilding SQL; Sealed still reads bounded page history.
- Production Redis outages return retryable, non-cacheable 503s. Only `MARKET_SNAPSHOTS_ON_DEMAND_FALLBACK=true` opts local development into on-request computation when Redis is unreachable. Keep it false in production.
- The grading publisher retains Phase 1's robust asking median/outlier cap, excludes asks older than thirty days and batches cards to bound ORM memory. Its `grading-identity-v2` namespace cannot reuse snapshots created without those safeguards.
- Snapshot publication checks lease ownership; failed builds preserve earlier data. Seed commands report failures through their exit status. The release seeds all three snapshots in an isolated worker-budget container.
- Added a separate paused-ingestion market snapshot service/timer. It makes no provider calls and does not start workers. Both paused-mode scripts share a maintenance mutex to prevent concurrent containers. Install it explicitly using `scripts/lightsail/README.md`; it does not replace the existing short Live Comps maintenance timer.
- Price-dashboard deduplication and React row keys now share provider/variant/printing/condition/grade/currency identity, preserving multiple variants with one provider card ID.
- Added tracked `OPERATIONS.md` and repaired root documentation links. Local `docs/` stays ignored intentionally. Reconciled obsolete TAG/outlier and ingestion-status notes.

Validation: backend 431 passed (30 infrastructure/live checks skipped); frontend 183 passed; TypeScript and production build passed; release/maintenance tests 14 passed; Python compilation, shell syntax and `git diff --check` passed. Chrome checked compare search/card selection, a 390px comparison chart, mobile card navigation/sticky actions and timeframe changes against the existing configured API. Full Movers browser navigation timed out, so this is partial browser coverage. Docker is unavailable locally, blocking container-based PostgreSQL performance/integration checks. Remaining release work: production-sized PostgreSQL refresh duration/memory, live worker/Beat and ingestion verification, installing the maintenance timer, Cloudflare Cache Rule activation, and deployment. No production or Cloudflare changes were made in this integration.

## Motion pass — 2026-10-26 (branch `phase3-ui-polish`, uncommitted, not deployed)

Frontend only, no new dependencies. Every effect is off under `prefers-reduced-motion`.

- **Card page reveal.** The card details fade and rise 8px (220ms) when they arrive (`<ViewTransition enter="card-reveal" default="none">` in `app/cards/[id]/page.tsx`). The rest of the page swaps instantly: the root crossfade is disabled in `globals.css`. A shared tile→hero image morph was dropped: the route is `force-dynamic` with `loading.tsx` and hover prefetch only loads the loading shell, so the pair never forms. It would need full prefetch (`prefetch={true}`) per hover.
- **Chart.** `PriceHistoryChart` lines draw once on mount (`isAnimationActive="auto"`, then `false`), so range and series toggles no longer replay the draw.
- **Live Comps.** Rows a background poll prepends get a single emerald tint (`.animate-fresh-row`, cleared after 1.5s). Feed items carry no previous price, so the tint has no up/down colour.
- **Pulsing dots.** `animate-ping` remains only on the Live Comps auto-refresh indicator. Loading badges and headers use a static dot; the autocomplete "Searching" dot uses `animate-pulse`.

Validation: frontend 182 passed; typecheck and build passed. Not checked in a real browser.

## Interface polish — 2026-10-24 (branch `phase3-ui-polish`, stacked on Phase 2, not deployed)

Frontend only.

- **Command palette.** Sets are searchable (loaded once on first open). Binder actions: add the current card, or open the binder. The results are an ARIA combobox/listbox. The nav shows "Ctrl K" off Apple platforms (`lib/shortcut.ts`).
- **URL filters.** `lib/url-state.writeUrlFilters` pushes a history entry for discrete filter changes and replaces it while typing, so Back restores the previous filters in catalog, movers (now including `layout`), sealed and grading profit. Pagination is load-more, so `page` stays out of the URL.
- **Mobile card page.** Chart toggles scroll in one row on phones. Range buttons show 1M/3M/6M/1Y below `sm` but keep their full accessible names. `StickyCardActions` adds a bottom bar (price, eBay, binder) once the hero actions scroll away.
- **Compare view.** `/compare?ids=a,b` (up to 4) has a card picker, one primary-market line per card (`primaryMarketSeries`), and % change (`indexToFirstValue`) or price. `PriceHistoryChart` takes an optional `formatValue`. Linked from card pages, the palette and the sitemap.
- **Empty states.** `EmptyState` gains `variant` (empty/unavailable/collecting), `compact`, `onRetry` and `role`. It is used in movers, sealed, Trending (including its error state), graded sales and the catalog grid.

Validation: frontend 181 passed; typecheck and build passed. `next start` served `/compare` and the card page's Compare link and sticky bar. Not checked in a real browser or on a device.

## Speed and SEO changes — 2026-10-24 (branch `phase2-speed-seo`, stacked on Phase 1, not deployed)

- **Edge-cacheable API reads.** `response_cache.cdn_cache_control` sends `public, max-age=0, s-maxage=<seconds left fresh>, stale-while-revalidate=<until discard>`. Stale entries get `s-maxage=10`, and response-cache 503s are `no-store`. `/cards/{id}/prices` uses `s-maxage=120, swr=600`, and `/cards/live-updates/stats` uses `s-maxage=30` (10 when stale). The frontend no longer forces `no-store` for `getCard`/`getCardPricing`. **Takes effect only after the Cloudflare Cache Rule in the README "Edge caching" section is created by hand.**
- **Card-page metadata.** `generateMetadata` (title, description, canonical, OG/Twitter with the card image) shares one `getCard` read with the page via React `cache()`. The root layout sets `metadataBase` (`https://cardboarddex.app`). New `robots.ts` and a request-time `sitemap.ts` (pages, guides, Pokédex, and sets from `/cards/sets`; about 1,500 URLs; no individual cards).
- **Hover prefetch.** `components/card-link.tsx` prefetches card pages only on hover, focus or touch (the documented Next pattern) and replaces the `prefetch={false}` card links in grids, tables and dashboards.
- The planned loading skeletons were dropped: every `loading.tsx` already has a skeleton.

Validation: backend 414 passed (30 skipped); frontend 167 passed; typecheck and build passed. `next start` against the production API rendered the card OG/Twitter tags, `robots.txt` and the sitemap (474 set URLs).

## Data trust changes — 2026-10-24 (branch `phase1-data-trust`, not deployed)

Phase 1 of the UI/efficiency plan. No migrations; `Cards`/`Sets` untouched.

- **Stale snapshots instead of 503.** Trending (`SNAPSHOT_RETAIN_SECONDS`) and live stats (`RETAIN_SECONDS`) are now published with a 24h Redis TTL. Fresh windows are unchanged (30 min / 60s). Older snapshots are served with `is_stale: true`; Trending also sends `X-Cache-Status: stale` and `s-maxage=10`. A missing snapshot still returns 503. The frontend shows "Prices as of …; updates are paused" (Trending) and "Totals as of …; updates paused" (Live Comps) and keeps totals for up to 24h.
- **eBay asking outliers.** `app/services/asking_prices.robust_asking_price` uses the median of up to 30 matched asks from the last 30 days, within 3× of the lower median, and rejects anything over 100× the raw price. Grading profit uses it for eBay PSA 9/10 (PPT medians keep the newest row). Cache namespaces are bumped (`get_grading_profit_identity_v2`, `grading_profit:identity-v2`). The card chart's eBay lines use the same rule: a 10× series band, then daily robust medians.
- **Grade toggles.** PPT `tag` median quotes are ingested. BGS and SGC have toggles, and toggles show only for companies with history.
- **Source labels.** `PriceSourceBadge` labels the card-page headline ("PPT market" / "Last known") and grading-profit eBay rows ("eBay asking · not sold"). Tiles turn amber with "Last known" after 7 days.

Validation: backend 410 passed (30 skipped); frontend 164 passed; typecheck and production build passed. Not yet checked on production data: grading-profit query time with the wider eBay window.

## Production deploy — 2026-10-23 (release `b90ff28`)

Deployed by hand on the host, because `release.sh` never migrates and its `check_revision` guard rejects a release whose schema is ahead of the database. This release includes `79153e6` (catalog 503 fix, PPT pacing, live-stats legacy split, monitor iowait rule), `a633300` (snapshot schedule) and `b90ff28` (shared Live Comps feed). Steps and evidence:

- Stopped worker and Beat. `alembic upgrade head` (0012 → `0013_catalog_price_selected`) ran in a worker-budget `run` container with `PGOPTIONS='-c statement_timeout=0'`, because the server default is 12s. `python -m jobs.catalog_prices verify` reported `{"checked_cards": 55013, "mismatched_cards": [], "ready": true}`.
- `CATALOG_CURRENT_PRICES_ENABLED` was **missing** from `/etc/cardboarddex/app.env`, so production had been on the slow legacy catalog path. It was added as `true` (backup `app.env.bak-<timestamp>`).
- `release.sh` completed ("Verified deployment completed") while `ingestion.paused` was still present, so it left worker and Beat stopped. The marker was then removed and `monitor_ingestion.py` reinstalled.
- The default catalog request (`/cards/search?limit=24&offset=0&sort_by=price_desc&hide_sealed=true`) returned 200 `miss`. Rebuilds took 493ms and 242ms (previously 4.0–4.6s, with 503s).

Open checks:

- Verify worker/Beat state first; resume only when authorized, then confirm `Live stats refresh published=True`, PPT batches and Trending refreshes.
- Confirm that `get_live_feed_v1` rebuilds about once every 10s regardless of open tabs, and that iowait stays under 25%.
- Production `EXPLAIN (ANALYZE, BUFFERS)` for the default catalog query.

## Market movers excludes sealed — 2026-10-23 (local, not committed)

Production movers listed sealed products. `sealed_product()` in `backend/app/services/product_metadata.py` is now the single definition shared by the sealed page and movers, so the two pages are disjoint:

- A product is sealed when explicit PPT or legacy metadata says "Sealed Products".
- Without metadata, a blank rarity means sealed.
- The predicate is never NULL, so `not_()` keeps cards that have no metadata.

The shared predicate is integrated into the worker-built Movers snapshot. Production-sized refresh duration and memory remain release checks; public Movers reads no longer rebuild rankings.

## Handoff — 2026-10-19

The implementation retires tcgapi.dev and migrates active catalog/pricing work to Pokémon Price Tracker (**PPT**). Direct eBay asking-listing comparisons remain. Distinguish local fixes from the deployed release.

User-supplied production evidence (October 19): release `55c4ad9e92ed876036c3019c929b7baa230f0042`, backend image digest `4efb69d243958cf0cd856e81318e8e04c96f4b29c3fbabe764344ae8018582eb`, deployed successfully with schema `0012_market_history_transitions`. Projection backfill/verification covered 54,996 cards with no mismatches. Transition seeding processed 933 products; the before/after preservation audit passed at `/var/lib/cardboarddex/ppt-cutover-20261019T190118Z`. Deployment readiness and search probes passed; this is not full performance or stability validation.

Later on October 19, ingestion was resumed and at 19:24 UTC `jobs.sync_ppt` repeatedly timed out while ranking the weekly priority pool inline, before making any provider requests. Fixes since then, all deployed as release `3c54983` with `PPT_INGESTION_ENABLED=true` and `PPT_PRIMARY_ENABLED=true`:

- **Ranking decoupled from sync (`09c57ff`, `3c54983`).** `jobs.sync_ppt.build_priority_pool` runs on its own Beat schedule (every 900s, 240s time limit, Redis lease, 120s statement timeout) and writes checkpoint `priority:<monday>`. `sync_ppt` never ranks: it uses this week's pool, falls back to the latest earlier pool with a warning, or rotates with no priority lane. Ranking uses the verified v2 projection (current selected USD positive prices) when available.
- **Trending served from a worker snapshot (`7214f7a`).** `jobs.refresh_trending` publishes `cardboarddex:{ppt|legacy}:trending-snapshot:v1` every 60s under a lease (about 8.5s on the host). Public `/cards/trending` without `q` never computes: a missing or stale (>30 min) snapshot returns 503 with `Retry-After: 60`. Image URLs are resolved at read time. `release.sh` seeds it in a worker-budget `run` container (non-fatal). While paused, the host `cardboarddex-live-stats.service` also publishes Trending and must be reinstalled from the release.
- **Unified history (`69df9f6`).** Only seeded PPT continuations count as legacy-prefix candidates.
- **Live Comps** polls every 15s and prepends newly ingested rows (frontend test added). Since `b90ff28`, unfiltered first-page polls share one cached query per 10s (`LIVE_FEED_SHARED_CACHE_ENABLED`, default true). PPT feed rows appear only when price or `price_date` changes, at most one fetch per product per UTC day.

Production evidence at 01:03 UTC on October 20: worker and Beat running, `sync_ppt` completing 8 requests per run (from fallback pool `priority:2026-10-12`), new PPT feed rows with `price_date` 2026-10-19, live stats `total_ppt_updates` 1,584, and Trending refreshed. Open checks:

- ~~Confirm the pause marker was removed~~ and ~~live-stats timeout~~: both happened on October 20; see "Production incidents — 2026-10-20".
- Confirm `PPT priority pool built key=priority:2026-10-19` (or diagnose a build failure) and its duration on production-sized PostgreSQL.
- eBay collection resumed producing rows (19:04 UTC on October 20). Keep host memory above about 150 MB available and iowait under 10%.
- The installed host monitor still reports legacy TCGAPI coverage and needs its separately installed script updated.

The source/rollback host remains retained; deletion is not authorized. Earlier chronological evidence is in [operations runbook](OPERATIONS.md).

## Card page, catalog and UI changes — 2026-10-20 (release `16edaa2`)

Committed in `16edaa2` and deployed with that release.

- **Card page.** The "Historical performance" panel (`MarketHistoryPanel`, `getMarketHistory`) is removed. The price chart defaults to 3M, has printing toggles (on by default) and PSA/CGC/TAG toggles (off by default; PSA also controls the eBay PSA 10/9 lines). Lines are step lines that carry the last recorded value forward through today, display-only (`carryForward` in `frontend/lib/provider-history.ts`); the tooltip shows "since <date>" for carried values.
- **Catalog.** `getCardSets` always sends `game` (the backend defaults to English only), so Japanese sets appear in the catalog and search autocomplete. The price slider is a continuous log scale from $0 to $5,000+ that commits on release.
- **Trending and Graded Sales.** Full views are tile grids. Graded Sales drops per-grade counts.
- **Dev-only Trending fallback.** `TRENDING_ON_DEMAND_FALLBACK` (default false) lets `get_trending_dashboard` compute the snapshot once when it is missing, for local runs without a worker. Never enable it in production. `backend/tests/conftest.py` forces it off in tests.
- **UI.** Nav is centered when zoomed. Card hover is shared (`frontend/lib/card-hover.ts`: tile lift plus at most a 2% image zoom) so images are no longer clipped.

Open items:

- Resolved locally in Phase 1: TAG ingestion and BGS/SGC toggles are implemented; deployment remains separate.
- Resolved locally in Phase 1: eBay asking outlier filtering is implemented and retained in the grading snapshot publisher.
- Five Trending tests fail when a local Redis is running (pre-existing; they pass in CI).
- Locally, Trending needs a seeded snapshot (`python -m jobs.refresh_trending`) or the fallback flag, graded sales need `ppt_products`, and grading-profit needs `listing_assessments` (`python -m jobs.check_listing_images`, stored data only).

## Catalog 503 fix — 2026-10-20 (deployed 2026-10-23)

Production `/cards/search` returned 503 (`Results temporarily unavailable`) for the default catalog request. Uncached broad price sorts took 4.0–4.6s against the 5s rebuild `statement_timeout`, and `number_asc` exceeded it; each timeout also triggers the 30s failure cooldown. Fix, keeping the deadline unchanged:

- Migration `0013_catalog_price_selected` adds `catalog_price_candidates.selected`, which marks each card's PPT-primary price (computed on write by `mark_selected`, backfilled by the migration), plus partial index `ix_catalog_price_selected(price)`. `Cards`/`Sets` are untouched.
- Broad price sorts read priced cards in index order, then unpriced cards by name (`NOT EXISTS`). Number/set sorts pick the page before looking up prices. `search_cards` serves stale results for up to 30 minutes (was 5).
- Synthetic 55k-card PostgreSQL 17 with production memory settings: default catalog 71→2ms, `number_asc` 215→38ms; results identical to the old code in all nine cases. The deepest price page is slower (106→174ms). Production still needs an `EXPLAIN (ANALYZE, BUFFERS)` check.
- Deploy: stop worker/Beat **before** `alembic upgrade head` (the backfill assumes no concurrent candidate writes), then run `python -m jobs.catalog_prices verify` (or `repair`) in the worker-budget container before releasing. Confirm `CATALOG_CURRENT_PRICES_ENABLED=true` in production; the legacy path barely speeds up.

## PPT daily pacing — 2026-10-21 (deployed 2026-10-23)

Production Live Comps stopped receiving PPT rows after about 8,000 calls each day. Suspected cause (from code; production confirmation pending): each refresh costs 2–3 credits, so 20,000 credits is about 8,000 requests. The 15s Beat at 8 per batch (about 32 a minute, under the 55 weight limit) spends them by about 04:00 UTC, then every reservation is `PPTBlocked("daily")` until 00:00 UTC, which `sync_ppt` swallowed silently.

- `PPTQuota.reserve` now also enforces `pacing_allowance` atomically in the Lua reservation: daytime cap × elapsed/22h + one hour of burst. Returns `paced`. Retry and ≥22:00 UTC are unpaced; the hard cap still reports `daily`. `PPT_DAILY_PACING_ENABLED=false` restores the old behavior.
- `sync_ppt` logs `PPT batch yielded reason=… lane=…` and returns `blocked`; the health report adds `quota.pacing_allowance`.
- Before deploying, confirm on the host: Redis `cardboarddex:ppt:v1:credits:<epoch//86400>` near 19,500–20,000 early in the UTC day, and PPT `price_observations` per hour dropping to zero after the first hours. After deploying, PPT rows should arrive in all 24 hours.

**Actual production stop (confirmed October 22, 05:46 UTC):** the ingestion monitor paused ingestion again at 01:55:03 UTC on October 21 ("Memory/swap/I/O pressure persisted for five minutes"). Worker and Beat had been `Exited` for 28 hours, and Redis had no PPT counters for day 20748. Memory (178–287 MB available) and swap (<0.7 MiB/s) were fine and the API was healthy; iowait sat at 9.3–11.8% (limit 10%, `monitor_ingestion.py:35`) and peaked at 15.0%. The 10% iowait threshold trips on this host's normal load.

Fix (deployed 2026-10-23; the monitor was reinstalled on the host):
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
- ~~Durable live-stats fix~~: deployed 2026-10-23. Legacy totals are counted once a day, and only PPT and matched eBay rows are recounted each minute. Don't make the eBay count incremental by observation ID: `check_listing_images` moves old assessments from pending to matched, so a watermark would miss them.
- If iowait stays above 25% after the October 23 deploy, find the next heavy reader (Trending refresh about 8.5s, PPT/eBay jobs) with `pg_stat_statements` or per-task timings.
- ~~The catalog 503 fix above is still local and not deployed~~: deployed 2026-10-23.

## Implemented migration

- Active provider: PPT, with separate ingestion/public visibility gates, 20,000 daily credits and 55 weighted credits/minute. Scheduled and manual refresh share validation, quotas and ingestion. Retired client and queued task names are inert even if an old legacy flag is true.
- Data preservation: existing card/set IDs and schemas, price observations, daily history, provider state and image keys stay intact. Additive migration `0012_market_history_transitions` follows `0011_catalog_prices`. No bulk rename of stored provenance. Legacy field/index/task identifiers remain only for history and compatibility.
- Price charts: unified “Market price” continuation after an explicit per-series cutover. Earlier recorded values remain; the card chart uses one PPT continuation view rather than a separate backfill toggle. Printing, condition, currency, language and metric must match. An unknown-condition legacy prefix joins a unique matching PPT series with point-level condition metadata; ambiguous or conflicting history stays separate. Missing dates stay missing in the data; the chart draws step lines that hold the last recorded value through today (display-only).
- Price selection: matched PPT raw prices preferred when enabled; last-known prices retain source dates/stale status. Unmapped cards retain legacy values. Missing recent graded medians remain unavailable. Catalog projection version 2 requires backfill and verification.
- Trending: PPT graded sales activity replaces the retired sales-period panel. `salesByGrade` counts rank synced cards; no fixed window, dollar volume or raw-sales total is inferred. Partial raw refreshes preserve graded snapshot freshness independently. The default dashboard is a worker-published snapshot; only search (`q`) computes on request, under the five-second deadline.
- Consumers: catalog/home, movers, sealed, binder, Live Comps, provider coverage, images, diagnostics and active copy use PPT-aware behavior. Direct eBay remains asking-price evidence with existing title/image checks.
- Operations: explicit transition seeding, read-only preservation receipts, versioned caches and bounded PPT health publication. No public read triggers provider ingestion or creates a transition.

## Validation and release requirements

Local validation: 366 backend tests passed (30 skipped), all 153 frontend tests passed, TypeScript checks and the production frontend build passed, and `git diff --check` passed. Skipped infrastructure checks still need their configured disposable services. Isolated SQLite/unit checks are not production-sized PostgreSQL, public HTTP, browser-device or stability evidence. These counts predate the Trending snapshot, priority-pool and Live Comps polling tests added since. With the October 20 changes: 384 backend passed (30 skipped), 162 frontend passed, TypeScript clean; no production build or browser check was run. On October 23, with the shared Live Comps feed and movers sealed exclusion: 399 backend passed (30 skipped); frontend not rerun. Run backend tests with `PPT_PRIMARY_ENABLED=false MARKET_HISTORY_ENABLED=false` to match CI, because the local `backend/.env` enables both.

Follow [operations runbook](OPERATIONS.md): restore backups off-host, audit identities/history, rehearse migrations, rebuild/verify projection v2, seed transitions, validate private PPT-on reads, then deploy visibility separately from any ingestion resumption. Keep the SQL five-second and public smoke 15-second deadlines unchanged. Production-sized performance, actual mapping coverage, bounded authenticated refresh and the 48-hour observation remain release checks.

Never run an extra Python process inside the 160 MiB serving API container. The earlier `docker exec` seed caused an OOM. Use the isolated worker-budget maintenance container and the existing deployment lock. The last recorded release still has worker/Beat startup verification open; verify current host state before making any resumption claim. `/opt/cardboarddex/ingestion.paused` makes `release.sh` skip worker/Beat, so only recreate it to deliberately pause. Preserve quota/checkpoint Redis state and the existing rollback host.

## References

- [Architecture](ARCHITECTURE.md)
- [Tracked operations runbook](OPERATIONS.md)
- [Lightsail scripts and timer installation](scripts/lightsail/README.md)
- Historical notes and pre-migration evidence remain in ignored local `docs/`; they are not shipped in fresh clones.
