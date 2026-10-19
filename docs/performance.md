# Application caching and page responsiveness

Implemented locally on October 13, 2026. Deployment and production latency verification are pending. No infrastructure upgrade, paid Cloudflare product, provider ingestion restart, or Cards/Sets schema/index change is required.

## Cache ownership and freshness

Public database reads use `backend/app/common/response_cache.py`, existing disposable Redis, and a process-local fallback. Cache keys include a version, endpoint, database identity, image-manifest generation, and every effective filter/page argument. Raw search strings are hashed in keys and are not logged.

| Endpoint/data | Fresh | Maximum age including stale time |
| --- | --- | --- |
| Catalog searches, Pokémon cards, set statistics | 60 seconds | 5 minutes |
| Set directory | 1 hour | 2 hours |
| Home overview, grading, sealed | 5 minutes | 30 minutes |
| Market Movers combined language/period ranking | 15 minutes | 30 minutes |

A fresh hit executes no rebuild SQL. A stale hit may start a background refresh; only one background refresh runs per API process and additional distinct keys are not queued. Successful empty results are cached. Failures never replace a successful snapshot or become result payloads. Results beyond their maximum age are not served.

Rebuilds use a dedicated database session with PostgreSQL `statement_timeout=5000ms`. This is a per-statement timeout, not a whole-request deadline. Token-owned Redis leases last 15 seconds; publication and lock release check ownership atomically. A rebuild that outlives or loses its lease cannot publish. Cold followers wait up to four seconds for the rebuild, excluding network-operation time; if unavailable they receive HTTP 503 and `Retry-After: 2`.

Local storage is limited to 64 entries and 8 MiB of serialized envelopes, not total interpreter heap usage. Oversized entries can be served and stored in Redis but are not retained locally. Lease/failure bookkeeping is bounded. Redis failures open a 30-second local circuit breaker; process-local coordination continues during that interval. Failed rebuilds have a 30-second per-process cooldown. Coordination during Redis outage is per process, not global. Redis publication failure does not publish a potentially unowned result locally.

Existing grading/sealed/set-statistics service caches remain available to direct service callers, but coordinated HTTP routes explicitly bypass them. Home HTTP reads use its uncached builder. This avoids resetting old snapshots' age through nested caches. Existing unrelated caches, provider quotas, and Celery broker state are untouched.

## Browser behavior and interfaces

The API helper retains successful allowlisted GET results in memory, up to 64 entries. Browsing results live for at most 60 seconds, sets for five minutes, and neither exceeds the backend's original fresh-until timestamp. Stale responses are displayed but not retained in browser memory. Navigating away and back in the same document can reuse results; a full reload starts a new memory cache.

Identical cacheable requests share a network request. Cancelling one subscriber only cancels that subscriber; the network is aborted when all subscribers leave. Explicit retries bypass memory reuse. An older request cannot overwrite a newer retry. `CacheOptions` accepts `abortSignal`, `bypassCache`, and `onCache`; `abortSignal` is distinct from sealed products' existing `signal` filter.

The coordinated endpoints bypass Next's server data cache and use browser HTTP revalidation, avoiding another cache lifetime layered over Redis. No Cloudflare cache rule or adapter change is needed. Live Comps, admin, telemetry, portfolio POSTs, and tracked card-detail reads keep their existing uncached behavior. HTTP retry does not force a backend rebuild or defeat its cooldown/locks.

Response bodies are unchanged. These CORS-exposed headers carry cache metadata:

- `X-Cache-Status`: `miss`, `hit`, `stale`, `stale-error`, or `stale-busy`.
- `X-Cache-Generated-At`: original snapshot generation time, retained across cache layers.
- `X-Cache-Expires-At`: fresh-until time, not the maximum stale limit.
- `Server-Timing`: cache status and application duration.

