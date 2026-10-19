> Historical record, archived before the PPT retirement cutover. Commands and activation claims are superseded by [the current runbook](../../ppt-cutover.md).

# Pokémon Price Tracker migration

Implementation is additive and disabled by default. Existing TCGAPI observations,
`market_history`, cards, sets, eBay observations, and eBay quality screening remain.
The initial implementation was disabled by default. See dated rollout results
below for authenticated testing and operator-reported production deployment.

## Data contract

- Provider identifier: `pokemonpricetracker`. English/Japanese cards and sealed
  products have separate identities. Explicit TCGplayer IDs in existing metadata
  are indexed once in bounded 500-state batches and checked first; otherwise exact
  language/set/name/card number is required.
  Legacy local IDs and image filenames are never assumed to be TCGplayer IDs.
- Ambiguous names/numbers, multiple products mapping to one card, or identity changes
  are quarantined. Existing catalog IDs and metadata remain intact. New products and
  sets receive deterministic `ppt-` / `ppt-set-` IDs. Provider set product counts
  are never assigned to printed set totals. Discovery returns images without
  constructing CDN URLs.
- `ppt_products` holds mapping, bounded metadata, current quote snapshots, success
  dates and retry state. `ppt_current_quotes` indexes currently valid observation
  fingerprints, so a missing current quote cannot silently revive an older median.
- `ppt_history` stores monthly JSON chunks keyed by product, language, printing,
  condition, grade and metric. Updates merge exact dates and accept corrections.
  Existing history is not pruned or overwritten. `ppt_checkpoints` stores discovery
  pagination, frozen weekly priority membership, scheduler position and rotation progress.
- Raw prices come from current top-level `variants`, with `conditionUsed` preserved.
  `prices.variants` and `prices.conditions` are deprecated and are not used. Missing
  conditions remain `Unknown`. The provider's primary printing determines the headline.
- Raw history uses `priceHistory.variants[printing][condition].history`. Sealed
  history uses `unopenedPrice`. Requests ask for `days=180,maxDataPoints=180`; only
  returned dates are recorded. Missing volume is unknown, not zero.
- PSA quotes use `marketPriceMedian7Day`, requiring recent `lastMarketUpdate` and
  `lastSaleDate`. Missing recent medians stay unavailable. Lifetime medians and smart
  prices are not substitutes. Provider smart-price outlier flags are retained.
- Graded history uses the separate `daily_average` metric. It is not used to
  calculate a seven-day-median change. Graded aggregates may combine eBay and
  Fanatics Collect; they are provider-reported sales, not authenticated listings.
- Raw changes require the exact baseline date, source, printing, condition and
  metric. Missing baselines yield null. PPT counts are excluded from legacy
  observation-as-sales analytics. Provider sales activity sums explicit raw volume
  only for the primary printing/condition; no graded counts or snapshots are added.

## Request budgets and scheduling

The 20,000 allowance is **credits**, not HTTP requests. Every request explicitly
sets a bounded limit; a single product uses `limit=1`. Cards cost requested limit
multiplied by `1 + includeHistory + includeEbay`. Sets cost one credit per page.
Discovery pages contain 25 products or 100 sets. Full-set unbounded fetches are rejected.

| Lane | Daily credits | Work |
| --- | ---: | --- |
| Priority | 4,500 | Up to 1,500 products with history and graded prices where applicable |
| Rotation | 13,000 | Up to 6,500 current-price/history requests |
| Graded bonus | 500 | Add graded data to 500 rotating card requests; no extra HTTP request |
| Discovery | 1,500 | Bounded catalog pages across both languages and product kinds |
| Retry | 500 | Due failures with capped exponential backoff |

Weekly priority uses popularity, release recency and price. Existing popular IDs
remain candidates during mapping. Rotation is oldest-success-first with proportional
backlog allocation and a 10% minimum share for each nonempty segment. A successful
product is not fetched again in the same UTC day. Retry state is persistent.

Beat enqueues short batches every 15 seconds. Each batch stops launching requests
at 25 seconds, with at most eight items by default. Single-flight request and batch
leases prevent overlapping workers. No quota sleep occupies the shared Celery
worker; direct eBay and image jobs retain their schedules.

