# CardboardDex Project Context

Updated: 2026-10-14. This handoff retains detailed product and implementation context, with dated deployment records and explicit known limitations. Repository: [n8liu/cardboarddex](https://github.com/n8liu/cardboarddex).

Read [AGENTS.md](AGENTS.md) before changing code, including the installed Next.js documentation requirement. Treat source code and dated verification as authoritative when older documents disagree. [ARCHITECTURE.md](ARCHITECTURE.md) describes the system boundaries but still contains outdated deployment and eBay implementation notes.

## Active production: 1 GB Lightsail, release 519dd23, schema 0007 — 2026-10-14 UTC

Production is successfully running on **`cardboarddex-1gb`, `micro_3_0`, $7/month, dual-stack, 1 GB RAM and 40 GB disk** in `us-west-2`. The previous AWS instance creation limit was cleared and destination creation completed with verified dual-stack network and hardware specifications.

Infrastructure migration and initial refresh rollout (completed earlier October 14):

- **Pre-cutover rehearsal:** Off-server restoration verified schema revision `0006_site_analytics`, table record counts, and Redis state against disposable test environments (`rehearsal-receipt.json`).
- **Maintenance window:** Paused writes at 2026-10-14 00:12 UTC. Captured final PostgreSQL dump and Redis AOF backup (`manifest.json`), restored both to `cardboarddex-1gb`, and verified complete row-count parity across all 10 tables (`cards`: 54,968, `price_observations`: 284,056, `provider_card_states`: 57,061, `raw_ebay_listings`: 28,842, `sets`: 491, `analytics_events`: 121, etc.).
- **Tunnel cutover:** Switched Cloudflare Tunnel routing to `cardboarddex-1gb` at minute 2 of the 30-minute window (148 seconds total maintenance time). The source instance `cardboarddex-recovered` remains running and billable, with API/Tunnel/ingestion stopped and source backup/retention timers disabled; source retirement requires explicit deletion authorization.
- **Service configuration:** Six-hourly backups and daily analytics retention systemd timers are active on `cardboarddex-1gb`. Docker Compose worker memory limits were raised to 192 MiB RAM / 256 MiB total with swap; Beat limits raised to 64 MiB RAM / 96 MiB total with swap. Concurrency remains 1.
- **Initial backend release & canaries (superseded by 519dd23 below):** Deployed immutable image `349558247779.dkr-ecr.us-west-2.on.aws/cardboarddex-backend:passive-652c868fcf5b` (digest `sha256:dac6310bc20b26a6798760b0c35864a0b385432c6da305f4a8cb79ca61141f06`). Production canaries for TCGAPI and eBay executed with zero errors, writing accepted market observations.
- **Passive refresh active:** The 1,500-card priority pool is frozen in durable Redis under `cardboarddex:passive:v2:cycle` for 7-day cycles. Alternating schedule runs 8-card batches (5 priority, 2 hot, 1 catalog) with atomic daily sublimits (1,500 TCGAPI / 450 eBay).
- **Monitoring & observation:** `cardboarddex-ingestion-monitor.timer` runs every minute recording health to `/var/lib/cardboarddex/ingestion-monitor/latest.json`. Ingestion was resumed with exactly one worker and one Beat. The 48-hour stability observation window is active (started 2026-10-14 06:25 UTC).

Initial-release verification at **2026-10-14 18:17 UTC**: both providers completed 202 successful checks, including 145/1,500 priority cards and 26 catalog advances each, with no retry backlog. TCGAPI used 410/1,500 scheduled requests (410/2,000 global); eBay used 209/450 (209/500 global). Exactly one worker and one Beat were running; all seven containers had zero restarts/OOMs, API readiness passed, and the monitor reported no regressions with approximately 302 MiB available. Automatic alternating dispatch and the 12:20 UTC backup succeeded.

Post-deployment backup `six-hourly/20261014T122001Z/manifest.json` passed checksum validation and actual off-server PostgreSQL/Redis restoration on October 14 at 18:17 UTC: schema `0006_site_analytics`, 54,968 cards, 491 sets. Private receipt: `.system_generated/lightsail/upgrade-1gb/active-refresh-receipt.json`.

Public endpoint verification of the initial passive release passed 13 tests; two legacy direct-AWS checks were skipped. `git diff --check` passed. Disposable local integration containers were removed; production and retained recovery resources were preserved.

### Current backend deployment and migration — verified October 14 at 19:55 UTC

- **Active release:** `/opt/cardboarddex/releases/519dd2311520b02c11a6548748a51eb53bb17b79`; `/opt/cardboarddex/current` points there. Immutable image: `349558247779.dkr-ecr.us-west-2.on.aws/cardboarddex-backend@sha256:21f25bca35cb60fa01448065d3730449dab3d5536018bfe20d3ee2235d1fe973`.
- **Schema:** The user manually applied `0007_market_data`; a direct production query verified that revision. The migration adds `market_history`, its day index, and `catalog_snapshots`, without altering Cards/Sets. The earlier schema mismatch is resolved. A disposable rehearsal of this migration was recommended but was not completed or verified in this session; the earlier off-server restore receipt covers schema 0006, not 0007.
- **Deployment:** The user successfully ran the existing release's `scripts/lightsail/release.sh` after clearing a lock inherited by nested Bash sessions. The prior scoped `passive-652c868fcf5b` release is superseded. Its exclusion of schema 0007 and other HEAD changes describes the initial rollout only.
- **Ingestion and readiness:** After verifying the new release and local readiness, the agent resumed exactly one worker and one Beat at approximately 19:55 UTC and removed `ingestion.paused`. Worker ping returned one online node; public `/ready` returned `{"status":"ready"}`. The monitor found all seven containers running, zero reported OOMs/restarts, no regressions, and approximately 295 MiB available. Its latest backup age was approximately 12 minutes. The full public smoke suite has not been rerun for this release.
- **Durable refresh progress:** At resumption, TCGAPI had checked 162/1,500 priority cards with 29 catalog advances; eBay had checked 155/1,500 with 28 catalog advances. Both had zero queued retries and zero overdue cards. Scheduled/global usage was 459/1,500 and 459/2,000 for TCGAPI, and 226/450 and 226/500 for eBay. These are snapshots of retained progress, not proof of a completed pricing batch on the new image.

### Repeated GitHub deployment failures for the same commit

The first CI attempt uploaded commit `519dd2311520b02c11a6548748a51eb53bb17b79` with image `21f25bca…`, then failed the schema guard while production was still at 0006. Application rollback succeeded. Later attempts rebuilt that same commit with image digests `7b43a80a…` and `45c14128…`. The immutable-release check rejected their differing `source.sha256` values before changing running services. Configuration files in the original release and the first conflicting staged upload were compared and were identical; the image reference differed.

The original image was subsequently deployed manually after migration. Failed GitHub runs do not become successful retroactively. Do not delete or overwrite the active release to clear the checksum error, or repeatedly rebuild the same commit expecting its existing release to accept a new digest. A retry must reuse the exact original image/configuration; a new code commit receives a separate release directory. Rebuilds of a commit can produce different image digests, so commit-only release naming remains a known retry limitation.

### Remaining production verification and rollback constraints

The monitor retains its original observation baseline of October 14 at 06:25:48 UTC and initial 48-hour deadline of **October 16 at 06:25:48 UTC**. The manual migration/deployment interrupted ingestion and changed the release; that deadline must not be presented as 48 uninterrupted hours on the new image. A full 48 hours after resumption is **October 16 at approximately 19:55 UTC**, subject to further changes or interruptions. The first-cycle **weekly coverage deadline remains October 21 at 06:19:46 UTC**; durable membership and progress were retained. Stability, overnight catalog sync, and weekly coverage reviews remain pending. The monitor pauses on configured regressions but does not certify completion of these reviews.

Verify a fresh schema-0007 backup with an off-server restore and test the new market-data features before claiming complete release validation. Do not downgrade merely to roll back application code: migration downgrade deletes the new tables and their data. Cross-instance rollback after destination writes requires transferring fresh PostgreSQL and Redis data back before switching traffic. Source `cardboarddex-recovered` remains running/billable with its application services and backup/retention timers stopped; source deletion is not authorized. The $7 destination price excludes the retained $5 source, snapshots, and backup storage.

GitHub deployment/image-sync workflows were restored to active, targeting the new host (SSM `mi-0701a7d2b33760744`). Stale run `34748756712` remains: user-authorized deletion returned HTTP 403, while cancel/force-cancel returned 409. Its exact historical workflow was verified to target retired ECS, with no Lightsail deployment. The old production image was recovered into ECR at its original digest; ECR retention now preserves tagged releases and expires unreferenced untagged images after seven days.

## Project rules

1. Log the exact error and useful request/card context for third-party failures; do not silently swallow exceptions. Keep credentials and sensitive response fields out of logs.
2. Do not change the existing `cards` or `sets` columns, constraints, indexes, or migrations without explicit permission.
3. Keep all eBay title interpretation in [backend/parsers/title_matcher.py](backend/parsers/title_matcher.py), with edge-case unit tests.
4. Before implementing a feature, publish a Markdown plan listing the files to change. Deliver one tested, runnable phase at a time.
5. Ask before committing or pushing unless already authorized.
6. Update this handoff after implementation when behavior, configuration, verification, or outstanding work changes. Do not append repeated feature histories.

## Product and data boundaries

CardboardDex provides an English/Japanese Pokémon card catalog, price comparisons, a National Pokédex, and a browser-based collection binder.

- **TCG API:** canonical card/set catalog and per-printing market-price observations.
- **eBay Browse API:** active asking-price listings matched by title, including raw cards, graded slabs, and sealed products. A matched title is not proof of authenticity or a completed sale.
- **PokéAPI:** Pokémon details; a bundled registry supports browsing 1,025 species and evolution families.
- **PostgreSQL:** catalog, provider state, price observations, and raw eBay listing records.
- **Redis:** Celery broker/results, provider quotas, analytics, caches, and the eBay application-token cache.

Provider credentials stay server-side. The browser calls FastAPI and also loads external fonts/media; PokéAPI detail fetching is implemented in the frontend's server-rendering path. Binder names/pages/slot-to-card-ID mappings persist in localStorage. Card IDs are sent to the backend for valuation and the resulting valuation is cached server-side.

Catalog image responses use `/cards/{id}/image`. The backend downloads provider images or redirects to configured S3/CDN assets; the Next image optimizer is configured for supported origins. S3 URLs may therefore be visible to clients. CloudFront/custom-domain delivery remains a deployment follow-up, not a verified requirement for existing image delivery.

## Stack and source map

- Frontend: Next.js 16 App Router, React 19, Tailwind CSS 4, Recharts, TypeScript, Vitest. Exact versions: [frontend/package.json](frontend/package.json).
- Backend: Python 3.11+ declared; Docker/CI use Python 3.12. FastAPI, SQLAlchemy 2, Alembic, Celery, Redis, HTTPX, boto3.
- Production deployment: Cloudflare Pages (frontend) with AWS Lightsail Linux VPS ($7.00/month micro_3_0 dual-stack server base, 1 GB RAM / 40 GB disk; Docker Compose running FastAPI, Celery worker+Beat, PostgreSQL 16 Alpine, Redis 7 Alpine, Cloudflare Tunnel connector) in `us-west-2`, and S3 card asset bucket.
- Local PostgreSQL/Redis: [docker-compose.yml](docker-compose.yml). Backend Docker/CI install [backend/requirements.txt](backend/requirements.txt); they do not currently consume `backend/uv.lock`.

| Area | Entry points |
| --- | --- |
| API setup, CORS, health, headers | [backend/app/main.py](backend/app/main.py) |
| Settings, database, Redis, rate limiting | [backend/app/config.py](backend/app/config.py), [backend/app/database.py](backend/app/database.py), [backend/app/common](backend/app/common) |
| Search, sets, Pokémon card queries | [backend/app/routers/catalog.py](backend/app/routers/catalog.py), [backend/app/services/catalog_service.py](backend/app/services/catalog_service.py) |
| Card detail, prices, images | [backend/app/routers/cards.py](backend/app/routers/cards.py) |
| Movers, grading, sealed signals, live updates | [backend/app/routers/market.py](backend/app/routers/market.py), [backend/app/services](backend/app/services) |
| Trending, action tracking, portfolio valuation | [backend/app/routers/analytics.py](backend/app/routers/analytics.py), [backend/app/services/portfolio_service.py](backend/app/services/portfolio_service.py) |
| Provider adapters and quotas | [backend/app/tcgapi/client.py](backend/app/tcgapi/client.py), [backend/app/ebay/client.py](backend/app/ebay/client.py), [backend/app/providers/limiter.py](backend/app/providers/limiter.py) |
| Catalog, pricing, image jobs | [backend/jobs](backend/jobs), [backend/app/celery_app.py](backend/app/celery_app.py) |
| Browser/server API access and fallback valuation | [frontend/lib/api.ts](frontend/lib/api.ts), [frontend/lib/portfolio.ts](frontend/lib/portfolio.ts) |
| Binder state and UI | [frontend/context/binder-context.tsx](frontend/context/binder-context.tsx), [frontend/components/binder](frontend/components/binder) |
| Pokédex data and species details | [frontend/lib/pokedex-data.ts](frontend/lib/pokedex-data.ts), [frontend/lib/pokeapi.ts](frontend/lib/pokeapi.ts) |
| Deployment workflows | [.github/workflows/backend-ci-cd.yml](.github/workflows/backend-ci-cd.yml), [.github/workflows/frontend-ci-cd.yml](.github/workflows/frontend-ci-cd.yml) |

## Card-profile pricing corrections and Live Comps grid (local, 2026-10-15)

- Card pricing now returns `tcg_market_prices` from the latest matched `ProviderCardState.payload.prices.data` snapshot. The market price and 24h/7d/30d changes come from the same printing in that response. This fixes stale momentum when unchanged prices suppress new historical observations. Null/missing percentages are not backfilled; eBay observations never substitute for TCG market data. Existing historical observations remain unchanged, and opening a profile makes no provider requests.
- `avg_listing_price`, `median_listing_price`, and `listing_sample_count` use unique raw USD eBay listing IDs observed within the trailing seven days, excluding future observations, nonpositive prices, non-USD prices, and graded listings. Repeated listing observations use the latest price once, independently of the history-chart window. No outlier trimming or TCG fallback is applied. UI labels explicitly state 7d; lowest listing and volatility retain their existing scope. No Cards/Sets schema changes.
- Live Comps defaults to a responsive 2/3/4/6-column artwork grid, showing six cards per row at widths of 1280px and above with price, provider, time, condition/grade, and links in each card. The optional full-width list, URL state, filtering, polling, and infinite pagination remain.
- Validation: 128 frontend tests, 57 focused backend tests, TypeScript, production build, and diff checks passed. Provider-data verification and deployment were not performed. Deploy the backend pricing-response additions before the frontend; the frontend intentionally does not fall back to old observation percentages when current snapshot fields are absent.

## Pokédex live totals (local, 2026-10-15)

- Pokédex header counts now use `AnimatedNumber` for species, tracked catalog products, indexed sets, and comps. Species count comes from `POKEDEX_DATA.length`; other totals come from `/home/stats`, sharing the homepage and unfiltered Live Comps count source.
- `useLiveCollectionStats` centralizes the existing homepage polling behavior for both pages: 60-second visible-tab refresh, refresh on return, no overlapping requests, abort on hide/unmount, and retained prior values with retry on errors. The Pokédex route loading shell uses placeholders instead of obsolete hardcoded totals. No new provider calls or backend changes. Local verification: all 130 frontend tests, TypeScript, production build, and diff checks passed; not deployed.

## Homepage live totals and trending feature (local, 2026-10-14)

- Fuller opening layout: the homepage uses a 1600px content width, reduced hero padding/gaps, and compact Trending, Live Comps, and Sealed Signals shortcuts under the main actions. The left hero column uses its full available width for shortcuts, with a larger fluid desktop headline; the homepage search bar uses 75% of that column on desktop and full width on mobile; this removes the unused space caused by nested 672px width caps. Market today begins closer to the hero. The enlarged artwork and lower-page totals retain their existing behavior.

- The three animated collection totals appear in their original “Behind the collection” section at the bottom of the homepage. `HomeLiveStats` fetches `/home/stats` independently of the cached market overview, refreshes every 60 seconds while visible, and refreshes when returning to the tab. Requests do not overlap; hidden/unmounted reads are aborted. Failed refreshes retain the last counts with an explicit retry state.
- `/home/stats` reads current product/set totals from the database. Its price-observation total uses `live_observation_count`, the same joined query and 60-second Redis count key as unfiltered Live Comps. Neither endpoint makes provider requests. Filtered Live Comps counts still reflect their filters; snapshots fetched at different times can differ.
- `HomeTrendingCard` loads the existing trending dashboard independently and chooses one of its first 50 cards at random once per mount. It displays only card artwork beside the main introduction on desktop, enlarged to 420px wide (approximately 588px tall) to match the supplied reference; tablet/mobile widths are capped at 340px/280px and preserve the image aspect ratio. Mobile stacks it below. The homepage artwork is shifted 5rem left from the desktop breakpoint; mobile remains centered. There are no visible labels, prices, or links; the image retains descriptive alt text. The artwork uses the shared `HoloCard` wrapper with the catalog’s 8-degree tilt and rarity-based holographic sheen. Selection stays stable while totals refresh. Loading uses an artwork placeholder, failures allow retry, and an empty list displays no artwork.
- “Behind the collection” contains both live totals and source descriptions at the bottom. No database schema or ingestion changes. Backend must deploy `/home/stats` before the corresponding frontend.
- Verification: all 124 frontend tests, 36 focused backend tests, TypeScript, production build, and diff checks passed locally. No production deployment or browser visual verification performed for this change.

## Mobile search positioning (local, 2026-10-14)

- Catalog filters (quick chips and Browse sidebar) are collapsed by default below 1024px behind an accessible Show/Hide filters button. Focusing the catalog search collapses them again without resetting filter selections. Desktop keeps both visible.

- At widths below 768px, focusing page search aligns the input eight pixels below the actual sticky header. Homepage autocomplete, catalog search, shared dashboard/species search, and Pokédex search opt in via `data-mobile-search`; dialog searches and desktop are excluded.
- `MobileSearchFocus` handles focus centrally in the root layout, adjusts during the first 700 ms of keyboard opening using VisualViewport resize events, and stops repositioning afterward. Blur/unmount cancels listeners and timers. Autocomplete's scrollable suggestions use the remaining visible viewport height. Mobile search text is 16px to avoid browser focus zoom.
- Local verification: all 119 frontend tests passed, including six mobile-focus tests for alignment, viewport sizing, desktop/modal exclusions, and cleanup; TypeScript, production build, and diff checks passed. Real-device keyboard behavior and production deployment remain unverified.

## Price comparisons and sales activity (local, 2026-10-14)

- Sealed Signals now follows Grading Profitability’s product-card layout: side-by-side newer/older sections on desktop, each with two product columns from 1280px (four total); narrower desktop uses one product column per era, and mobile stacks the sections, rounded cards, rank/type/signal badges, 112×160px mobile and 144×208px larger artwork, and separate market-price/growth panels. Each era retains independent rankings, pagination, errors, and loading; history and purchase-return controls remain in each card’s disclosure.

- Larger dashboard artwork: Sealed Signals, Grading Profitability, and Market Movers card images are 112×160px on mobile and 144×208px from 640px. Market Movers table thumbnails are 56×80px on mobile and 64×96px from 640px; its side-by-side gainers/drops grids use one product per era column at narrow desktop widths and two at 1280px+. Images retain object-contain sizing so the full product remains visible.

- Movers cards and table rows, and Sealed Signals rows, now show previous → comparison price and signed monetary change alongside the selected-period percentage. Provider-percentage reversals are explicitly labeled “Est. previous”; missing/invalid baselines remain unavailable. Movers returns these fields from stored data only.
- Sealed comparisons use actual matching-printing history endpoints when a complete 30/90-day window exists. The historical ending price is kept separate from today's market quote, avoiding mismatched dollar/percentage changes. Provider-only 30-day changes use an estimated baseline. Response/service cache versions were bumped for the new fields. No database tables or migrations changed.
- Sales Activity now distinguishes unsynced history, no matching reports, and missing period sales. Set-name searches work, and the sync timestamp is scoped to matching sales records rather than unrelated history. Recorded zero sales remain distinct from missing counts.
- Read-only public verification: `https://api.cardboarddex.app/market/sales-activity?days=30` returned HTTP-success JSON with `synced_at: null`, `total_sales: null`, zero products, and no items. The panel cannot display rankings until history ingestion supplies records. No provider sync, production settings change, or deployment was performed. A bounded history pilot and verified provider access remain required before enabling scheduled history collection; respect any production ingestion pause gate.
- Local checks: 55 focused backend tests and all 113 frontend tests passed; frontend production build (including TypeScript) and diff checks passed. UI behavior was tested with fixtures, not production browser verification.

## Visible metric count-up animations (local, 2026-10-14)

- `frontend/components/ui/animated-number.tsx` now counts from zero over 900 ms when a loaded metric enters the viewport. Each value animates once per mount/value change; scrolling back to the same value does not replay it. Market Movers summary percentages/counts and catalog set totals inherit this behavior.
- Price overview TCG market price, raw listing minimum/average/median, volatility, homepage catalog totals, and Live Updates headline counts use the shared component. Missing price values remain unavailable rather than becoming zero.
- Reduced-motion preferences skip animation (including preference changes during animation). Server HTML and browsers without IntersectionObserver retain final values. Final-width reservation limits layout movement, and assistive technology receives the final value rather than frame-by-frame updates. Observers and animation frames are cleaned up on value changes/unmount.
- Local verification: 109 frontend tests passed, including visibility, delayed negative values, formatter rerenders, reduced motion, observer fallback, and cleanup. TypeScript and production build verification recorded with this change; no deployment or production visual verification performed.

## Application caching and loading improvements (local, 2026-10-13; not deployed)

- Adds bounded Redis/process response caching with original generation/freshness timestamps, stale serving, token-owned rebuild locks, one background refresh per API process, isolated database sessions, query timeouts, and explicit unavailable responses after maximum age. Covers catalog/Pokémon searches, set directory/statistics, home, grading, sealed, and movers. Coordinated routes bypass older nested service caches.
- Browser caching now explicitly covers browsing reads for up to 60 seconds and sets for five minutes, capped by backend freshness. Subscriber-aware cancellation, request deduplication, retry bypass, and stale notices preserve `no-store` for live polls/private/tracked reads. Coordinated server fetches bypass Next's data cache. Public response bodies remain compatible; exposed cache/timing headers provide metadata.
- Catalog loads immediately and only debounces text/price changes. Existing independent controls/detail-streaming work is retained. Live Comps pauses hidden-tab polling and prevents poll overlap; PokéAPI has three-second deadlines; binder fallback is limited to four concurrent HTTP reads with partial-success/error logging.
- Market Movers now reads stored ungraded USD TCG observations only, uses the exact period's reported percentage, and ranks before pagination. No provider requests, unrelated-row deltas, other-period substitution, or fabricated movers. Empty coverage is explicit; source observation dates remain visible while ingestion is paused.
- Verification: 239 backend tests passed, 19 opt-in tests skipped; 103 frontend tests, TypeScript, and production build passed. Three separate disposable PostgreSQL/Redis integration tests passed. Local production-build browser checks held API responses pending across six listing/dashboard routes at 390px and 1440px: controls remained usable, no horizontal overflow, and zero browser exceptions. A fixture-based catalog revisit used zero additional API requests and had no browser errors. Production latency is not yet measured; no whole-page speedup is claimed. Existing framework deprecation warnings remain.
- No Cards/Sets schema/index changes, ingestion restart, R2 activation, Cloudflare rules, paid-service upgrade, commit, push, or deployment. See [performance behavior and rollout](docs/performance.md) for exact freshness limits, interfaces, verification, monitoring, and rollback.

## FAQ, guides, and release calendar (local, 2026-10-12; not deployed)

- `/faq` places the calendar and set directory at the top, followed by 18 searchable questions across collecting, website usage, prices, and shopping, plus six linked guides (getting started, card identification, pricing, storage, releases/restocks, and TCG history). Articles are static routes with metadata, contents navigation, review dates, and official references.
- `/calendar` redirects to `/faq#calendar`; the embedded calendar provides month/list views, retailer/event/language filters, date selection, and separate undated Target/Walmart/Pokémon Center drops. Every valid dated set from the directory’s shared catalog/researched data appears on its release day, including historical sets. Both views share one request per language per mount/retry; missing dates remain unknown. Set releases are date-only events, not retailer checkout times.
- Expected retailer windows use the site owner’s schedule: Target Tuesday/Thursday at **12:00 AM PST (start of day)** and Walmart Wednesday at **6:00 PM PST**. PST is fixed UTC−8 year-round, without daylight-saving adjustment. Windows appear only for today/future dates, never as fabricated historical drops. The **Show expected windows & reminders** checkbox hides both weekly windows and Pokémon Center planning reminders. These windows are explicitly unconfirmed; no live inventory monitoring or verified upcoming checkout schedule is claimed.
- The expandable Pokémon Center history table links to five reported preorder openings, also shown on their historical calendar dates: Delta Reign September 30, 2026 (37 days before release), Pitch Black June 10, 2026 (37), Mega Evolution July 15, 2025 (73), Destined Rivals March 24, 2025 (67), and Prismatic Evolutions November 1, 2024 (77). News publication timestamps are not used as checkout times. Future English expansions receive a one-calendar-month planning reminder, clamped to month end; Japanese sets and promo collections are excluded. A matching reported preorder suppresses that set’s estimate, including Delta Reign’s otherwise October 6 reminder.
- English set dates use 187 factual release records across 22 series/collections from the user-supplied TCGplayer article (updated September 28, reviewed October 12), matched to catalog IDs through normalized names/explicit aliases. Japanese catalog dates stay separate. The directory supports series filtering, search, release ordering, elapsed calendar days using the current PST date, unknown dates, partial failure/retry, and incremental display. Print status requires dated set-specific evidence, expires back to Unknown, and is not inferred from age or stock. No current set-specific production evidence was found, so all statuses initially remain Unknown.
- New destinations are linked in the header, command palette, and footer using the existing visual theme. No backend/schema changes or automated retailer scraping. Editorial events need manual review and redeployment; catalog dates follow existing ingestion.
- Source ownership: [calendar UI](frontend/components/release-calendar.tsx), [event/date helpers and preorder history](frontend/lib/release-calendar.ts), [English release data](frontend/lib/english-set-releases.json), [FAQ/guide content](frontend/lib/learning-content.ts), and [regression tests](frontend/tests/learning-pages.test.tsx).
- Research, sources, data ownership, and maintenance: [FAQ/calendar notes](docs/learning-and-calendar.md). Verification on October 12: 84 frontend tests passed (16 learning-page tests), including shared release events, fixed-PST schedules, historical preorders, and month-end reminder handling; TypeScript and production build passed. Existing Edge Runtime deprecation warnings remain. These are local checks, not deployment verification.
- Browser verification with fixture catalog responses: FAQ, calendar, and history article fit 320/390/768/1024/1440/1600px widths. FAQ expansion, month navigation, list view, and unknown-guide 404 passed with zero browser exceptions. Real retailer inventory and live catalog responses were not exercised. Follow-up browser checks confirm the combined FAQ layout at all six widths, calendar-before-questions order, section navigation, and `/calendar` redirect to `/faq#calendar`, with zero browser exceptions.

## Provider market-data upgrades (local, 2026-10-11; not deployed)

- Implements API recommendations 1/2/3/6/7: cached historical performance and purchase-cost return estimates, market-price freshness, explicit sealed identity, provider-reported sales activity, and admin catalog coverage/new-set discovery. Printing/condition holdings, collection imports, and bulk upgrades remain excluded.
- Migration `0007_market_data` adds only `market_history` and `catalog_snapshots`. Cards/Sets schemas are unchanged. Deploy migration/backend before frontend; the new routes require these tables.
- Individual history ingestion is bounded and idempotent by product/printing/day, retains 372 days, and preserves unknown versus zero sales. Read paths never call the provider. `MARKET_HISTORY_ENABLED=false` by default; the opt-in Celery schedule processes five oldest/unsynced products hourly and snapshots both Pokémon catalogs daily. No production ingestion was started; keep the existing pause restrictions.
- Sealed rankings now support 30/90-day growth and cached charts. Explicit provider product type overrides rarity heuristics; price-only ingestion preserves card metadata. Ninety-day growth needs a real baseline; 30-day growth may use the provider's direct percentage. Freshness uses `market_price_as_of`, separately from the provider check time. Purchase-cost estimates are unrealized before fees/taxes and do not persist user input.
- Trending's sales column uses reported daily sales from synced products, not observation counts or fabricated dollar volume. Recent sales may lag prices by 1–3 days. Legacy observation endpoints remain compatible, while the frontend skips their unused aggregation.
- Admin catalog health compares paginated provider snapshots to local sets/products and shows missing/recent sets. It uses existing session/origin protection and performs no catalog writes.
- See [market-data rollout and semantics](docs/market-data.md). Provider plan capabilities and live data population are not verified; unavailable/restricted data stays explicit in the UI.
- Verification: 218 backend tests passed, 16 skipped; 53 frontend tests passed. TypeScript and the production build passed. The SQLite migration upgrade/downgrade/re-upgrade test confirms Cards/Sets schemas remain unchanged; live PostgreSQL/provider checks were not run for this change.
- Local runtime repair (2026-10-11): the development PostgreSQL database was still at `0006_site_analytics`, so sealed history queries returned HTTP 500. Applied existing migration `0007_market_data` to local `localhost:5432/cardboarddex`; both new tables now exist. Verified local API HTTP 200 for newer/older eras at both 30/90 days (598 newer and 1,970 older products), plus a successful page render at `localhost:3000/sealed-signals`. No production migration or provider sync was performed. No `file:///` links appeared in the rendered page or returned image URLs; the separate browser warning was not reproduced or conclusively diagnosed.

## Admin traffic statistics — phase one (deployed, 2026-10-10)

- Admin origin update (2026-10-11, local; deployment pending): defaults and environment examples now include exact HTTPS origin `https://cardboarddex.nliu.org`. Existing production `ADMIN_ALLOWED_ORIGINS` overrides must also append it, followed by API container recreation. This setting governs admin and telemetry authorization separately from CORS. The existing `SameSite=Strict` cookie still prevents cross-site browser sessions between `nliu.org` and `cardboarddex.app`; use the same-site admin URL until cookie/API routing support is addressed. Regression coverage verifies custom-origin login/stats/logout and rejects HTTP, sibling, and spoofed origins; it does not simulate browser cookie enforcement.
- `/admin/stats` provides an admin login shell and private traffic dashboard: UTC date ranges (Today/7/30/custom within 90 days), daily views/unique browser visitors/sessions, lifetime views/visitors, country breakdown, top 20 pages, and previous-period comparisons. Recharts includes an accessible daily data table; loading, disabled, empty, expired-session, and error states are explicit.
- Local refinement (2026-10-10, not yet deployed): dashboard separates period totals from lifetime totals, labels page views as Total visits, adds views per visitor and country/page traffic shares, highlights the selected preset, and explains equal counts. Persistent browser UUIDs already deduplicate visitors across reloads/tabs; backend aggregation was correct. Added tracking for back/forward-cache document restores, which previously bypassed the pathname effect. Repeat views increase visits without creating a visitor; no IP grouping or historical backfill. Verification: 42 frontend tests and 13 analytics backend tests passed; TypeScript and production build passed. Existing Edge Runtime and Starlette deprecation warnings remain.
- The root layout mounts a browser pathname tracker. It excludes admin/unknown routes, filter/query-string changes, API polling, disabled/local development environments, recognized bots, and browser opt-outs/Do Not Track. UUID event IDs deduplicate retries and Strict Mode effect replay. It sends no search text or binder contents. Browser delivery failures log errors without interrupting navigation.
- FastAPI owns `/admin/login`, `/admin/logout`, `/admin/stats`, and `/telemetry/page-view`. Login uses existing `ADMIN_API_KEY`; eight-hour sessions use a Secure/HttpOnly/SameSite=Strict cookie, database-stored HMACs, logout revocation, exact origin checks, and separate rate limits. Admin secret rotation invalidates sessions. Admin and telemetry responses, including errors, use `Cache-Control: no-store`. No admin credential is stored in browser storage or the frontend bundle.
- Migration `0006_site_analytics` adds only `analytics_events`, `analytics_visitors`, `analytics_days`, and `admin_sessions`; `cards`/`sets` remain unchanged. Event writes serialize per visitor, deduplicate event IDs, and maintain lifetime daily totals transactionally. Visitor HMACs persist for lifetime counts; sessions restart after 30 minutes without a tracked page view. Reports count sessions active in each period.
- Detailed reporting/retention is 90 UTC calendar days; `python -m jobs.cleanup_analytics` removes expired events and admin sessions in bounded batches, preserving lifetime visitors and view totals. New Lightsail systemd retention service/timer runs independently of paused Celery ingestion. It must be installed and monitored at rollout.
- Collection defaults OFF. Backend requires `ANALYTICS_ENABLED=true` and stable `ANALYTICS_IDENTITY_SECRET` (at least 32 characters); frontend requires build-time `NEXT_PUBLIC_ANALYTICS_ENABLED=true`. Local testing additionally requires `NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL=true` and `ADMIN_COOKIE_SECURE=false`. Set exact `ADMIN_ALLOWED_ORIGINS`; preview hosts are excluded by default.
- Country is Unknown unless the actual socket peer belongs to explicit `ANALYTICS_TRUSTED_PROXY_CIDRS`. Before enabling country attribution, verify the closed Tunnel origin, Cloudflare geolocation, and Uvicorn socket-peer preservation (`--no-proxy-headers`). See [admin stats setup and rollout](docs/admin-stats.md). Production rollout is verified below: trusted peer `172.18.0.1/32`, Uvicorn forwarded-header trust disabled with `FORWARDED_ALLOW_IPS=`, HTTPS admin cookies, and daily retention enabled.
- Verification: 202 backend tests passed, 16 skipped (including opt-in live/PostgreSQL checks); 38 frontend tests passed; TypeScript check and production build passed. Separate disposable PostgreSQL 16 test passed upgrade/downgrade/re-upgrade, unchanged catalog schema, concurrent first visits and duplicate deliveries, and UTC bucketing with a non-UTC database session. The temporary database container was removed. Existing framework/dependency deprecation warnings remain.
- Local activation verified on 2026-10-09: frontend runs on port 3001; the ignored root `.env` now has a local admin secret, HTTP-compatible admin cookies, localhost/127.0.0.1 origins on ports 3000/3001, and analytics enabled. The local PostgreSQL database already had revision `0006_site_analytics`; no migration was needed. After backend reload, login/stats/logout returned 200, unauthenticated access returned 401, and an unapproved origin returned 403. The local credential is stored in ignored `.system_generated/admin-stats/local-admin-secret.txt` with mode 0600; never commit it. These local credentials are separate from production.
- Public Trending counters are unchanged and are not visitor statistics. Interaction events (search, filters, binder actions, outbound eBay clicks), referrers/devices, and engagement are phase-two work. Existing `trackUserAction()` has no current component callers; prior feature descriptions of full click/search tracking should not be read as verification.

## Implemented features and interaction details

The following retains the product's visual specifications, interaction behavior, and component locations. These descriptions do not override the pricing, privacy, caching, or deployment limitations recorded below.

- **Interactive Physical Pokémon Portfolio Binder & Valuation Suite (`/binder`)**:
  - **Authentic White Collector Album Binder Experience** ([`frontend/components/binder/binder-page-view.tsx`](frontend/components/binder/binder-page-view.tsx), [`frontend/app/binder/page.tsx`](frontend/app/binder/page.tsx)):
    - **Physical Binder Aesthetics (White Theme)**: Rendered in a clean, pristine White Collector's Album theme matching CardboardDex's design language: crisp white leatherette cover textures (`.binder-leather-cover`), perimeter dashed stitching (`.binder-stitch`), refined silver/chrome metallic corner brackets, heavy metallic 3-ring chrome spine with circular hole punches (`.binder-ring`, `.binder-hole-punch`), and welded polypropylene pocket sleeves (3x3 grid) with diagonal gloss reflections (`.binder-sleeve-gloss`).
    - **Flexible Page Layouts**: Supports **Two-Page Spread (Open Binder)** on desktop displaying 18 slots side-by-side with center rings, as well as **Single Page** 9-pocket mode.
    - **Multi-Page Management**: Smooth page navigation (`Page 1 of N`), direct page tabs (`[P.1]`, `[P.2]`, `[+ Add Page]`), delete page, and keyboard shortcuts (`[` / `]` or `ArrowLeft` / `ArrowRight`).
  - **Client-Side `localStorage` Persistence (Binder Metadata and Card IDs)** ([`frontend/context/binder-context.tsx`](frontend/context/binder-context.tsx)):
    - Stores binder/page names, page IDs, version, and slot-index-to-card-ID mappings under `cardboarddex_binder`; prices are fetched separately. Card IDs are uploaded for backend valuation.
    - Real-time cross-tab synchronization with `storage` and `cardboarddex_binder_updated` window events.
  - **Portfolio Valuation & Historical Valuation Chart (known correctness issues below)** ([`frontend/components/binder/portfolio-value-chart.tsx`](frontend/components/binder/portfolio-value-chart.tsx), [`backend/app/services/portfolio_service.py`](backend/app/services/portfolio_service.py)):
    - Aggregates portfolio market value from cached provider observations using multi-currency formatting (`USD`, `EUR`, `JPY`, `GBP`; fixed conversion rates) and rolling `AnimatedNumber`.
    - Computes 24h, 7d, and 30d value deltas ($ and %) and highlights the Crown Jewel (highest-value card in the binder).
    - Interactive `Recharts` ComposedChart styled in a white card chassis with historical portfolio valuation curves, timeframe filters (`7D`, `1M`, `3M`, `1Y`, `ALL`), SVG emerald gradient fill, dotted crosshair, and date scrubbing.
    - Single-roundtrip batch backend endpoint `POST /cards/portfolio-valuation` with Redis caching (`cardboarddex:portfolio:{hash}`, TTL 300s) and resilient client-side fallback hydration ([`frontend/lib/portfolio.ts`](frontend/lib/portfolio.ts)).
  - **Interactive Pocket Sleeves & Card Picker Spotlight Modal** ([`frontend/components/binder/binder-sleeve-slot.tsx`](frontend/components/binder/binder-sleeve-slot.tsx), [`frontend/components/binder/card-picker-modal.tsx`](frontend/components/binder/card-picker-modal.tsx)):
    - Empty pockets feature dashed slot indicators and glowing `+ Insert Card` actions.
    - Filled pockets display cards with full 3D `HoloCard` tilt perspective and rarity-reactive foil shaders, slot ribbons, live market price tags, and drag-and-drop reorganization between slots.
    - Spotlight modal with debounced search across the ingested card catalog, quick-filter chips (*Charizard*, *Pikachu*, *Gengar*, *Grails $100+*, *Under $20*), language toggles, and 1-click slot insertion.
  - **Top-Right Toolbar & Card Detail Integration** ([`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx), [`frontend/components/binder/add-to-binder-button.tsx`](frontend/components/binder/add-to-binder-button.tsx), [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx)):
    - Positioned as a dedicated top-right action button in the header toolbar, intentionally isolated from the central page navigation links and replacing the static "TCG & eBay Comps" badge. Features a 9-pocket binder icon, text label, and dynamic card count badge (e.g. `Binder 2`).
    - Integrated `<AddToBinderButton>` on card detail pages (`/cards/[id]`) and fallback view with quick-add to next available slot and in-binder slot badge.

- **Interactive Micro-Animations & Productivity Quality of Life (QoL) Suite**:
  - **Holographic Foil 3D Tilt Effect & Rarity-Reactive Shaders on Card Hover** ([`frontend/components/ui/holo-card.tsx`](frontend/components/ui/holo-card.tsx)):
    - Integrated across all card grids in [`frontend/components/card-grid.tsx`](frontend/components/card-grid.tsx), [`frontend/components/pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx), and the hero card on [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx).
    - Mouse-driven 3D card tilt using CSS perspective (`perspective: 800px; transformStyle: preserve-3d`) calculating dynamic `rotateX`, `rotateY`, and `scale3d(1.025)`.
    - **Rarity-Reactive Foil Shaders**: Automatically adapts foil patterns based on card rarity:
      - **Gold / Secret / Hyper Rare**: Warm radiant metallic gold sheen (`#ffd700`, `#ffaa00`, `#ffe680`).
      - **Cosmic Starburst (Special Illustration Rare / Illustration Rare / Art Rare)**: Twinkling celestial starfield with chromatic dispersion.
      - **Ultra / Laser Prism (Ultra Rare / Full Art / VMAX / VSTAR / ex)**: High-contrast diagonal laser spectrum beams.
      - **Classic Holo / Reverse Holo**: Smooth prismatic rainbow sweep.
      - **Satin Glare (Common / Uncommon / Standard)**: Clean soft white specular spotlight without rainbow tints.
  - **Pokémon Type-Themed Atmospheric Ambient Lighting** ([`frontend/app/pokemon/[id]/page.tsx`](frontend/app/pokemon/[id]/page.tsx)):
    - Multi-stop atmospheric gradient lighting tuned to canonical primary and secondary Pokémon types (e.g. Charizard warm ember, Gengar phantom violet, Blastoise oceanic cyan).
    - Features glowing accent border bar, ambient radial spotlight mesh across the hero canvas, and a floating dual-tone glowing podium behind the official artwork.
  - **Interactive Price Chart Area Glow, Dotted Crosshair & Smooth Curve Animations** ([`frontend/components/price-history-chart.tsx`](frontend/components/price-history-chart.tsx)):
    - Upgraded from static `LineChart` to interactive `ComposedChart` with SVG linear gradients (`#rawGradient` with soft 16% emerald area fill).
    - Enabled smooth 700ms cubic-bezier curve draw-in animations (`isAnimationActive={true}`).
    - Added a dotted vertical crosshair line (`strokeDasharray: "3 3"`) and active dots with drop-shadow for interactive date scrubbing.
  - **Species Trading Cards View Parity & Skeleton Cascades** ([`frontend/components/pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx)):
    - Upgraded card grid on `/pokemon/[id]` to use `HoloCard` with rarity foil shaders, multi-currency switching via `useCurrency()`, staggered cascade entrance (`animate-card-cascade`), and base64 SVG shimmer blur placeholders (`shimmerBlurDataUrl`).
    - Replaced generic spinner box with 6-card staggered cascading skeletons during filter and sort updates.
  - **Staggered Card Grid & Table Entrance Cascade**:
    - Added `@keyframes card-cascade` and `.animate-card-cascade` using spring cubic-bezier easing (`300ms cubic-bezier(0.16, 1, 0.3, 1) backwards`) in [`frontend/app/globals.css`](frontend/app/globals.css).
    - Applied staggered `animationDelay` across [`card-grid.tsx`](frontend/components/card-grid.tsx), [`card-table-view.tsx`](frontend/components/card-table-view.tsx), [`pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx), and [`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx), preventing abrupt content popping.
  - **Dynamic Rolling Number Count-Up for Telemetry Stats** ([`frontend/components/ui/animated-number.tsx`](frontend/components/ui/animated-number.tsx)):
    - Smoothly transitions numeric values using `requestAnimationFrame` and an ease-out cubic curve (`1 - (1 - progress)^3`).
    - Respects `prefers-reduced-motion` and supports custom formatters (multi-currency, percentages, and compact abbreviations).
    - Integrated for Set Totals in [`catalog-browser.tsx`](frontend/components/catalog-browser.tsx), Top Surge %, Steepest Drop %, Gainers, and Drops in [`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx), and Tracked Volume & Comps count in [`top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx).
  - **Catalog Dual-Handle Price Range Slider & Backend Price Filtering**:
    - **Dual-Handle Range Slider** ([`frontend/components/ui/price-range-slider.tsx`](frontend/components/ui/price-range-slider.tsx)): Features two draggable styled dots on both ends ($1 to $5,000+ / Any) operating across 12 non-linear stepped price milestones (`[1, 10, 25, 50, 100, 150, 200, 250, 500, 1000, 2500, 5000]`), enabling fine-grained price selection across both budget and mid-tier brackets ($10, $25, $50, $100, $150, $200, $250) while scaling up to grails ($1,000, $2,500, $5,000+). Includes connecting emerald highlight bar, pointer capture dragging, keyboard navigation (`ArrowLeft`/`ArrowRight`/`Home`/`End`), dynamic currency-aware readout badge (`All Prices`, `Under $25`, `$10 – $50`, `$100 – $200`, `$100+`), and milestone tick labels.
    - **Sidebar Integration & Quick Filter Sync** ([`frontend/components/catalog-browser.tsx`](frontend/components/catalog-browser.tsx)): Positioned in the sidebar filter panel; bi-directionally synchronizes with Quick Filter chips (`Under $10`, `$10 – $50`, `$100+ Grails`, `All`) and browser URL query parameters (`?min_price=X&max_price=Y`).
    - **Server-Side Price Querying & Pagination** ([`backend/app/routers/cards.py`](backend/app/routers/cards.py), [`backend/app/services/catalog_service.py`](backend/app/services/catalog_service.py)): Supported `min_price` and `max_price` query parameters in `GET /cards/search` and `GET /cards/sets/{set_id}/stats`, executing database-level subquery filtering on latest market prices with Redis caching and live Set Total price aggregation.
    - **SSR Pre-Fetching** ([`frontend/app/catalog/page.tsx`](frontend/app/catalog/page.tsx)): Pre-fetches filtered cards and set statistics on server components for bookmarked or shared URLs without layout shift.
  - **Quick Filter Chips for Catalog & Movers**:
    - **Catalog Browser** ([`catalog-browser.tsx`](frontend/components/catalog-browser.tsx)): 1-click price filter pills (`All Cards`, `Under $10`, `$10 – $50`, `$100+ Grails`, `Illustration / Specials`) filtering cards through the catalog query state.
    - **Market Movers** ([`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx)): 1-click velocity filter pills (`All Movers`, `Mega Surge (+25%+)`, `Steep Dips (-15%+)`, `High Value ($50+)`, `Budget (<$15)`).
  - **Global Command Palette (`Cmd + K` / `Ctrl + K`)** ([`frontend/components/command-palette.tsx`](frontend/components/command-palette.tsx)):
    - Full-screen spotlight modal listening for `Cmd + K`, `Ctrl + K`, or clicking the header search shortcut.
    - Direct route navigation (`Pokédex`, `Catalog`, `Movers`, `Sealed`, `Grading`, `Trending`, `Live Comps`).
    - Multi-Currency switching (`USD`, `EUR`, `JPY`, `GBP`) directly inside the palette.
    - Live instant Pokémon species search matching against `POKEDEX_DATA`.
    - Live debounced card search via `searchCards()` with thumbnails and real-time market prices.
    - Full keyboard navigation (`↑`, `↓`, `Enter`, `Esc`). Mounted globally in [`frontend/app/layout.tsx`](frontend/app/layout.tsx) with a trigger badge in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx).
  - **High-Density Trader Table View**:
    - Created [`frontend/components/card-table-view.tsx`](frontend/components/card-table-view.tsx) providing a compact, 50px-height tabular view (Rank, Thumbnail, Title & Set, Rarity, TCG Market Value, Last Updated, and Quick Comp Links).
    - Toggleable between Visual Cards and Trader Table in [`catalog-browser.tsx`](frontend/components/catalog-browser.tsx) and [`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx), persisting in `localStorage`.
  - **Multi-Currency Switcher**:
    - Implemented [`frontend/context/currency-context.tsx`](frontend/context/currency-context.tsx) supporting `USD` ($), `EUR` (€), `JPY` (¥), and `GBP` (£) with localized formatting and persistence in `localStorage`.
    - Integrated selector in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) and connected site-wide across all cards, deltas, and aggregated set totals.
  - **Sliding Gliding Pill Navigation Header**:
    - Hardware-accelerated sliding background pill in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) that glides to destination buttons with responsive resize tracking.

- **Responsive page controls and independent product loading (local, 2026-10-12; not deployed)**:
  - Catalog, sealed signals, market movers, grading, trending, and live updates render their interactive headings/search/filter controls without awaiting backend product data in the route. Products load in the browser with visible in-section loading text; initial pending requests no longer flash empty grids. Existing route loading files cover route-code delivery, not product fetching.
  - Catalog uses one debounced card-request flow instead of overlapping mount/filter requests. Set options and set statistics load independently of cards; set-option loading/failure, product failure, and retry are explicit. Obsolete card/stat responses cannot replace newer filters. Dashboard foreground requests also protect current filters from older responses; sealed columns retain their independent loading and retry behavior.
  - Card detail navigation renders outside its data boundary; metadata and pricing requests start together but pricing streams in separately. Pokémon cycling navigation and card filters render independently of the PokéAPI hero; species cards load client-side and preserve the referral parameter. Home market/release loading labels are now visible as well as accessible.
  - No backend/schema, provider-ingestion, deployment, or navigation-prefetch policy changes. Browser-fetched catalog/ranking results require JavaScript and browser API connectivity; these grids are no longer included in initial server HTML. This removes API waits from controls, not underlying API latency, and makes no claim about measured production speed.
  - Verification: 92 frontend tests passed, including eight new delayed-API/control, catalog request-count/stale-response, and grading retry tests; TypeScript and production build passed. Local production-build browser checks held API responses pending across all six listing/dashboard routes at 390px and 1440px: headings/navigation/search remained available, result loading text was visible, no horizontal overflow, and zero browser exceptions. Detail streaming was build-checked, not tested against delayed production services. Existing Edge Runtime deprecation warnings remain.

- **Cloudflare Pages Production Resilience & Error Isolation**:
  - Live production frontend deployed at `https://cardboarddex.app` and `https://cardboarddex.pages.dev`.
  - Added smart API endpoint resolution in [`frontend/lib/api.ts`](frontend/lib/api.ts) and [`frontend/next.config.ts`](frontend/next.config.ts): production targets `https://api.cardboarddex.app` through Cloudflare Tunnel, including when a stale Pages environment variable still supplies the generated AWS URL. Local development retains `http://localhost:8000`; generated `*.on.aws` image access has been removed.
  - Dynamic API URL resolution with trailing slash normalization inside `request<T>()`, `getCard()`, `getCardPricing()`, `trackUserAction()`, and `cardImageUrl()` prevents stale module-level hostnames in edge/serverless runtimes.
  - Added [`frontend/components/card-detail-client-fallback.tsx`](frontend/components/card-detail-client-fallback.tsx) with client-side fallback hydration: if Edge SSR encounters a network or runtime error, the card profile dynamically loads data and pricing comps directly from the browser rather than failing with a hard 404 `notFound()`.
  - Listing/dashboard routes now fetch products client-side on mount as described above; card details retain a browser fallback after server-fetch failure.
  - Instant default load for Live Comps ([`live-updates-dashboard.tsx`](frontend/components/live-updates-dashboard.tsx)): removed the first-mount skip guard so recent comps load immediately on initial page open rather than waiting 15 seconds or requiring filter interaction.
  - Implemented comprehensive error boundary in [`frontend/app/error.tsx`](frontend/app/error.tsx) with technical details toggle, direct action buttons (`Retry Action`, `Reload Application`, `Return to Pokédex`), and API health status check.
  - Listing/dashboard API errors stay within the rendered page. Card detail server-fetch failures render a browser retry fallback.
  - Disabled navigation prefetching (`prefetch={false}`) in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) to prevent burst 404 / RSC fetch floods on Cloudflare Pages edge, and added `wrangler.toml` specifying `compatibility_flags = ["nodejs_compat"]`.

- **Card Detail ➔ National Pokédex Species Bridge**:
  - Added `findPokemonForCardName()` in [`frontend/lib/pokedex-data.ts`](frontend/lib/pokedex-data.ts) matching card names to canonical Pokédex species entries.
  - Integrated into [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx) with hero species badge (`[#0002 Ivysaur] →`), dedicated `Pokédex (Ivysaur)` action button, and a new `Pokédex Species` row in the specifications table linking directly to `/pokemon/[dex_id]`.
  - Updated logo avatar in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) from `"T"` to `"CD"` (CardboardDex).
  - Guarded client-side `getCardSets()` in [`frontend/components/catalog-browser.tsx`](frontend/components/catalog-browser.tsx) to eliminate redundant set re-fetching on mount, and added 24-hour ISR caching in [`frontend/lib/api.ts`](frontend/lib/api.ts).