Responses use `Cache-Control: public, no-cache, max-age=0, must-revalidate`. The UI distinguishes cached/refreshing results from unavailable refreshes. Snapshot generation is not evidence of recently ingested prices. Background completion does not push data to an already open page; the next request sees the refreshed snapshot.

The initial catalog request has no typing debounce; text/price input changes wait 250 ms, while discrete filters and pagination load immediately. Navigation and controls remain independent of product loading. Filter changes clear previous-filter products; same-filter refreshes retain results while pending. Existing card-detail pricing streaming and browser history behavior are preserved.

Live Comps pauses background polling in hidden tabs and avoids overlapping polls. It attempts an immediate refresh when visible, unless another request is already running. Both PokéAPI detail reads have three-second deadlines and keep their existing daily revalidation/fallback behavior. Binder fallback uses four workers, each issuing one detail/pricing read at a time, logs exact failures, and preserves successful cards. Existing binder valuation semantics are not redesigned here.

## Market Movers semantics

The request path never calls the provider. It ranks latest ungraded USD TCG observations by the exact requested `price_change_24h`, `price_change_7d`, or `price_change_30d` field. Selection is deterministic by provider timestamp, observation timestamp, and observation ID. Missing/nonfinite changes, invalid prices, unrelated providers/currencies, and graded observations are excluded. Positive and negative lists are ranked across the matching language before pagination.

There is no other-period substitution, comparison of unrelated historical rows, or arbitrary fill of empty lists. Insufficient stored data returns empty rankings, with an explicit UI message. `price_change_amount` remains null because this path does not manufacture a currency amount from a percentage. Item dates remain source observation dates; response `updated_at` is the snapshot generation time. While ingestion is paused, available observations can remain old even after the response cache refreshes.

## Verification and rollout

Verified locally: 239 backend tests passed (19 opt-in skips), 103 frontend tests passed, TypeScript and production build passed, and three disposable PostgreSQL/Redis integration tests passed. Browser checks with API responses held pending passed for catalog, movers, grading, sealed, trending, and Live Comps at 390px and 1440px, with usable controls, no horizontal overflow, and zero browser exceptions. Existing Next Edge Runtime and backend dependency deprecation warnings remain. These results do not establish production latency. A final local Chrome check with 400 ms fixture API delays confirmed zero additional API requests when navigating away from and back to the catalog, and zero browser errors. Automated first/repeat visit wall times were 1,165/1,151 ms (including navigation/action waits); this is not evidence of a 50% whole-page improvement.

Run ordinary checks with isolated settings:

```sh
# backend/
DATABASE_URL=sqlite:// REDIS_URL=redis://127.0.0.1:1/0 CACHE_REDIS_URL=redis://127.0.0.1:1/0 PPT_MINUTE_WEIGHT_LIMIT=55 PPT_API_KEY= EBAY_CLIENT_ID= EBAY_CLIENT_SECRET= .venv/bin/pytest -o addopts='' -q

# frontend/
npm test
npm run typecheck
npm run build
```

`backend/tests/test_cache_integration.py` additionally requires explicit `CACHE_TEST_DATABASE_URL` and `CACHE_TEST_REDIS_URL` pointing to disposable services. It creates/removes its own PostgreSQL schema and namespaced Redis keys, never flushes Redis, and checks real Redis coalescing/lease ownership plus PostgreSQL ranking, warm-hit SQL counts, and statement timeout. Do not point it at production.

Deploy only after release authorization, backend first, then frontend. Verify migration `0007_market_data` is already present for the existing home/sealed builders; this change adds no migration. Preserve the ingestion pause marker and do not start worker/Beat as part of performance rollout.

Before and after rollout, record a small sequential sample for catalog, movers, grading, sealed, and card detail. Capture HTML response time, API duration, payload bytes, image duration, and time until products appear; compare first visits, repeat client navigation, and full reloads separately. Record filter parameters without including private collection content. Do not run concurrent load tests on the small production host.