All lanes share atomic Redis reservations, a weighted sliding-minute ceiling of
55 (below the provider's 60), and a hard daily cap at or below 20,000. Counters use
the durable non-evicting Redis, never the response cache. Reservation happens before
HTTP; lost responses remain charged. Response credit and daily-remaining headers
reconcile usage. Purchased/total remaining balances are ignored. Minute exhaustion
and provider 429s establish a global cooldown; authentication errors stop requests
for 24 hours. New requests pause in the last 30 seconds of a UTC day to avoid
ambiguous rollover accounting. At 22:00 UTC, overdue queues may borrow unused lane
capacity, including unused retry capacity, without exceeding the total cap.

Use a dedicated API key, durable Redis persistence, and an accurate UTC system
clock. Do not share this daily budget with outside callers. For an existing key,
start at the next UTC reset or conservatively initialize its already-used credit
counter before enabling ingestion. Provider balance headers cannot protect the
first request after an unknown external spend. Do not clear quota keys to retry.

The budget is a ceiling, not a promise to spend exactly 20,000: empty/missing
mappings, unavailable data, errors, cooldowns and short provider responses reduce
useful work. Verify paid-plan licensing before a commercial launch.

## Local/shadow rollout

1. Back up PostgreSQL and durable Redis using the existing operational procedure.
   Rehearse migration `0009_pokemon_price_tracker` on a disposable restored database.
   This follows `0008_listing_assessments` and does not change Cards/Sets schema.
2. Apply the migration separately from the release. Add `PPT_API_KEY` only to the
   private backend environment. Never put it in a frontend build variable.
3. Start a bounded pilot with `PPT_INGESTION_ENABLED=true`,
   `PPT_PRIMARY_ENABLED=false`, and a low `PPT_DAILY_CREDIT_LIMIT` (for example 100).
   Leave `TCGAPI_INGESTION_ENABLED=true`. Restart worker/Beat to load settings.
   `python -m jobs.sync_ppt` also runs one bounded batch through the same leases/quota.
4. Run `python -m jobs.ppt_report` for read-only mapping, due coverage, storage and
   quota diagnostics. Review quarantined identities manually against both catalogs;
   there is deliberately no fuzzy auto-approval. Compare representative EN/JP,
   sealed, promo/parallel printings and PSA 9/10 histories to the provider dashboard.
5. Observe memory, database growth, worker queue latency, weighted-minute use,
   response charges and daily reset behavior on the target host. Confirm that the
   direct eBay worker and ingestion pause procedures still operate normally.
6. After validation, set `PPT_PRIMARY_ENABLED=true` and
   `TCGAPI_INGESTION_ENABLED=false`; raise the PPT budget to 20,000. Restart API,
   worker and Beat together. TCGAPI price/catalog/history schedules and their manual
   job entrypoints are gated; direct eBay remains enabled. No provider request occurs
   on public pricing or catalog read paths.

Rollback: set PPT primary/ingestion flags false and TCGAPI ingestion true, restart
services, and retain all additive tables. **Do not downgrade to roll back application
code**: downgrade removes the new data. Source-aware cache keys isolate the main
read caches; allow the remaining short-lived client/CDN caches to expire on cutover.

## UI/API

Card pricing adds `provider_quotes`, `provider_history`, and `ppt_mapped`. Quotes
expose source, metric, language, printing, condition, grade, currency, source date,
fetch date and staleness. The graph defaults to six months, retains legacy lines,
and offers checkboxes for individual PPT variants and grade series. Missing PPT
days break lines; historical backfill does not create Live Comps entries.

Catalog, movers, sealed, grading, binder and trending choose the current PPT price
when enabled and available. Otherwise raw prices use dated legacy TCGAPI data.
Mapped cards without a recent PSA median do not substitute older medians or eBay
asking prices. Live Comps adds a PPT filter and distinguishes market updates,
graded aggregates and matched asking listings. Existing direct eBay screening is
not applied to aggregate history, nor is it claimed to authenticate those aggregates.

## Validation and limits

### Catalog/Live Comps query correction (local follow-up)

Follow-up after operator deployment of `c6d015e27e02470b868264e4879a854861ea6d19`
and migration 0010: PPT catalog passed at 4.06s. Instrumented production Live Comps
returned its filtered count in 0.74s and feed rows in 0.02s, but the combined scalar
KPI statement exceeded the five-second deadline. The earlier local benchmark did
not predict this production KPI failure.

The next code-only correction moves KPIs to `live_observation_totals`: one aggregate
over non-eBay providers and a second aggregate joining eBay observations to unique
matched assessment fingerprints, with card/item/version/status checks retained.
It avoids repeated correlated evidence probes over full history. On the isolated
restore with 500 synthetic matched eBay assessments, totals took 0.135s with PPT
hidden and 0.064s with PPT visible; exact parity against the original eligibility
predicate passed. Tests cover rejected/pending, wrong card/item, obsolete version,
missing evidence, provider aliases and PPT visibility. The full backend suite passed.
These are local measurements. This follow-up needs deployment and the same
read-only production validation, but no migration beyond 0010. Public PPT remains
disabled pending that check.

Operator read-only checks showed the production legacy catalog taking 4.06 seconds,
PPT catalog exceeding the five-second statement deadline, and PPT Live Comps
returning 48 records in 4.73 seconds. Primary pricing remains disabled pending
validation of the correction. Ingestion and public price selection are independent.

Current-primary selection now builds one independent CTE of valid PPT fingerprints
and card IDs, shared by the PPT and legacy fallback branches. It removes the
per-legacy-observation correlated preferred-price lookup. Live Comps KPI counts
use separate scalar aggregates; TCGAPI counts no longer evaluate listing JSON
eligibility. eBay and graded eligibility rules remain in effect.

Migration `0010_ppt_query_indexes` builds PostgreSQL indexes concurrently for legacy
latest pricing, primary PPT lookup, and provider-filtered feed ordering. It adopts
the exact `ix_price_observations_tcgapi_latest` index already created during the
incident and rejects invalid/incomplete indexes. Before adopting an independently
created index, confirm its definition matches the migration. Cards/Sets are untouched.
Do not remove quota data or increase API statement timeouts for this change.

Local validation used the October 17 production backup plus 1,500 synthetic current
PPT quotes (395,797 observations total). With new indexes, PPT catalog returned 24
items in 0.425 seconds; PPT Live Comps returned 48 items in 0.395 seconds, without
response/Redis caches and with five-second per-statement limits. The prior catalog
predicate on the same indexed database took 0.759 seconds. These are single local
measurements with synthetic PPT coverage, not cold-cache or production benchmarks.
The backend regression suite passed under explicit default test settings. PostgreSQL
migration and existing-index adoption passed; Cards/Sets columns were preserved.
Private benchmark receipt: `.system_generated/ppt-rehearsal/query-results.json`.

Deploy a new immutable release containing the sealed adapter correction and these
queries. Apply migration 0010 separately using that release's image, then validate
PPT-on catalog and Live Comps with a process-only flag and read-only transactions
before enabling `PPT_PRIMARY_ENABLED` for public API processes. No commit, push,
production migration 0010, or production flag change was performed by this local work.

Production trial follow-up, October 17 (operator-reported): migration 0009 and
release 4f4482798b16891814056159c1f248e8d11a8f46 deployed successfully. PPT primary
remains disabled; manual batches indexed legacy identifiers and saved set discovery.
Sealed refreshes for 712093/712094/712096 returned HTTP 400 with `includeEbay=false`
in their query strings. The published sealed endpoint does not support this
cards-only parameter. The adapter now strips it for non-card endpoints while still
rejecting attempts to request graded sealed data. A regression test covers the
worker's exact argument shape and two-credit reservation. This correction is local;
the cause still needs confirmation through a bounded production retry after release.
Do not raise the trial budget to work around these errors. The local environment's
minute setting of 100 exceeds the current configuration maximum of 55; targeted
tests override it to 55 without modifying the private environment file.

Fixtures cover actual published field shapes, exact baselines, missing medians,
EN/JP identity separation, quarantine, corrections, idempotence, source preference,
shadow visibility, scheduler checkpoints, history/feed separation, migration
preservation, weighted sliding limits, concurrent reservations, daily rollover,
prepaid exclusion, lost responses, and cooldowns. Quota tests execute the Lua scripts
using `fakeredis[lua]`; they are not production Redis persistence/load tests.

Public contract references: [OpenAPI](https://www.pokemonpricetracker.com/api/openapi),
[API reference](https://www.pokemonpricetracker.com/api-reference),
[data coverage](https://www.pokemonpricetracker.com/data-coverage).
### Authenticated local pilot — October 16, 2026

The configured key successfully returned English/Japanese cards and sealed products.
Provider headers confirmed 20,000 daily credits and 60 weighted requests/minute.
Eight HTTP requests used 16 credits (19,984 remaining at the last response), including
one rejected unfiltered Japanese-card request. Successful requests charged exactly
the expected one credit for sets, two for sealed history, and three for card history
plus graded data. The pilot conservatively reserved 18 credits including the failed
request. No purchased credits were used.

Five sampled products were imported into isolated PostgreSQL 16 with real Redis 7
quota accounting: EN Fighting Energy 490294, JP Psychic Energy 566552, EN Destined
Rivals Booster Box 624679, JP 151 Card File Set 618704, and EN Umbreon VMAX 246723.
Migration to head succeeded. Ingestion stored 2,829 dimensioned history points in
203 monthly chunks and 11 current observations. Repeat imports preserved counts,
the seeded legacy history remained intact, and card-profile response serialization
passed. History covered April 21–October 16; individual series can have gaps.

Real responses exposed printing/language suffixes in `conditionUsed`, such as
`Near Mint Holofoil - Japanese`. Normalization now removes exact known suffixes so
current quotes match their condition-specific history and 7/30-day changes. Five
regression cases cover this behavior without treating unknown conditions as NM.
Umbreon returned PSA 9/10 seven-day medians of $1,985.09/$3,800 dated October 16.
The energy-card samples lacked recent graded medians; their historical grade series
were retained without fabricating current quotes.

Reproducible local runner: `PYTHONPATH=. .venv/bin/python scripts/ppt_live_pilot.py`
from `backend`, with an explicit resource and bounded filters. `verify-saved` replays
the saved responses without provider calls. It targets only the dedicated pilot
PostgreSQL database on localhost:15432; requests use durable pilot Redis on :16379.
The single-process file lock and retained request receipt enforce an additional
30-credit pilot ceiling. Private receipts/payloads are under
`.system_generated/ppt-pilot/`; preserve the receipt and `ppt-pilot-quota` Docker
volume when repeating the pilot. Credentials are never written into receipts.

Backend regression suite: 337 passed, 27 skipped. Scheduled ingestion and PPT
primary flags remain false; application/production databases were not changed.
Real existing-catalog matching coverage, production throughput, restart/daily-reset
observations and the 1 GB host's memory/storage headroom still require a shadow pilot.
