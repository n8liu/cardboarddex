# Pokémon Price Tracker migration

Implementation is additive and disabled by default. Existing legacy observations,
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

## Cutover and public API

Follow [the current cutover runbook](ppt-cutover.md). Apply migrations through 0012, rebuild/verify projection version 2 and seed immutable market transitions before enabling public PPT prices. Never reactivate the retired provider during rollback.

Card pricing returns `market_quotes`, `market_history_series`, and compatibility `provider_quotes`/`provider_history`. The unified graph keeps original legacy provenance before the cutover, continues compatible raw series with PPT, and exposes original PPT backfill separately. Unknown conditions and graded metrics remain distinct. Stale raw quotes retain dated last-known values; current graded medians require recent evidence. A raw-only refresh does not renew the graded-sales snapshot date.

Trending ranks provider-reported `ebay.salesByGrade` counts from synced card metadata. Missing counts are unknown; explicit zero remains zero. No fixed sales window is implied. Public reads make no provider requests.

Earlier pilot responses and production measurements are retained in [the historical integration record](archive/pre-ppt/pokemon-price-tracker.md). They are not evidence of this release's deployment.

Contract references: [PPT documentation](https://www.pokemonpricetracker.com/docs), [OpenAPI](https://www.pokemonpricetracker.com/api/openapi).