Use cache status headers and structured `Response cache route=... status=... duration_ms=...` logs to compare hit rate and application latency. Rebuild logs include elapsed time and serialized bytes, without search text. Observe errors, 503/retry rates, Redis evictions, available memory, swap, and CPU burst capacity. A 50% improvement in repeat-navigation data wait is a rollout target, not a claimed production result. Cold SQL work and image delivery can still dominate initial visits.

Rollback to the previous application releases if latency, correctness, or resource use regresses. Old and new response namespaces are separate; let disposable entries expire rather than flushing broker/quota data. R2 cutover, thumbnails, broader query/index redesign, and paid capacity remain separate work.

## Trending and volume follow-up — October 18

Operator CI output showed 15-second read timeouts for `/cards/trending` and
`/cards/top-pokemon-volume`; 11 other smoke checks passed. This is a post-deployment
verification failure, not a successful full rollout. Do not increase the smoke-test
read timeout to hide the failing routes.

The local fix introduces `card_observation_stats`: disjoint non-eBay and matched
assessment joins aggregate narrow observation columns per card. PPT aggregates
remain excluded from observation-volume metrics. Top Pokémon Volume calculates
current/prior windows and catalog enrichment in one pass instead of three; Trending
joins per-card aggregates instead of grouping wide catalog/history joins. Existing
ranking formulas, immediate click updates and explicit reset behavior are preserved.
Process cache keys now include pricing mode, and explicit Trending invalidation
matches the actual source-prefixed Redis namespace.

On the isolated October 17 production restore (395,797 observations including
1,500 synthetic PPT quotes and 500 synthetic matched assessments), uncached Volume
completed in 0.546–0.613s and Trending in 1.124–1.148s with PPT both off and on. Redis
and process caches were bypassed/cleared; each SQL statement had a five-second
limit. These local measurements do not establish production latency. Full backend
regression tests passed, including evidence exclusions, half-open time windows,
PPT-volume exclusion and immediate click-ranking tests. No new migration is needed;
retain schema 0010. No commit/deployment was performed for this follow-up. Re-run
production smoke tests and observe both cold and warm requests after release.

### Remaining Trending timeout: shared request aggregation

The next deployed smoke run passed Top Pokémon Volume but still timed out on
Trending. A read-only trace against production found separate Trending card
queries (2.57s plus 2.19s for clicked cards), Pokémon enrichment exceeding its
five-second SQL limit, and volume taking another 4.11s in total.

The new default, unfiltered dashboard shares one request-scoped per-card aggregate
across all three sections and supplementary clicked cards. Filtered searches keep
the existing SQL path. Result fetching uses 512-row batches to reduce transient
memory; retained rows are bounded by catalog size, not history size. Ranking,
listing eligibility, source selection, time windows, and click invalidation remain.
No timeout changes or schema migration are required.

An isolated temporary container on the production host ran the candidate against
the real database in read-only transactions, with five-second statement limits,
real click scores and both response caches bypassed. Final service-call timings:
8.724s with PPT primary off, 9.923s with it on; all three sections returned 50 items.
Peak process RSS was 147,856 / 148,944 KiB. These are service-call measurements,
not public HTTP latency or concurrent-load certification. An initial validation
child inside the serving container exited 137; subsequent checks used a separate
temporary container to avoid sharing the serving process's memory allowance.
The running API code and persisted configuration were not changed.

Backend suite passed; focused tests also passed after bounded fetching was added.
Regression coverage compares shared versus independent results for all five time
windows, includes a clicked card outside the top 200, and asserts one history SQL
statement per uncached default dashboard. Changes remain local and uncommitted.
Deploy normally, then rerun the public smoke suite; retain the 15-second deadline
and observe memory and cold/warm latency under normal traffic.


## Independent Live Comps feed and totals (local, 2026-10-18)