- **"Shop on eBay" Direct Marketplace Routing**:
  - Built reusable [`components/shop-ebay-button.tsx`](frontend/components/shop-ebay-button.tsx) featuring a custom 4-color vector eBay logo (`e` red, `b` blue, `a` yellow, `y` green) and white background with a crisp black border (`bg-white border border-black`).
  - High-intent query builder `buildEbaySearchUrl()` intelligently formats queries:
    - Singles: combines `"Pokemon"`, card name, card number with set total (e.g., `199/165`), and set name.
    - Sealed products: strips dummy card numbers (`#`, `N/A`) and generates clean queries.
  - Integrated primary hero button on the card profile page ([`app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx)) and companion button in the price dashboard header ([`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx)).

- **Top 50 Volume Page Direct Pokédex & Card Showcase Navigation**:
  - Clicking any Pokémon icon or name on the Top 50 volume leaderboard ([`components/top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx)) now navigates directly to `/pokemon/[dex_number]` (e.g. `/pokemon/6`), matching the Pokédex page behavior.
  - Displays the full species profile, audio cry, stats, and `<PokemonCardsView>` containing all matching database trading cards with set filters and price comps.
  - Added universal `← Back` navigation in [`components/back-to-pokedex-button.tsx`](frontend/components/back-to-pokedex-button.tsx).

- **Card Profiles Raw eBay Isolation, Volatility Metric & Multi-Series Chart**:
  - Strictly isolated card profile telemetry cards (`Lowest Verified (Raw)`, `Avg Listing (Raw)`, and `Median Listing (Raw)`) in [`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx) to raw (ungraded) eBay listing observations, removing catalog estimates and graded slabs from the raw-listing baseline.
  - Replaced legacy "Store Buylist" with a quantitative **"Volatility"** metric calculating seller asking-price dispersion ($CV = \sigma / \mu \times 100\%$) alongside standard deviation ($\sigma = \$X.XX$) and financial risk classification (`Low`, `Moderate`, `High`).
  - Upgraded [`components/price-history-chart.tsx`](frontend/components/price-history-chart.tsx) to support 4 synchronized, color-coded lines across dates:
    - 🟢 **Raw eBay Listings** (`#10b981`, Emerald)
    - 🟣 **TCG API Updated Listing** (`#8b5cf6`, Violet)
    - 🟡 **PSA 10 eBay Listings** (`#f59e0b`, Amber)
    - 🔵 **PSA 9 eBay Listings** (`#0284c7`, Sky Blue)
  - Implemented **dynamic Y-axis scaling** based on displayed lines with $\ge 2$ points, preventing isolated 1-point outliers from compressing the scale of primary lines.
  - Added **continuous forward-filling** to today's date (`today`) so every active line extends cleanly to the present until updated, including single-point series.
  - Implemented `<MultiLineTooltip />` displaying all active series simultaneously on hover with individual color dots and formatted currency amounts, ordered hierarchically from PSA 10 eBay at the top down to Raw eBay at the bottom.
  - Added an interactive timeframe filter button group directly below the chart with instant client-side date slicing for **1 Month (1M)**, **3 Month (3M)**, and **1 Year (1Y)**, with left-edge baseline anchoring.
  - Added interactive sorting for the "Latest variants & pricing data" table allowing one-click sorting by **Date**, **Price**, **Printing Name** (A–Z / Z–A), and **Variant / Condition** with bidirectional toggles (`↑` / `↓`), quick filter toolbar buttons, and clickable table headers.
  - Set `export const dynamic = "force-dynamic"` on [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx) to request dynamic rendering. Backend response caching and the browser memory cache can still delay updates.

- **Card Profiles "Avg Listing Price" KPI & Clean Variant Tables**:
  - Replaced legacy "Lowest w/ Shipping" card in [`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx) with a high-fidelity **"Avg Listing Price"** (Average Asking Price) metric card.
  - Dynamically calculates the arithmetic mean across title-matched eBay listing observations with a real-time listing count badge (e.g. "Mean of 21 active eBay listings"), gracefully falling back to TCG active listing estimates or backend `avg_listing_price`.
  - Cleaned the variants table column from "Lowest / Shipping" to "Lowest Price", stripping shipping clutter from card profiles.
  - Added `avg_listing_price` field to `CardPricingResponse` in [`backend/app/schemas/cards.py`](backend/app/schemas/cards.py) and [`backend/app/routers/cards.py`](backend/app/routers/cards.py) with backend unit tests.

- **Frontend Shared Primitives & Bundle Optimization**:
  - Reusable UI primitives under `frontend/components/ui/`:
    - [`back-to-top.tsx`](frontend/components/ui/back-to-top.tsx): Floating glassmorphic "Go to top" button with smooth scrolling and responsive scroll threshold.
    - [`infinite-scroll-sentinel.tsx`](frontend/components/ui/infinite-scroll-sentinel.tsx): `IntersectionObserver`-backed streaming pagination sentinel with manual load more fallback and end indicator.
    - [`search-input.tsx`](frontend/components/ui/search-input.tsx): Monospace search bar with vector search icon, hotkey indicator, and instant clear button.
    - [`empty-state.tsx`](frontend/components/ui/empty-state.tsx) and [`stat-kpi.tsx`](frontend/components/ui/stat-kpi.tsx): Uniform terminal telemetry cards and empty states.
  - Centralized query parameter serialization in `frontend/lib/api.ts` via `buildQueryString()`.
  - Extracted featured Pokémon into `frontend/lib/featured-pokemon.ts` to keep the landing page's featured-data dependency small.

- **Unified Infinite Scroll Pagination (Catalog Standard)**:
  - Replaced legacy button paginations with continuous infinite scrolling across all 5 major data feeds:
    1. **Card Catalog** (`/catalog`)
    2. **Market Movers** (`/market-movers`)
    3. **Sealed Investment Signals** (`/sealed-signals`)
    4. **Grading Profitability** (`/grading-profit`)
    5. **Live Comps & Ingestion Feed** (`/live-updates`)
  - Features automatic background fetching via `IntersectionObserver` (320px root margin) with manual fallback buttons.

- **Theme Alignment & Minimalist Redesign (Movers, Sealed, Grading)**:
  - Aligned Market Movers, Sealed Signals, and Grading Profitability to the landing page's minimalist terminal aesthetic:
    - `font-mono` typography and light `bg-[#f7f8f6]` canvas.
    - Status headers with pulsating emerald indicators (`MOMENTUM RADAR`, `INVESTMENT SIGNALS`, `ARBITRAGE CALCULATOR`).
    - 4-card telemetry KPI grids matching landing page `PLATFORM_STATS`.
    - Stripped word bloat, marketing slogans, bulky black callouts, and rotated promotional ribbons in favor of sleek, data-dense cards.

- **Discovery homepage (local, 2026-10-12; not deployed)**:
  - [`landing-page.tsx`](frontend/components/landing-page.tsx) uses a shorter search-first hero, dated Market today highlights, a horizontal English/Japanese release browser with separate Released/Upcoming tabs, six visual tool previews (Movers, Sealed, Binder, Catalog, Grading, Pokédex), featured species, and lower-page database coverage counts. Hover movement respects reduced motion. The search popup can extend outside the hero; only decorative backgrounds are clipped. The shared header now fits narrow screens and uses the scrolling navigation row below 1280px.
  - New database-only `GET /home/overview` ([service](backend/app/services/home_service.py), [router](backend/app/routers/home.py)) uses a bounded five-minute in-process cache and serializes cache rebuilds per process. It reads each product's latest ungraded USD TCG API observation, selects positive card/sealed growth and negative card declines by the provider's reported 30-day change, and shows actual price/observation dates, including stale/unknown states. It does not substitute weekly changes or invent chart data. Only cached history for the selected products is loaded. Highlights represent latest available observations, not a guarantee of current-day prices.
  - Releases include up to eight released and two upcoming sets per language (upcoming within 180 days), with actual set dates, local product counts, and representative product artwork. Undated sets are omitted. Stats count catalog products, sets, and price observations; price records are not completed sales. Hardcoded totals, ingestion cadence claims, and the live-status badge were removed; metadata and footer now describe active eBay listing comparisons accurately.
  - [`recently-viewed.ts`](frontend/lib/recently-viewed.ts) shows up to 12 unique successful card views from the past 30 days, using browser storage (`cardboarddex_recently_viewed_v1`) and including both server-rendered and client-fallback card details. It stores display metadata and view time, not price snapshots; handles malformed/restricted storage; responds to cross-tab clearing; and offers Clear history without altering binders. Expired entries are excluded on read and pruned on the next recorded view.
  - Homepage data loads after the static search shell, with loading, empty, unavailable, and retry states. No upstream provider requests or ingestion restarts are needed. Deploy the API before the frontend; cached history reads require the previously added `0007_market_data` migration. No additional migration or Cards/Sets changes were introduced.
  - Verification: 224 backend tests passed (16 skipped), 62 frontend tests passed, TypeScript and production build passed. Isolated Chrome checks with a temporary SQLite test catalog verified widths 320/390/768/1024/1440, release filters, the search overlay, and card-detail → recently viewed → clear history, with no browser runtime exceptions. Production-scale PostgreSQL timing was not measured; existing framework deprecation warnings remain.

- **National Pokédex Browser (Dedicated Route `/pokedex`)**:
  - Hosted at `/pokedex` ([`app/pokedex/page.tsx`](frontend/app/pokedex/page.tsx)) and powered by [`components/pokedex-browser.tsx`](frontend/components/pokedex-browser.tsx), cataloging all **1,025 Pokémon** across **9 generations** (Gen I Kanto through Gen IX Paldea).
  - Built with canonical static registry ([`lib/pokedex-data.ts`](frontend/lib/pokedex-data.ts)) and direct PokéAPI client ([`lib/pokeapi.ts`](frontend/lib/pokeapi.ts)) with 24-hour Next.js ISR caching (`revalidate: 86400`).
  - **Single-Page Progressive Loading / Infinite Scroll**: Smooth progressive streaming using `IntersectionObserver`, dynamic batch expansion, animated progress bar ("Showing X of Y Pokémon"), "Load More" action, "Show All" instant expander, and shared `<BackToTop />`.
  - **Generation Section Dividers**: Visual full-width divider banners separating each generation with Roman numeral badges, Dex # range, and Pokémon counts.
  - Interactive generation tabs, 18 type filter pills, instant search (name or #dex number), and sorting by Dex # or Name.
  - **Evolution Family Search & Topological Grouping**:
    - Powered by a canonical static evolution registry ([`lib/pokemon-evolutions.ts`](frontend/lib/pokemon-evolutions.ts)) covering all **1,025 Pokémon** across **541 evolution families**.
    - When searching, direct query matches expand to include the entire evolution line (pre-evolutions and evolutions), seamlessly handling cross-generation evolutions (e.g. *Mankey* -> *Primeape* -> *Annihilape #979*, *Eeveelutions*, *Applin*, *Kleavor*).
    - In default Dex sorting (`Dex # (Low → High)`), family members are sequentially grouped in stage order (Root/Baby → Stage 1 → Stage 2) at the primary match's index (e.g., *Pichu #172* is placed alongside *Pikachu #25* and *Raichu #26*).
    - **Interactive User Toggle**: Control bar features an `Evolutions` toggle button (`showEvolutions`, default ON, URL synced with `?evo=0`) allowing users to toggle between full evolution families and strict direct name matches.
    - **Visual Stage Badging**: Search cards display clean, styled status badges: `★ Direct Match (Stage Name)`, `Pre-Evo (Stage Name)`, and `Evolution (Stage Name)`.
    - **Generation Divider Guard**: Suppresses inter-generation divider headers during active evolution searches so family cards stay grouped cleanly without section breaks.

- **Dedicated Pokémon Detail & Trading Cards Showcase (`/pokemon/[id]`)**:
  - Route `/pokemon/[id]` ([`app/pokemon/[id]/page.tsx`](frontend/app/pokemon/[id]/page.tsx)) provides a rich species profile combining PokéAPI data with CardboardDex trading cards.
  - **Pokédex Profile Sequential Cycling & Flanking Arrows** ([`components/pokemon-cycle-nav.tsx`](frontend/components/pokemon-cycle-nav.tsx)):
    - Flanking interactive arrow buttons (`<PokemonArrowButton />`) positioned directly to the left and right of the Pokémon artwork with hover preview tooltips (sprite thumbnail, Dex #, and name).
    - Top breadcrumb cycling header (`<PokemonCycleHeader />`) featuring previous Pokémon (`← #0005 Charmeleon`), direct Pokédex list link, and next Pokémon (`#0007 Squirtle →`).
    - Seamless continuous wrap-around between #1 (Bulbasaur) and #1025 (Pecharunt).
    - Keyboard shortcut cycling (`<PokemonKeyboardCycle />`): press `ArrowLeft` or `ArrowRight` to cycle adjacent profiles instantly without mouse interaction (auto-bypassed when focused in search or input fields).
  - **Hero & Species Profile**: High-resolution official artwork, English/Japanese naming, genus, height, weight, canonical Pokédex flavor text, and base stats BST breakdown.
  - **Interactive Audio Cry Player** ([`components/pokemon-audio-player.tsx`](frontend/components/pokemon-audio-player.tsx)): Plays authentic Pokémon game cries with animated equalizer bars.
  - **Displayed-card summaries (local update 2026-10-12)**: Count, highest-value individual card (with a link), and total displayed price are calculated from the currently visible card list, without separate database summary requests. Search and visibility changes update these immediately. Missing prices are excluded from the sum and reported; zero prices remain valid. These describe the loaded, filtered list (currently up to 100 products), not the entire catalog.
  - **Trading Cards Grid** ([`components/pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx)): Pokémon cards with set filtering, sorting, language selection, and a **Show/Hide sealed products** button, hidden by default. Visibility is shareable through `hide_sealed=false`. Sealed detection follows the existing catalog convention (empty/null/`None` rarity); highest-value card always excludes sealed products. Obsolete filter responses are ignored, and failed refreshes preserve prior results with a retry button. Six focused frontend tests cover summaries, visibility, navigation, response races, missing prices, and recovery.

- **Card Profile Set Navigation & Direct Catalog Routing (`/cards/[id]`)**:
  - In [`app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx), made the set identity interactive across the entire card profile:
    - Clickable category set badge above the card title (`[SET_NAME] →`) linking to `/catalog?set=[set_id]`.
    - Dedicated hero action button: `Browse Set ([SET_NAME])` alongside `Shop on eBay` for immediate collection discovery.
    - Clickable Set row in the specifications table linking directly to the set's cards.
    - Added `findPokemonForCardName()` in [`lib/pokedex-data.ts`](frontend/lib/pokedex-data.ts) to resolve species names from card titles (stripping mechanics like *ex*, *vmax*, *vstar*, *tag team* and trainer prefixes) and provide a direct link to the corresponding `/pokemon/[dex_id]` profile.
  - Seamlessly pre-filters the catalog browser to the specific set, updates the set dropdown, and loads all corresponding trading cards.

- **Typography, Theming & Navigation Header**:
  - **IBM Plex Mono**: Applied globally across the application via Google Fonts preconnect in `app/layout.tsx` and custom typography styling in `app/globals.css`.
  - **Top Navigation Bar ([`components/nav-header.tsx`](frontend/components/nav-header.tsx))**:
    - **Sticky Minimalist Header on Scroll**: Uses `sticky top-0 z-40` with a dynamic scroll listener. At the top of the page, it remains seamless and opaque; as the user scrolls down, it smoothly transitions to a minimalist frosted-glass surface (`bg-white/92 backdrop-blur-md shadow-2xs border-slate-200`) that follows the page without obstructing content.
    - Stripped all unicode emojis to harmonize with the technical terminal/monospace design language.
    - Centered navigation links with clean, uppercase monospace titles: `POKÉDEX`, `CATALOG`, `MOVERS`, `SEALED`, `GRADING`, `TOP 50`, and `LIVE COMPS`.
    - Crisp SVG icons replace unicode emojis across all search inputs, filter sections, button labels, and empty states.

- **Catalog & Set Foundation (English & Japanese)**:
  - Catalog and pricing integration is consolidated under `backend/app/tcgapi/`.
  - TCG API supplies Pokémon sets, cards, image URLs, and per-printing market prices for both English (`game=pokemon`) and Japanese (`game=pokemon-japan`) expansions.
  - Catalog supports English and Japanese data; dated local/production inventory snapshots are retained in Deployment status below.
  - Code cards are automatically excluded from catalog search and browsing.
  - Unrated / sealed items hidden by default (`hide_sealed=true`), with an interactive sidebar toggle.
  - Catalog sorting supports `price_desc` (default), `price_asc`, `number_asc`, `number_desc`, `name`, and `set`.
  - **Filtered Set Total Price Tag**: Added real-time set market value aggregation (backend endpoint `GET /cards/sets/:id/stats` with Redis 300s cache) and interactive terminal telemetry tag in the top right of the cards view on `/catalog`. Displays complete set dollar value (or filtered subquery total), active priced card ratio (e.g. `165/165 priced`), and average card price tooltip, with SSR pre-fetching in `app/catalog/page.tsx` for instant zero-layout-shift rendering.

- **Expected Grading Profitability Tab ([`components/grading-profit-dashboard.tsx`](frontend/components/grading-profit-dashboard.tsx))**:
  - Backend endpoint `GET /cards/grading-profit` calculates estimated spreads, profit ($), and ROI (%) between raw observations and PSA 10 / PSA 9 asking-price comps. Fixed probabilities and omitted costs limit the model; see open work.
  - Interactive Grading Fee simulator with live fee slider ($10–$100) and instant presets ($15, $19, $25, $50, $75).

- **Quantitative Sealed Investment Signals Tab ([`components/sealed-signals-dashboard.tsx`](frontend/components/sealed-signals-dashboard.tsx))**:
  - Heuristic analytics engine powered by `GET /cards/sealed-signals`.
  - Local remodel (2026-10-11, not deployed): separate newer (under three calendar years) and older/vintage (three years or more) rankings, based on set release dates. Unknown/future dates are excluded from these columns; age does not establish print status. New `era=all|newer|older` API filter runs before pagination, with separate cache keys. Existing clients default to `all`.
  - Theme alignment (2026-10-12, local; not deployed): follows Trending’s white page, light-gray ranking columns, compact bordered white rows, monospace typography, and 1600px dashboard width. The heading uses title case; filters sit between subtle dividers instead of a separate raised panel. Rows keep product identity, market price, and selected-period growth visible; price history, freshness, signal score, listing details, and purchase-return calculator sit inside a collapsed per-product disclosure. Newer/older columns, language/period controls, advanced filters, URL state, and independent pagination remain. Loading skeletons match the compact layout. Verification: seven sealed-page tests and production build (including TypeScript) passed; browser checks with fixture products passed at 320/390/768/1024/1440px, including details/filter expansion, with no horizontal page overflow or browser exceptions. Existing Edge Runtime warnings remain; live API/inventory was not verified by the fixture checks.
  - Language filter (2026-10-11, local): visible All / English / Japanese toggle applies to both eras, resets column pagination, and persists through `game=all|pokemon|pokemon-japan` URLs and browser navigation. Reset returns to All. API filtering occurs before counts, rankings, and pagination, with language-specific cache keys; classification uses the same `Set.series == "Pokemon Japan"` marker as the catalog (other/null series are English). No schema changes. Verified 25 backend tests, 13 frontend tests, TypeScript, production build, and all six local era/language API combinations returning HTTP 200. Local totals: newer 531 English / 67 Japanese; older 1,851 English / 119 Japanese. Deploy backend support before the frontend toggle.
  - Default ranking is observed 30-day percentage price growth before fees, not projected ROI or the heuristic score. Valid zero returns remain zero; unavailable returns sort after negative returns without substituting weekly growth. Each column has independent pagination, loading, empty, and retry states. Search/type controls remain visible; signal and sort controls are expandable, with URL persistence and reset. Desktop columns stack on mobile. Product rows show currency-aware market prices and selected-period growth, with secondary metrics available in expandable details.
  - Verification: 47 frontend tests, 206 backend tests (16 skipped), TypeScript, and production build passed locally. Existing Edge Runtime, Starlette, and Alembic deprecation warnings remain. API follow-up recommendations: [TCG API opportunities](docs/tcgapi-opportunities.md).
  - Deploy the backend era filter before the new frontend; an older API ignores unknown query parameters and would otherwise return the same global list for both columns. No Cards/Sets schema changes or ingestion restarts are required.
  - Deterministic 4-factor scoring model: Supply Scarcity (30%), Buylist Liquidity (25%), Momentum Velocity (25%), and Set Age (20%).
  - Buy signals: `STRONG BUY` ($\ge 75$), `BUY` ($60\text{--}74$), `HOLD` ($45\text{--}59$), `UNDERPERFORM` ($<45$).

- **Top 50 Trending Dashboard Tab ([`components/top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx))**:
  - Restructured 3-column layout powered by backend endpoints `GET /cards/trending`, `POST /cards/track-action`, and `POST /cards/trending/reset`.
  - **Column 1 (Trending Cards)**: Most searched and clicked trading cards, ranked by a blended score of real-time Redis clicks, price observation frequency, market value, and 7-day price movement.
  - **Column 2 (Popular Pokémon)**: Most searched and viewed Pokémon characters, ranked by user search heat, character click volume, and card catalog depth.
  - **Column 3 (Volume Leaders)**: Top Pokémon by summed observation value ($) with rolling timeframes (`24h`, `7d` default, `30d`, `all_time`, `2026_ytd`), observation count, and period-over-period momentum.
  - Responsive multi-column layout with view switcher (`All 3 Columns`, `Cards`, `Pokémon`, `Volume`), timeframe filter pills, and live search. Real user clicks and searches are tracked in Redis via `POST /cards/track-action`.
  - **Navigation Attribution**: Card detail GETs record views except when `?ref=trending`; explicit tracking uses `POST /cards/track-action`. Cached requests and untrusted clients limit how accurately these represent unique user activity.
  - **Pokédex Navigation Reset**: Tab switches reset scroll to `(0, 0)`; scroll position is only restored when returning directly from that Pokémon's profile page.

- **National Pokédex 1,025 Species Dataset & Card Attribution ([`common/pokemon_data.py`](backend/app/common/pokemon_data.py), [`services/catalog_service.py`](backend/app/services/catalog_service.py))**:
  - Centralized `POKEMON_DEX_NUMBERS` containing official Pokédex numbers for all 1,025 Pokémon species.
  - Helpers `get_pokemon_dex_number()`, `get_pokemon_canonical_name()`, and `get_pokemon_sprite_url()` resolve canonical species identity and construct official-artwork URLs.
  - Master regex matcher `match_to_pokemon()` matches card titles across all 1,025 Pokémon species sorted by length descending, ensuring multi-word and later-generation species (e.g. Zekrom #644, Rayquaza #384, Greninja #658) are correctly attributed without missing icons or `#0000` dex numbers.

- **Interactive Landing Page Live Search Autocomplete Dropdown ([`components/search-autocomplete.tsx`](frontend/components/search-autocomplete.tsx))**:
  - Replaced static search input in [`landing-page.tsx`](frontend/components/landing-page.tsx) with a responsive typeahead autocomplete dropdown.
  - Local clipping fix (2026-10-11): hero uses visible overflow and `z-10` so autocomplete extends over following sections; only the decorative glow is clipped in a separate noninteractive layer. Navigation (`z-40`) and command palette (`z-50`) remain above the hero. TypeScript and production build passed; browser visual verification was not run.
  - Categorizes results into three sections plus a full-catalog search action:
    1. **Pokémon Species**: Instant matching across all 1,025 Pokédex entries with official artwork thumbnail, name, Pokédex `#`, and elemental type badges.
    2. **Expansions & Sets**: Fast client-side matching across the fetched sets with representative booster/product artwork and series name.
    3. **Cards & Products**: Debounced API queries against `searchCards()` with card image and fetched market price.
    4. **Full Catalog Search Action**: One-click or Enter key submission to search the entire expansion catalog.
  - Backend endpoint `GET /cards/sets` enriched with representative product/card `image_url` for the fetched sets.
  - Complete keyboard accessibility (`ArrowDown`, `ArrowUp`, `Enter`, `Escape`) and click-outside dismissal.

- **Live Updated Items & Market Comps Tab ([`components/live-updates-dashboard.tsx`](frontend/components/live-updates-dashboard.tsx))**:
  - Backend endpoint `GET /cards/live-updates` streams all real-time price observations, title-matched eBay comps, graded slab asking-price observations, and TCG API price syncs in chronological order.
  - Auto-refresh ticker (15s polling with live pulse and pause/resume toggle).
  - Side-by-Side 2-column view with responsive toggle and floating Back-to-Top button.

- **Frontend Bundle Optimization & ISR Prerendering**:
  - **Dynamic Command Palette Code-Splitting** ([`frontend/components/command-palette-lazy.tsx`](frontend/components/command-palette-lazy.tsx), [`frontend/app/layout.tsx`](frontend/app/layout.tsx)): Deferred the large Pokédex dataset from initial page loads by dynamically importing `CommandPalette` on the client with `ssr: false`.
  - **Static Generation & ISR** ([`frontend/app/page.tsx`](frontend/app/page.tsx), [`frontend/app/pokedex/page.tsx`](frontend/app/pokedex/page.tsx)): Enabled static HTML prerendering on the homepage and 24h Incremental Static Regeneration (`revalidate = 86400`) on `/pokedex`. Actual latency depends on deployment and cache behavior.

## Backend, caching, and rendering details

### Route ownership and loading components

| Router | Public routes |
| --- | --- |
| `catalog.py` | `/cards/search`, `/cards/sets`, `/cards/sets/{set_id}/stats`, `/cards/pokemon/{name}` |
| `market.py` | `/cards/market-movers`, `/cards/grading-profit`, `/cards/sealed-signals`, `/cards/live-updates` |
| `analytics.py` | `/cards/top-pokemon-volume`, `/cards/trending`, `/cards/trending/reset`, `/cards/track-action`, `/cards/portfolio-valuation` |
| `cards.py` | `/cards/{card_id}`, `/cards/{card_id}/prices`, `/cards/{card_id}/image` |

- Business logic lives in catalog, grading, sealed, trending, and portfolio services. `cards.py` retains some compatibility re-exports; use the owning router/service for new changes.
- [page-loading-status.tsx](frontend/components/page-loading-status.tsx) and [section-loading-bar.tsx](frontend/components/section-loading-bar.tsx) provide shared status/progress visuals. Route `loading.tsx` files cover catalog, card/species detail, Pokédex, binder, and analytical dashboards; grid skeletons and client fallback states complement the route shells.
- [back-to-top.tsx](frontend/components/ui/back-to-top.tsx) supplies the floating scroll action across catalog, movers, grading, sealed, live updates, and Pokédex views. Species navigation also uses sessionStorage to restore its last viewed position.

### Catalog queries and cache layers

- Local implementation now uses `cardboarddex:responses:v1:*` and the bounded response coordinator; exact freshness/stale limits are in [performance notes](docs/performance.md). Earlier production cache names/lifetimes describe the pre-rollout implementation.
- Search and set statistics accept `min_price`/`max_price`, filter latest-price subqueries, and support server-rendered bookmarked URLs. Catalog search uses the composite observation index `ix_price_observations_search_lookup`.
- [api.ts](frontend/lib/api.ts) uses explicit browser endpoint lifetimes, a 64-entry cap, shared requests with independent cancellation, and original backend expiry timestamps. `no-store` is respected. Coordinated endpoints bypass Next server data caching; this new policy is local until deployed.
- [catalog-browser.tsx](frontend/components/catalog-browser.tsx) avoids an immediate redundant set fetch when SSR already supplied sets. [next.config.ts](frontend/next.config.ts) configures AVIF/WebP, qualities 70/75/80, and a minimum cache TTL of 2,678,400 seconds (31 days). SVG optimization is allowed with attachment disposition and a sandboxed image CSP; local-IP allowance is enabled only for the configured local API origin.
- `.card-cv` and `.table-row-cv` use `content-visibility: auto` to reduce offscreen work. [shimmer.ts](frontend/lib/shimmer.ts) generates base64 SVG blur placeholders.
- The catalog summary code assumes USD for TCG observations. Validate currency/printing consistency before broadening provider support.
- Redis-backed analytical caches use `cardboarddex:grading_profit:{hash}`, `cardboarddex:sealed_signals:{hash}`, and `cardboarddex:top_volume:{key}` with 300-second TTLs. Their local fallbacks currently have no eviction.

### Market, trending, and pricing responses

- Local market movers now cache combined database rankings by language/period through the response coordinator (15 minutes fresh, 30 minutes maximum age), with Redis rebuild coalescing and no provider calls.
- The old provider/fallback mover path has been removed locally. Stored observations require the requested period's explicit percentage; missing coverage stays empty. Legacy formatting exports are retained for compatibility but do not power this route.
- The local market-movers route no longer instantiates an interactive provider client or consumes provider quota. Existing ingestion quota handling is unchanged.
- Live updates aggregate provider/graded counts with a combined `CASE` query and Redis `cardboarddex:live_updates:kpi` (60 seconds). The unfiltered total count is also cached for 60 seconds.
- Card prices resolve each observation payload once via `_resolve_obs_payload()`/`_build_obs_item()`, exposing selected pricing fields rather than raw provider payloads.
- Latest-variant grouping includes `provider_card_id` to preserve distinct eBay listings. Raw asking-price averages use `_trim_outliers_iqr()` when enough observations exist.
- `GET /cards/{id}/prices` accepts a bounded `days` parameter, but observations with null `provider_updated_at` currently bypass the cutoff and response rows are not capped.
- Trending records card views/clicks, Pokémon activity, and search terms. In-memory tracking dictionaries have a 2,000-entry cap; Redis sorted sets are periodically trimmed. Cache invalidation uses `scan_iter()`, and `TrackActionRequest.entity_id` has length/pattern validation. These controls do not prevent fabricated activity or bound every analytical response cache.
- All eBay observations are asking-price comps. The UI's historical “sales” labels and volume calculations are documented limitations.

### Images and API protections

- `get_card_image()` validates card IDs against an alphanumeric/underscore/hyphen pattern with a 64-character maximum.
- With `S3_BUCKET_NAME`, it checks the public asset URL and returns a cacheable `307` redirect when present. Otherwise it fetches the provider image, synchronously uploads through a shared boto3 client, and returns the bytes.
- S3 keys are `cards/{card_id}.png`; stored Content-Type comes from the downloaded image. Asset responses use one-year immutable cache headers. Image URLs are stable rather than content-versioned.
- Missing/broken images use a local SVG placeholder and Redis `cardboarddex:broken_img:{card_id}` for 24 hours. Failed requests can therefore continue showing placeholders until expiry.
- [sync_images_to_s3.py](backend/jobs/sync_images_to_s3.py) uses a thread pool for download/upload work. Options include `--limit`, `--all`, `--set-id`, `--workers`, `--overwrite`, `--bucket`, and `--region`; there is no `--concurrency` or `--card-id` option.
- TCG outbound calls use HTTPX connect/read/write/pool timeouts of 5/30/10/5 seconds; eBay uses 5/25/10/5. Requests retry selected 429/5xx failures with backoff. These are per-operation timeouts, not whole-job deadlines.
- The API's Redis rate limiter uses fixed windows; its in-memory fallback uses a sliding window. Images have a separate 6,000/minute bucket. Proxy-header trust and heavy-endpoint enforcement remain open issues.
- CORS uses exact configured origins plus an anchored production/preview/development regex. CORS does not authenticate non-browser clients.
- Successful API responses receive CSP, HSTS, nosniff, framing, and referrer headers. Generic 500 responses mask exception details while logging errors server-side. Frontend HTML needs its own policy.
- `POST /cards/trending/reset` requires `X-Admin-Token`; unconfigured admin access is disabled. Listing links are restricted to HTTP(S) and eBay/TCGPlayer domains.
- PostgreSQL pooling uses `pool_size=15`, `max_overflow=15`, `pool_timeout=5.0`, and `pool_recycle=1800`. Total connections still depend on process/task count.
- Public read routes set Cache-Control directives, but headers alone do not prove Cloudflare caches a response or establish a cache-hit percentage.

### Job durability and deployment mechanics

- Catalog ingestion checks existing observation fingerprints to avoid duplicate inserts. Current tables separate catalog identity, provider state, normalized observations, and raw eBay listings; catalog schemas remain protected.
- Price batches prefer least-recently-synced cards. Manual CLI targeting supports canonical card IDs, card-name queries, and Pokémon species through `get_cards_for_pokemon()`, including name expansions and Mew/Mewtwo isolation.
- Scheduled pricing tasks expire after 860 seconds with an 840-second hard limit. Catalog sync expires after 3,540 seconds with a 3,480-second hard limit. Late acknowledgement/prefetch settings do not replace distributed overlap protection.
- The Dockerfile builds dependencies in a separate stage and runs the application as an unprivileged user. It can run FastAPI or a worker command supplied by Docker Compose.
- Prepared backend CI runs application/deployment tests, publishes an AMD64 SHA-tagged image, and deploys its digest with matching Compose configuration over verified SSH. It checks schema revision without applying migrations. The recovery image is active; source publication remains pending as recorded below.
- Frontend CI uses Node 22, `npm ci`, TypeScript checking, and a webpack production build. It currently omits `npm test`.
- Cloudflare Pages Git integration was previously configured with `@cloudflare/next-on-pages`; both Wrangler files name `.vercel/output/static` as the output and enable `nodejs_compat`. The adapter is not pinned in `frontend/package.json`; verify the live Pages build configuration before changing deployment tooling.
- `frontend/.npmrc` enables `legacy-peer-deps=true`, and `react-is` is an explicit dependency for Recharts compatibility.
- `/health?details=true` reports database/Redis connectivity, not latency or active connection counts. `/health/quotas` exists but reads keys inconsistent with the provider limiter.

## Provider and job behavior

### TCG API

[TCGAPIClient](backend/app/tcgapi/client.py) defaults to `https://api.tcgapi.dev/v1` with server-side `X-API-Key`. It calls `/sets`, `/sets/{id}/cards`, `/cards/{id}`, `/cards/{id}/prices`, `/prices/top-movers`, and `/bulk/prices`. Game identifiers are `pokemon` and `pokemon-japan`; canonical provider IDs identify catalog cards, with long IDs normalized by `local_card_id()`.

[Catalog sync](backend/jobs/sync_catalog.py) upserts sets/cards and stores pricing observations/provider state. Japanese sets use `series="Pokemon Japan"`. Pagination, deduplication, and Redis cursor helpers already exist; reliable per-page resumption remains unfinished. The quota-error path checkpoints the final selected set rather than the last successfully processed set. Also, `--all` currently passes `None` into a function that falls back to the configured set limit, so it does not guarantee an unlimited sync.

### eBay

[EbayClient](backend/app/ebay/client.py) uses OAuth client credentials and Browse item-summary search. Application tokens are shared through Redis. [collect_ebay_prices.py](backend/jobs/collect_ebay_prices.py) records raw listings and deduplicated observations after [title matching](backend/parsers/title_matcher.py). The matcher covers proxy/fake, lot, language, speculative grade, and sealed-product edge cases.

No completed-sales ingestion is implemented. Raw listing rows are updated on repeat ingestion; they are not an immutable event archive.

### Provider payloads and matching rules

TCG request details supported by the adapter:

| Endpoint | Parameters / behavior |
| --- | --- |
| `GET /sets` | `game`, `page`, `per_page`; pagination uses provider metadata or page length. |
| `GET /sets/{id}/cards` | Paginated card ingestion; attaches set identity to each record. |
| `GET /cards/{id}` | Provider card detail for identity/pricing ingestion. |
| `GET /cards/{id}/prices` | Optional `printing` filter. |
| `GET /prices/top-movers` | `game`, `direction`, `period`, `printing`, `type`, `limit`. |
| `GET /bulk/prices` | Comma-separated `ids`; batch size must respect the provider's current contract. |

- Pricing fields used include `printing`, `market_price`, `low_price`, `median_price`, `lowest_with_shipping`, `buylist_price`, `price_change_24h`, `price_change_7d`, `price_change_30d`, `total_listings`, and provider update timestamps.
- Printing values include Normal, Holofoil, Reverse Holofoil, 1st Edition, and Unlimited where provided. Missing fields/variants vary by card; do not assume every response contains them.
- The eBay OAuth endpoint is `https://api.ebay.com/identity/v1/oauth2/token`; Browse search is `/buy/browse/v1/item_summary/search`. The application-token Redis key is `cardboarddex:ebay:oauth_access_token`.
- Raw listings are stored in `raw_ebay_listings` (migration `0003_ebay_raw_listings.py`), including item ID, title, price/currency, listing URL, seller feedback, dates, match/rejection details, and raw payload. Matched observations retain source item identity and title-match metadata.
- The parser rejects proxies/fakes/custom cards, lots/bulk, digital codes, foreign-language mismatches, alterations/autographs, speculative grades such as “PSA 10?”, and empty/opened sealed products.
- Japanese targets receive `is_target_japanese`; `RE_NON_JAPANESE_FOREIGN` rejects other languages while permitting Japanese terms. `extract_core_card_name()` normalizes suffixes such as `Ivysaur - 002/165` and printing parentheticals such as Master Ball Pattern/Mirror Holofoil.
- Grading extraction supports PSA, BGS, CGC, and SGC. These are parsed seller claims, not independent grading-certificate verification.
- Sealed matching distinguishes booster boxes, ETBs, bundles, cases, tins, blisters, binder collections, and UPCs; isolates cases from single units and Pokémon Center variants; rejects single-promo extractions.
- Sealed observations use `variant_id=ebay:{card_id}:sealed` with sealed condition/printing. Raw/graded variants include company and grade/condition information.
- Direct eBay shopping queries combine “Pokemon”, card name/number, and set name; sealed queries omit dummy numbers. Listing URLs are surfaced through the detail dashboard's variants table.

### Scheduling and limits

[Celery Beat](backend/app/celery_app.py) schedules TCG price batches at minutes `:00/:30`, eBay batches at `:15/:45`, and both-game catalog sync at 03:00 UTC. These are batch schedules, not a promise that every card refreshes every 15 minutes.

Provider limits use Redis daily counters and per-second burst pacing; defaults are 2,000 TCG and 500 eBay requests/day. Celery uses JSON serialization, late acknowledgements, prefetch one, task expiration, and hard time limits. These settings do not provide a distributed singleton lock. Run only one Beat scheduler and verify overlap behavior during rolling deployments.

## Deployment status

### Admin stats production rollout — 2026-10-10 UTC

- The reported `/admin/stats` HTTP 404 came from a release mismatch: Cloudflare had frontend commit `22869ded33d9c64e2365d440e6e5232c12142163`, while manually disabled Backend CI/CD left Lightsail on `9b4c787158473fb3b3deb460e20668aae47161ea`. GitHub run `34748756712` still reports queued; backend automation remains disabled. No workflow history was deleted and no new commit/push was made for this repair.
- **Active backend:** `/opt/cardboarddex/releases/22869ded33d9c64e2365d440e6e5232c12142163`, ECR digest `sha256:fbf2bd0f5996712ac8d16db159917bf031c9a7080edf86489937b39a1af54777`, tag `admin-22869de-20261010`. The AMD64 image was built from the committed backend and passed 202 tests (16 opt-in skips) before publishing to the verified existing account/repository. Production `BACKEND_IMAGE` now matches the current release digest.
- Backup `six-hourly/20261010T002001Z/manifest.json` passed checksum and separate local PostgreSQL/Redis restore checks before rollout. Alembic `0006_site_analytics` was applied; catalog counts remain 54,968 cards and 491 sets. Only the new analytics/admin schema was added. The previous application release remains available for rollback; do not drop analytics tables as part of an ordinary application rollback.
- Production preserves its existing `ADMIN_API_KEY`; a separate stable analytics identity secret was generated server-side. Analytics is enabled with Secure/HttpOnly/SameSite=Strict admin cookies and exact origins `https://cardboarddex.app` and `https://www.cardboarddex.app`. The API is still bound to host loopback. Trusted country/client headers use only Docker gateway `172.18.0.1/32`; `FORWARDED_ALLOW_IPS=` preserves the real socket peer. Public telemetry verified country `US`.
- `cardboarddex-analytics-retention.timer` is enabled; its initial service execution succeeded (exit 0). Existing backup timer remains active. Ingestion pause marker and stopped worker/Beat are preserved. API readiness is 200, health is healthy, restart count is zero, and no OOM occurred. Post-rollout available memory was 156 MiB with 256 MiB swap used; this is an immediate check, not long-term capacity verification.
- Cloudflare dropped dashboard-set analytics environment variables during the first rebuild (`6e62c5e1-77fc-452b-8937-204f8c2c21bd`), leaving the public tracker disabled. The Pages build command now explicitly exports `NEXT_PUBLIC_ANALYTICS_ENABLED=true` only when `CF_PAGES_BRANCH=main` (false for preview branches), and `NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL=false`, before the unchanged `npx @cloudflare/next-on-pages` adapter. The existing API URL settings were preserved. Final deployment `f2b7c1b9-bdaa-4ccd-b4a5-62d16c8ee436` succeeded at 02:59:57 UTC. Public verification at 03:00:20 UTC confirmed layout chunk `layout-0d5ca5b6abbf0beb.js` contains the tracker and opt-out UI with both public flags compiled; readiness returns 200 and unauthenticated stats returns 401 instead of 404.
- Public verification passed HTTPS readiness, CORS, login, authenticated stats, `no-store`, cookie security attributes, rejection of unapproved origins, telemetry deduplication, country attribution, logout, and post-logout 401. The synthetic deployment visit and its lifetime-count contribution were removed afterward. Admin credentials were never printed or changed.
- Operational receipts and scripts are under ignored `.system_generated/admin-stats/`. The rollout preserved the pre-change production environment in `/etc/cardboarddex/app.env.before-admin-22869de`. Atomic environment updates must preserve file ownership/mode; the initial attempt was stopped before API replacement by an ownership error and corrected. Remote shell scripts are uploaded before execution so Docker cannot consume the remaining streamed script input.

### Delete-first attempt and fallback recovery — 2026-10-08 UTC

- **Current production host: `cardboarddex-recovered`, dual-stack `nano_3_0`, 512 MB RAM, $5/month, us-west-2a.** The owner authorized a delete-first attempt with fallback to this original plan. After deleting `cardboarddex-ipv6`, AWS rejected the 1 GB IPv6 target with the explicit nano-only account restriction. The original host no longer exists; the IPv6/capacity migration remains incomplete. AWS Support must lift the bundle restriction before retrying.
- Final quiesced backup `six-hourly/20261008T041945Z/manifest.json` passed PostgreSQL and Redis restoration before deletion. Manual snapshot `cardboarddex-delete-first-20261008` was verified available and retained. Recovery preserved 54,968 cards, 491 sets, 284,056 observations, and revision `0005_price_obs_analytics_cover`. Keep the snapshot until separately approved for deletion. Private recovery checkpoints/configuration live under ignored `.system_generated/lightsail/delete-first-20261008/`; do not print embedded credentials.
- Maintenance began about 04:19 UTC and public readiness returned about 17:35 UTC, exceeding the two-hour plan. Lightsail's `sh` launch wrapper initially rejected Bash `pipefail`; bootstrap was completed via verified SSH. API recovery then selected the stale `BACKEND_IMAGE` from the env file instead of the release digest and returned `/ready` 404 until work resumed and corrected it. New tested recovery tooling explicitly invokes Bash and pins the release image before reconnecting the Tunnel.
- Active release remains `9b4c787158473fb3b3deb460e20668aae47161ea`; image digest `sha256:50ae114df7b8831340db0ff0ac1603cb097a4983114e8e274ff18422a19ad29a`. API/PostgreSQL/Redis are healthy; API has zero OOM events/restarts. Ingestion pause marker persists and worker/Beat remain stopped. Live Comps remains stale at September 24, not newly updating.
- Fresh SSM node `mi-0477fdc9fccf98fc2` is Online; direct and SSM-proxied SSH both verified with AWS-provided host keys. GitHub host/SSM variables and known-hosts secret now point to the recovered host. The image-sync workflow was reenabled. Backend CI/CD remains disabled because stale September 13 run `34748756712` is reported queued, while cancel and force-cancel both return HTTP 409. Resolve this before restoring backend deployment automation; no run history was deleted.
- Six-hourly backup timer is enabled. Recovery backup `six-hourly/20261008T173507Z/manifest.json` passed checksums and both off-server database restores. Public endpoint tests: 13 passed, two legacy AWS checks skipped. Local Lightsail tooling: 87 passed, three opt-in container checks skipped; the new real Redis success/corruption restore test passed separately. Compose validation and diff checks passed. No schema changes, application-release upgrades, commits, or pushes occurred. Detailed operations and remaining work are in `docs/lightsail-migration.md`.

### IPv6 infrastructure implementation blocked — 2026-10-08 UTC

- The owner approved implementation of a separate $5/month 1 GB/40 GB IPv6-only replacement, with up to 30 minutes cutover maintenance and 48-hour observation before source retirement. AWS again rejected the instance-only creation of `cardboarddex-ipv6-1gb` with `InvalidInputException`: "maximum limit of Lightsail Instances : 1." This is an AWS account restriction, not a local approval rejection. The historical nano-only restriction remains unverified. Service Quotas reporting two instances does not establish actual eligibility.
- Follow-up inventory confirms only the original running dual-stack `cardboarddex-ipv6` on `nano_3_0`; public `/ready` returns HTTP 200. No replacement, cutover, deployment, credential rotation, ingestion restart, or production configuration change occurred. Live migration remains incomplete. Submit the updated Support request in `docs/lightsail-migration.md` to allow two concurrent instances and the 1 GB bundle; no support message was sent.
- Local preparation: provisioning now waits for operation completion and verifies actual RAM/CPU/system disk and IPv6-only networking before reporting readiness or configuring backup resources. Added credential-free IPv6 HTTPS transport checks for execution on the future host and inside its backend container. Authenticated dependency verification, secure SSM bootstrap integration, restore rehearsal, and all cutover/observation gates remain pending.
- Verification: Lightsail tooling suite passed 67 tests with two opt-in container tests skipped; after adding the final follow-on-resource guard test, all 33 provisioning/preflight tests passed. Both relay tests passed. No destination runtime validation is claimed. Preserve all earlier local cleanup and provisioning changes; nothing committed or pushed.

### Cleanup and Live Comps verification — 2026-10-07 UTC

- Read-only public API and verified SSH checks at 23:17–23:19 UTC confirm `/ready` returns HTTP 200, but **Live Comps ingestion is not updating**. The feed still contains 284,056 observations: 32,702 eBay and 251,354 TCG API. Newest eBay `observed_at`: `2026-09-24T05:15:07.134359Z`; newest TCG API: `2026-09-24T03:13:31.474000Z`. Response-level `updated_at` advances with requests and must not be interpreted as ingestion freshness.
- AWS reports `cardboarddex-ipv6` running on `nano_3_0`. The active release remains `9b4c787158473fb3b3deb460e20668aae47161ea`. `/opt/cardboarddex/ingestion.paused` exists; worker and Beat exited 13 days ago. API, PostgreSQL, and both Redis containers are healthy. Host memory: 412 MiB total, 88 MiB available; swap used: 262 MiB. No deployment, restart, or infrastructure mutation was performed. Capacity/workload resolution is still required before safely resuming ingestion.
- Local cleanup removes the duplicated market-router fallback `TTLCache` and TypeScript-confirmed unused imports, formatters, handler, binder loading state, volume calculation, and API URL export. Existing backend compatibility re-exports remain because tests/callers use them. Cards/Sets schemas are unchanged; pre-existing provisioning/runbook edits are preserved.
- Local `frontend/lib/api.ts` now bypasses browser memory caching and in-flight reuse for `cache: "no-store"`, including Live Comps polls. Other browser GET cache entries remain reusable for 60 seconds, with expired entries pruned and a 64-entry capacity. This fixes polling delay but cannot restore paused ingestion; it will increase network requests for callers that explicitly request `no-store`.
- Verification: 190 backend tests passed (15 opt-in live tests skipped); 28 frontend tests passed, including six cache regressions; TypeScript with `--noUnusedLocals --noUnusedParameters`, production build, and `git diff --check` passed. Build reports the existing Next.js Edge Runtime deprecation. Changes are local and have not been committed, pushed, or deployed.

### Live outage verification and recovery — 2026-09-29 UTC

- Public `/ready` returns HTTP 530 with body `error code: 1033` and no production-origin CORS header. The catalog screenshot shows the same HTTP status for search/sets; browser CORS errors are secondary to the unavailable Cloudflare Tunnel.
- AWS reports `cardboarddex-ipv6` running on `nano_3_0`, but recent `StatusCheckFailed_Instance` samples are 1 while `StatusCheckFailed_System` samples are 0. Verified recovery SSH times out on port 22; the Lightsail firewall permits that port. SSM reports `ConnectionLost`, with last ping at 2026-09-25 10:31:27 UTC. This indicates an instance OS/network reachability failure; exact cause remains unconfirmed without host logs.
- Recent CPU utilization is approximately 2%, with burst capacity at 100%. Current evidence does not support renewed CPU-credit exhaustion. Memory pressure, guest networking, and process state cannot be checked while management access is unavailable.
- The newest six-hourly S3 backup manifest is `six-hourly/20260925T062004Z/manifest.json`, last modified at 2026-09-25 06:20:32 UTC; no weekly manifests were listed. This inspection checked manifest timestamps only, not archive integrity or restoreability.
- Read-only investigation only: no reboot, deployment, firewall change, or ingestion restart was performed. Previously recorded ingestion pause cannot be rechecked on-host during this outage. Recovery must preserve the existing disk/database and retain the ingestion pause; inspect host logs, memory, containers, and backup failures after management access returns.

Recovery follow-up (approximately 08:42–08:44 UTC): after the user authorized continuation, a controlled Lightsail reboot restored verified SSH, SSM Online, and all four Cloudflare Tunnel connections. Public `/ready` returns 200; `/cards/sets` returns 220 records in 0.66 seconds and the screenshot's 24-card price-descending search returns 24 records in 0.81 seconds. Both catalog responses include `Access-Control-Allow-Origin: https://cardboarddex.app`. Backend, PostgreSQL, and both Redis containers are healthy. The ingestion pause marker remains present and worker/Beat remain stopped. Disk usage is 52%; available memory is approximately 152 MiB, with 198 MiB swap used. This establishes immediate recovery, not sustained stability.

Prior-boot logs confirm a global out-of-memory event at 2026-09-25 10:11:28 UTC that killed `fwupd`, later network-online timeouts, and scheduled backups failing to connect to the S3 dual-stack endpoint. These events support memory/network failure concerns but do not establish the exact causal chain. No service masking or network configuration changes were made. No deployment or schema changes were made.

Backup recovery (2026-09-29 09:19 UTC): after explicit user approval, the existing backup service uploaded PostgreSQL and Redis to `cardboarddex-backups-349558247779-us-west-2`, publishing `six-hourly/20260929T091903Z/manifest.json` at 09:19:24 UTC. PostgreSQL archive size is 52,985,353 bytes; Redis snapshot size is 3,124 bytes. Independent off-server verification downloaded both objects, verified SHA-256 checksums, and successfully restored PostgreSQL in a disposable local container: 54,968 cards, 491 sets, schema revision `0005_price_obs_analytics_cover`. The disposable container was removed by the verification script. Public readiness remained HTTP 200 after backup completion. The backup timer remains enabled; future scheduled completion and sustained host stability still require observation. Ingestion remains paused.

Recovery follow-up: **2026-09-24 UTC**. Earlier recoveries relapsed under dashboard/image load. The capacity-fix release below adds database and request-concurrency controls; do not treat the earlier smoke checks as proof of sustained stability.

- Current host: `cardboarddex-ipv6`, 512 MB Lightsail instance in `us-west-2a`. Recovery enabled dual-stack networking on the same disk, changing the bundle from `$3.50/month nano_ipv6_3_0` to `$5/month nano_3_0`, within the existing server budget. Its public IPv4 address is dynamic; query AWS before connecting. The old `32.187.254.253` address is obsolete.
- GitHub uses `LIGHTSAIL_HOST=cardboarddex-ipv6` and `LIGHTSAIL_SSM_TARGET=mi-04eda276674cf91be`. The older `mi-07cf7e6e80daf232f` registration is stale. Recovery SSH uses short-lived Lightsail access certificates and host keys independently verified through AWS. No new persistent SSH authorized key was installed.
- The original backend workflow passed tests and image build, then failed with `TargetNotConnected`; all 30 SSM checks reported `ConnectionLost`. After publication of `b4111b2`, run `35939942195` reached SSH but failed strict host verification because GitHub still stored the pre-migration host keys. GitHub `LIGHTSAIL_KNOWN_HOSTS` now contains the AWS-verified current keys, and `LIGHTSAIL_SSH_KEY` now contains the existing Lightsail default key after successful authentication. No server-authorized key was added. The backup workflow failed because its latest completed archive was over 64 hours old. The host showed sustained swap/disk stalls, exhausted CPU burst capacity, and an API process with roughly 424 MB swapped out.
- The previously active release was `31b2efd92e46f38a9a6be7740fbae3aed7a19542`, image digest `sha256:1a844284d1e1fd42d8bbece2ff5aeea9f11fe3e60402ff473e4c70a8ae24467a`. This remains the previous release for reference; deploying it would restore the unbounded query behavior. The capacity recovery image is now active; ingestion is paused after full-service recovery repeatedly stalled the host.

### Recovery changes and artifact

- Latest verification after the paused recovery: 13 public checks passed, two direct-AWS checks skipped, but a subsequent concurrent image burst timed out while a backup was running. Local readiness still returned 200. At approximately 06:38 UTC, `vmstat` measured 91–92% CPU steal and heavy swapping; Lightsail reported burst capacity falling to 0% at 06:33 UTC. The outage is not fully resolved even with ingestion paused. Avoid repeated load tests/restarts that consume the remaining capacity; a sustainable capacity/workload decision remains outstanding. S3 independently confirmed a completed backup at schema `0005_price_obs_analytics_cover`; the additional backup requested at 06:34 UTC was still running at last inspection.

- Latest capacity image: `cardboarddex-backend:recovery-20260924-capacity`, digest `sha256:62a75b7c74ed9f4c2f1b7bccc3ec8f252fe467e9d6bf2bc4b5e5c2b216b984d3`, release `/opt/cardboarddex/releases/recovery-20260924-capacity`. It adds a configurable API thread limit (four in production), releases image-request database sessions before external I/O, and serializes S3 client initialization. All 174 backend tests pass in the AMD64 image; 15 opt-in live tests are skipped there.
- PostgreSQL runs with JIT off, parallel query workers disabled, and a 12-second statement timeout. Migration `0005_price_obs_analytics_cover` adds only a covering index on `price_observations`; `cards` and `sets` are unchanged. It was tested through upgrade/downgrade/re-upgrade on disposable PostgreSQL 16, then applied online in production and validated. The migration session has a five-minute index-build timeout. A representative aggregate uses an index-only scan, zero heap fetches, and completes in 200 ms. Normal deployment still checks revisions and never runs migrations automatically.
- With ingestion paused for verification, all 13 public endpoint tests passed (two direct-AWS tests skipped). A simultaneous page-load check returned all 24 images within 1.87 seconds, Live Comps in 1.60 seconds, Trending in 0.58 seconds, and readiness in 0.33 seconds. API OOM/restart counts remained zero. Restoring worker and Beat subsequently reproduced HTTP 502 and a whole-host stall before a second load test could begin. Full-service stability is not established. After another preserved-disk restart, the capacity release completed deployment with ingestion paused. `/opt/cardboarddex/ingestion.paused` prevents the release script and its rollback from starting ingestion; existing worker/Beat containers also have restart policy `no` so reboot preserves the pause. Eight deployment tests cover normal and paused success/failure paths. New catalog/pricing ingestion is unavailable during this pause.

- A later catalog failure was a separate 15-second client timeout. Production EXPLAIN measured the broad price sort at 25.7 seconds: 28,551 correlated price lookups and sorts. A single ranked latest-price relation measured 3.1 seconds on the same database. Broad price sorts/range filters now use that relation; selective name/set searches retain indexed per-card lookups. Timestamp ties use observation ID consistently. No schema changes were required. The new `search:v2` cache namespace ensures old cached responses do not mask verification.

- Dashboard queries now aggregate price histories in PostgreSQL; grading materializes at most four observations per card without JSON payloads, and sealed products use the latest observation by timestamp/ID. These initial query changes did not alter database schema; the later price-observation index migration is described above.
- Compose uses 16 MB PostgreSQL shared buffers, one-minute steady-state health checks with five-second startup probes, and a lightweight curl readiness probe. The 512 MB host has a 512 MB LZ4 zram swap device at priority 100; the existing 2 GB disk swap remains fallback. `cardboarddex-zram.service` enables this before Docker at boot. Bootstrap and release scripts install it only on small hosts.
- Dynamic login-status scripts were disabled to avoid expensive status-generation processes. Unused Snap services and the desktop disk-management service were disabled during recovery; no firmware/disk service masking was applied. Snap is not the active SSM installation.
- CI now fails before SSH if SSM never becomes Online and preserves AWS errors. Release verification requires successful privileged backup-timer activation instead of silently swallowing failure.
- Published and tested AMD64 recovery image: `cardboarddex-backend:recovery-20260923-memory`, digest `sha256:b9713a8ab6bda24de4971ad73669094aaa6f293f9945db8b94add7c15c9fc740`. This image was superseded by the search fix below; the limits-only release is retained for rollback.
- Search-fix image: `cardboarddex-backend:recovery-20260924-search`, digest `sha256:cbcef6c0b4b8a8660d7aa8f473afa4d5f39848b527c9f0b1c8af2fbf6e89cc60`, historically deployed at `/opt/cardboarddex/releases/recovery-20260924-search`, now retained as `/opt/cardboarddex/previous`; `/opt/cardboarddex/current` points to the capacity release. The updated release script completed all verification steps successfully. It passes 171 backend tests inside the AMD64 image (nine opt-in live checks skipped). Initial uncached public searches took 3.47 seconds for the exact 24-card request, 2.93 seconds for 23 cards, and 3.15 seconds for ascending prices. With ingestion restored, a fresh uncached 24-card search took 2.99 seconds. All seven public smoke tests pass, including the 15-second frontend deadline (two direct-AWS tests remain intentionally skipped).
- Deployment initially stalled checking multiple images while ingestion was resident. The host was restarted with application processes stopped, and only the backend image was pulled before API startup. The release script now drains ingestion before image pulls/schema checks, serializes pulls, and restores the previous release if a pull fails; regression tests cover that failure.
- The original fixes were published as `b4111b2`. Follow-up runtime limits, query/concurrency fixes, the price-observation index migration, deployment sequencing, and regression tests remain local pending commit/push approval; publish them before rerunning deployment, or main will remove the new limits.

### Backups and verification

- Existing backup bucket: `cardboarddex-backups-349558247779-us-west-2`, with private access, TLS, SSE-S3, six-hourly retention of seven days and weekly retention of 28 days. Production credentials remain in protected host files and ignored local operational files; never print or commit them.
- The backup timer was active, but repeated runs timed out after 30 minutes during the outage. The recovery backup `six-hourly/20260924T000429Z` completed at 00:05:30 UTC in about one minute; its manifest freshness and revision `0004_price_obs_search_index` were independently verified from S3. GitHub backup verification, including the full disposable restore, [passed](https://github.com/n8liu/cardboarddex/actions/runs/35936844062). With the follow-up limits active, backup `six-hourly/20260924T045921Z` completed successfully at 04:59:49 UTC.
- Historical checks for the first recovery image passed (168 backend tests, seven live tests skipped); these results predate the later relapses and do not establish current stability. Regression tests cover bounded history materialization, latest-price selection, SSM failure handling, backup-timer deployment failures, and safe zram initialization. All 36 deployment tests pass, including disposable container restore tests. Compose validation and shell syntax checks pass. Seven public smoke tests pass with bounded ingestion running, including the exact initial `/cards/sets` and price-descending `/cards/search` requests with production-origin GET CORS headers; two direct-AWS checks are intentionally skipped because the API binds to loopback behind Cloudflare. The four affected dashboard endpoints return 200, and SSM reports Online. A completed eBay task wrote 146 observations with zero provider errors. TCG bulk pricing returned a tier restriction and the existing individual-request fallback succeeded.
- The screenshot outage was HTTP 530 / Cloudflare tunnel error 1033; missing CORS headers came from the edge error response. SSH and SSM were also unreachable. Tunnel logs showed timeouts around 03:53 UTC; available system logs did not establish the precise initiating process. A preserved-disk restart restored access.
- API RAM/total RAM+swap limits are 160/224 MiB; worker 96/160 MiB; Beat 48/80 MiB. Python processes use `MALLOC_ARENA_MAX=2`, and worker children recycle after ten tasks. These bound application memory growth; they do not prove the host has sufficient sustained capacity. Initial checks with all services running showed no OOM events, roughly 342 MiB compressed into 114 MiB, and idle disk I/O. The 05:00 UTC scheduled pricing task completed five cards with zero provider errors, while API readiness remained successful; API, worker, and Beat had zero restarts. Those initial successes were followed by another outage. Keep ingestion paused until capacity is resolved and verify a complete workload cycle before declaring sustained stability.
- See [the Lightsail runbook](docs/lightsail-migration.md) for migration history and recovery restrictions. Do not delete or replace the only instance to bypass AWS account limits without explicit authorization.

## R2 image delivery implementation (pending activation)

- Lightsail 1 GB eligibility recheck (2026-09-26 08:38 UTC): attempted separate `cardboarddex-ipv6-1gb` using active $5 `micro_ipv6_3_0` (1 GB / 40 GB / IPv6 only). AWS rejected creation with `InvalidInputException`, "maximum limit of Lightsail Instances : 1", despite Service Quotas reporting 2. The historical nano-only restriction remains unverified. Rechecked source `cardboarddex-ipv6`: still running on `nano_3_0` dualstack; no replacement exists and no production/backup/IAM settings changed. AWS Support API is unavailable (`SubscriptionRequiredException`); no case submitted. Exact findings and a ready-to-submit Support request are in `docs/lightsail-migration.md`. Provisioner now defaults to the separate destination, rejects the production name, validates bundle specifications, and supports `--instance-only` so eligibility failures cannot mutate backup resources. Ingestion remains paused; migration awaits AWS restriction removal.

- Live Comps investigation (2026-09-25 07:07 UTC): public `/ready` returned 200; `/cards/live-updates` returned 284,056 observations, with newest `observed_at` at 2026-09-24 05:15:07 UTC. The response-level `updated_at` is request time, not evidence of new ingestion. Production inspection confirmed `/opt/cardboarddex/ingestion.paused` exists and worker/Beat have been stopped for about 25 hours. Host memory was 412 MiB total, 65 MiB available, with 243 MiB swap used. Stale Live Comps is explained by paused ingestion; no workers were restarted. Capacity resolution or moving ingestion off the host remains necessary before safely restoring scheduled updates. The browser request helper also caches GET responses for 60 seconds despite `cache: "no-store"`; this can delay polling but does not explain the day-long data gap.

- User published `9b4c787158473fb3b3deb460e20668aae47161ea`; [backend deployment 36076917738](https://github.com/n8liu/cardboarddex/actions/runs/36076917738) succeeded. `/opt/cardboarddex/current` points to that release. API readiness is successful, backend restart count is zero, and worker/Beat remain stopped with the ingestion pause marker present.
- The preceding workflow-expression and clock-dependent test failures are fixed and published. Local verification: 190 backend tests passed (15 live checks skipped), 40 deployment/tooling tests passed (two container checks skipped), 22 frontend tests passed, TypeScript/build/actionlint passed.
- The user created both R2 buckets and configured GitHub secrets R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_ENDPOINT_URL. Public DNS resolves images.cardboarddex.app. A real uploaded image returned HTTP 200, correct JPEG/immutable headers, then CF-Cache-Status HIT. The shared placeholder also returns 200.
- [100-image pilot 36078751849](https://github.com/n8liu/cardboarddex/actions/runs/36078751849) uploaded 90 images (2,608,786 bytes), reported 10 failures, and published a verified 90-image manifest. Representative failures were provider HTTP 404s; the workflow reports failure when any image fails even though successful objects and the manifest are published. Inventory contains 54,968 source image records. No whole-catalog size guarantee is inferred from the pilot.
- [500-image continuation 36079017839](https://github.com/n8liu/cardboarddex/actions/runs/36079017839) completed: 494 uploaded, six provider 404s, 16,723,862 new bytes; manifest contains 584 verified images.
- User configured the Cloudflare Cache Rule. Verification PASSED: a new missing-image URL returned 404/BYPASS twice, while a real uploaded image returned 200/HIT twice with immutable headers.
- Full backfill was started through ignored operational script `.system_generated/lightsail/r2_backfill.py`, starting with run 36096212877. At the September 24 PDT / September 25 UTC Actions investigation, no controller process was running. Its latest checkpoint is batch 7, [run 36098574750](https://github.com/n8liu/cardboarddex/actions/runs/36098574750), completed at 05:32 UTC: 497 uploaded, three provider 404s, and 4,061 verified manifest images. GitHub confirms manifest publication succeeded and only the failure-reporting step failed. The reason the controller stopped is not established. The public Actions page returned HTTP 200, its API responded, and the latest backup verification passed. No controller was restarted during this investigation. The controller dispatches sequential 500-image runs, checks published manifests/storage/error categories, and stops on unexpected failures, more than 100 failures in a batch, approaching the 8 GB cap, or a main-branch change. Read `.system_generated/lightsail/r2-backfill-progress.json` and its `.jsonl` history, and verify process/run status before starting another controller. Repository visibility was verified public.
- Before cutover, API readiness returned 200 and the initial catalog still returned relative API image URLs. Latest Lightsail metrics: burst capacity about 50.4%, CPU about 2.4%, with ingestion paused. Baseline saved in ignored `r2-before-cutover.json`.
- Production CDN mode and scheduled synchronization remain disabled. Full backfill, cutover, and the 24-hour observation remain pending; no production CPU savings are claimed yet. Cards/Sets schemas are unchanged. Keep ingestion paused.
- See [R2 image setup and cutover](docs/r2-images.md) for configuration, validation, costs, and rollback.

## Configuration

Backend settings are loaded from environment variables and the repository-root `.env` by [Settings](backend/app/config.py). The following are **code defaults**, not verified production values.

| Variable | Purpose / default |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy connection URL; defaults to `sqlite:///./cardboarddex.db`. Configure PostgreSQL for development/production as appropriate. |
| `REDIS_URL` | Durable broker/results, quotas, OAuth tokens and checkpoints; `redis://localhost:6379/0`. |
| `CACHE_REDIS_URL` | Disposable response caches and analytics; falls back to `REDIS_URL` locally. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | API defaults 3/2; production worker overrides 2/0. |
| `POSTGRES_HOST` / `POSTGRES_PASSWORD` | Production connection configuration; safely constructs a URL instead of interpolating passwords. |
| `TCGAPI_API_KEY` | Server-side TCG API credential; unset by default. |
| `TCGAPI_BASE_URL` | `https://api.tcgapi.dev/v1`. |
| `TCGAPI_DAILY_REQUEST_LIMIT` | `2000`. |
| `TCGAPI_SYNC_SET_LIMIT` | `250` newest sets per game by default. |
| `PRICE_COLLECTION_CARD_LIMIT` | `5` cards per scheduled collection batch by default. |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | Server-side OAuth credentials; unset by default. |
| `EBAY_MARKETPLACE_ID` | `EBAY_US`. |
| `EBAY_DAILY_REQUEST_LIMIT` | `500`. |
| `S3_BUCKET_NAME` | Optional bucket for image caching/sync. |
| `AWS_REGION` | Image-storage client region; `us-west-2`. |
| `CLOUDFRONT_DOMAIN` | Optional asset hostname without a scheme. |
| `BACKEND_CORS_ORIGINS` | Comma-separated origins; defaults to localhost/127.0.0.1 on ports 3000/3001. `main.py` additionally allows matching production/preview origins and exact HTTPS origin `https://cardboarddex.nliu.org` (added locally 2026-10-10; deployment pending). Admin origin authorization remains separately configured through `ADMIN_ALLOWED_ORIGINS`. |
| `NEXT_PUBLIC_API_URL` | Browser-visible API base URL; resolved by [next.config.ts](frontend/next.config.ts) and [api.ts](frontend/lib/api.ts). Never put credentials here. |
| `PSA_VALUE_FEE` | Grading-fee assumption; `24.99`. |
| `ADMIN_API_KEY` | Token for privileged routes through `X-Admin-Token`; admin actions disabled when unset. |
| `ENABLE_API_DOCS` | `false`; controls Swagger, ReDoc, and OpenAPI routes. |
| `RATE_LIMIT_PER_MINUTE` | `300`; image paths use a separate hardcoded `6000`/minute bucket. |
| `RATE_LIMIT_TRACK_ACTION_PER_MINUTE` | `30`. |
| `RATE_LIMIT_HEAVY_PER_MINUTE` | `60`, but currently not wired to endpoints. |

Earlier references to `S3_CARD_ASSETS_BUCKET` and `S3_CUSTOM_DOMAIN` do not match these settings. `AWS_DEFAULT_REGION` is not the application's `aws_region` setting.

Never commit `.env`, provider credentials, database passwords, or Tunnel tokens.

## Development and verification commands

From the repository root, `docker compose up -d` starts PostgreSQL and Redis. Review the exposed-port issue below before using it on a remotely reachable host.

From `backend/`, with the virtual environment and intended environment configured:

```bash
.venv/bin/uvicorn app.main:app --reload
.venv/bin/alembic upgrade head

# Isolated test configuration: avoid the configured database/Redis.
DATABASE_URL=sqlite:// REDIS_URL=redis://127.0.0.1:1/0 TCGAPI_API_KEY= EBAY_CLIENT_ID= EBAY_CLIENT_SECRET= .venv/bin/pytest
PYTHONPATH=. .venv/bin/python -m compileall -q app jobs tests parsers
```

Jobs below write to the configured database/S3 and consume provider quota. Use an activated backend virtual environment; check `--help` for other supported options.

```bash
python -m jobs.sync_catalog --game all --limit 50
python -m jobs.sync_catalog --game pokemon --limit 50
python -m jobs.sync_catalog --game pokemon-japan --limit 50
python -m jobs.cycle_prices --card-id 28402
python -m jobs.cycle_prices --pokemon "Pikachu"
python -m jobs.update_card --card-id 28402
python -m jobs.update_card "Rayquaza Legends Awakened"
python -m jobs.update_card --pokemon "Rayquaza" --limit 20
python -m jobs.update_pokemon "Charizard" --limit 20
python -m jobs.collect_prices --limit 50
python -m jobs.collect_prices --card-id 29919
python -m jobs.collect_prices "Rocket's Moltres"
python -m jobs.collect_ebay_prices --limit 20
python -m jobs.collect_ebay_prices "Charizard Base Set"
python -m jobs.collect_ebay_prices "151 Binder Collection"
python -m jobs.sync_images_to_s3 --limit 100 --workers 5
python -m jobs.sync_images_to_s3 --all --workers 10
celery -A app.celery_app worker --beat --loglevel=info
```

Catalog options also include `--resume` and `--reset-cursor`; use them only with the checkpoint limitations above understood. The image-sync CLI supports `--set-id` for targeting a set.

For manual continuous cycling, use `python -m jobs.cycle_prices --continuous --interval 900 --tcg-limit 50 --ebay-limit 20` as an alternative scheduler, not alongside Beat against the same workload.

From `frontend/`:

```bash
npm ci
npm run dev
npm test
npm run typecheck
npm run build
```

From `backend/`, the explicit live verification command is:

```bash
RUN_LIVE_DEPLOYMENT_TESTS=1 .venv/bin/pytest -m live tests/test_deployment_endpoints.py -v
```

Set `AWS_BACKEND_URL` to the legacy endpoint from the recorded infrastructure table only while testing migration parity. Omit it after retirement.

Opt-in deployment tests and direct-AWS parity checks: [docs/ecs-tunnel-migration.md](docs/ecs-tunnel-migration.md). `RUN_LIVE_DEPLOYMENT_TESTS=1` enables public endpoint calls; `AWS_BACKEND_URL` additionally enables the two direct-AWS checks.

Latest audit verification (2026-09-15):

- Backend: 151 passed, five live-test skips, using isolated database/Redis configuration.
- Frontend: 20 tests passed across five test files.
- `npm audit --omit=dev`: no known production-dependency vulnerabilities reported at that time.
- Mocked checks reproduced image redirect bypass, proxy-header trust, retained expired cache entries, and portfolio look-ahead bias.
- Public homepage headers lacked CSP and framing protection. Live IAM/RDS/S3 permissions, Python advisories, and comprehensive historical secret scanning were not audited.
- Build/typecheck success was recorded by the preceding migration work; those checks were not rerun for the security audit or this documentation-only cleanup.

## Open work, in priority order

### 1. Security and availability

- **Image fetching:** validate redirects/destinations and enforce image type/size limits in `TCGAPIClient.get_image()`. The existing hostname allowlist only checks the initial URL.
- **Caches and request cost:** bound and evict expired portfolio/grading/sealed/volume caches, avoid retaining invalid requests, enforce heavy-endpoint limits, and bound expensive history queries.
- **Proxy trust:** accept client-IP headers only from trusted proxies; confirm direct-origin closure after cutover.
- **Redis:** local rate-limit middleware now uses an async client with explicit timeouts and lifespan cleanup; deployment and production latency verification remain pending.
- **Development services:** bind Compose PostgreSQL/Redis to loopback; configure authentication/network isolation where remote access is required.
- **Frontend headers:** deploy an application-compatible CSP and framing restrictions on HTML responses. API headers do not protect the separate frontend document.
- **Cloud secrets/IAM (verify live):** the runbook reports secrets in ECS environment entries; move to secret references. Restrict the guide's wildcard OIDC subject and AWS resource permissions; grant OIDC permission only to deployment jobs.

### 2. Pricing correctness and privacy

- Remove current-price backfilling of missing historical portfolio prices; expose historical coverage. Preserve duplicate holding quantities and consistent printing identity.
- Fix fallback valuation's oldest-observation selection and unbounded per-card request fan-out. Reconcile percentage-change versus currency-amount semantics across calculations.
- Replace sold-sales wording for active listings/catalog observations. Observation frequency is affected by ingestion and does not measure transaction volume.
- Replace arbitrary mover fallbacks with insufficient-data states. Expose grading probabilities, missing costs, and sealed-score assumptions; use explicit ordering for latest sealed observations.
- Browser `no-store` compliance and bounded cache retention are implemented locally as of October 7; production deployment remains pending. Date or refresh FX rates.
- Document binder uploads and third-party media/font requests. Redact sensitive provider error payloads and keep operational diagnostics protected.

### 3. Operations and follow-up features

- ECS/ALB/RDS retirement is complete. Production runs on the $7/month Lightsail server base (cardboarddex-1gb, 1 GB RAM / 40 GB disk) with dual-stack networking, raised worker/Beat memory limits, active systemd backup timers, and source rollback retention.
- Standardize locked Python dependencies and vulnerability checks; add `npm test` to frontend CI and regression coverage for the findings above.
- Fix quota diagnostics to read the same Redis keys as the limiter. Separate liveness from readiness and protected diagnostics.
- Repair catalog `--all` and checkpoint semantics before relying on resumable ingestion. Verify one Beat scheduler during deployments.
- Add freshness, provider-quota, failed-image, job-duration, and match/reject monitoring.
- Verify available eBay programs/scopes before implementing completed-sales ingestion. Add sold-sales statistics and accounts/watchlists after pricing identity and data quality are reliable.

### Passive refresh and 1 GB capacity rollout — 2026-10-14 (deployed and active)

Production has been upgraded to `cardboarddex-1gb` ($7/month `micro_3_0`) and the passive refresh engine is live in production:
- **Priority pool & rotation:** 1,500 individual cards ranked by 50% 7-day popularity, 25% set release recency, and 25% price, frozen for seven days in durable Redis (`cardboarddex:passive:v2:cycle`). Batches of eight cards reserve five weekly priority slots, two hot slots (12 hottest, 3-hour cooldown), and one catalog progression slot using independent durable cursors.
- **Request limits:** Atomic Lua reservations enforce global ceilings (2,000 TCGAPI / 500 eBay requests/day) and scheduled-pricing sublimits (1,500 TCGAPI / 450 eBay requests/day).
- **Execution & deduplication:** 900s token lease, hard task limits, and observation deduplication (unchanged quotes do not create duplicate price observations) prevent synthetic comp creation.
- **Operator report:** `python -m jobs.passive_refresh_report` outputs comprehensive JSON metrics (cycle deadlines, checked/remaining/overdue cards, cursor positions, retries, and quota usage).
- **Validation:** 59 unit tests passed across config, client, and passive refresh suites; full backend suite passed 251 tests; all 8 integration tests passed against real disposable PostgreSQL/Redis (verifying 7-day healthy operation, outage reporting, crash recovery, and Redis restarts).
- **Production status:** Canaries succeeded, ingestion pause marker removed, single Celery worker (192/256 MiB) and Beat (64/96 MiB) resumed. 48-hour stability observation active with minute-by-minute systemd health monitoring.