The dashboard now uses `/cards/live-updates/feed` and `/cards/live-updates/stats`
independently. The feed preserves existing filters and offset pagination, requests
one extra row for `has_more`, and never executes count/KPI queries. Its SQL has a
five-second statement timeout. Both new routes use `Cache-Control: no-store`.
The legacy `/cards/live-updates` response remains unchanged for older clients.

Statistics are global, including when the feed is filtered. A stored-data-only
Celery task runs every 60 seconds, expires queued work after 55 seconds, and has
a 20-second hard limit. The existing single worker can delay refreshes behind
other work; one minute is a target, not a guarantee. The task computes totals
in one SQL statement within a read-only repeatable-read transaction, with a
five-second statement timeout. A 30-second token-owned Redis lease prevents
concurrent publication; a worker that loses its lease cannot overwrite totals.
Keys include snapshot version, matcher version, and PPT visibility mode. No new
provider requests, schema changes, or worker concurrency are introduced.

Successful snapshots are fresh for 60 seconds and usable for 30 minutes.
Refresh failure retains the last successful snapshot. Statistics requests only
read Redis: missing, invalid, expired, or unavailable snapshots produce HTTP 503
with `Retry-After: 60`, without database queries or refresh dispatch. The UI shows
timestamps/staleness and stops displaying expired numeric values. Feed requests,
errors, retries, and 15-second polling remain independent of 60-second totals
polling. Hidden tabs pause polling; obsolete filter responses are ignored.
Pagination displays loaded counts instead of exact filtered totals.

Deploy backend/API, worker, and Beat before frontend. Seed the snapshot with
`python -m jobs.refresh_live_stats` in a separate configured one-off container, then
verify both new routes before deploying frontend. To roll back the backend,
first restore the older frontend that uses the retained legacy route. No data
migration or destructive rollback is necessary.

Production incident, October 18: paused ingestion stopped both the worker and
Beat, leaving no totals snapshot. Seeding via `docker exec` in the 160 MiB API
container exhausted its memory budget and killed Uvicorn. A separate container
using the deployed worker service's memory limits successfully published totals.
For paused ingestion, use the dedicated systemd timer documented in
`scripts/lightsail/README.md`; it never starts provider jobs and yields to the
normal Celery schedule when the pause marker is removed. Do not run the extra
Python process inside the API container.

Validation: full isolated backend suite and all 143 frontend tests passed;
TypeScript and production build passed. Tests cover cold/missing totals, no
feed aggregates, provider/grade/search parity, legacy compatibility, stale expiry,
lease publication, failed refresh preservation, independent retry, cancellation,
obsolete filters, and preserving final-page state during first-page polling.
Backend tests require explicit default visibility/ingestion flags because local
`.env` settings enable a different provider mode; the test-only environment uses
`PPT_MINUTE_WEIGHT_LIMIT=55 PPT_PRIMARY_ENABLED=false PPT_INGESTION_ENABLED=false
TCGAPI_INGESTION_ENABLED=true`, SQLite, and unreachable test Redis URLs. No local
configuration was changed. Opt-in live/infrastructure tests were skipped.

Production deployment and timing verification remain pending. Compare feed
latency with missing versus available snapshots; record worker refresh duration
and snapshot age separately. `Live feed query` logs include acquisition/query
elapsed time, while `Live stats refresh` logs report total refresh duration.
These are not separate connection-wait/SQL/serialization measurements. No
production performance improvement is claimed from fixture tests.


## Catalog current-price projection (local, 2026-10-18)

The catalog family now shares selected-price lookups and has an optional
transactionally maintained current-price projection. Reads remain disabled by
default until migration 0011, backfill, and parity verification complete. Local
restored-data benchmarks passed the 50% broad-sort improvement gate in both
provider modes; PostgreSQL 16 production validation remains pending. See
[catalog-price-projection.md](catalog-price-projection.md) for exact semantics,
commands, measurements, limitations, and rollout/rollback requirements.
