# Passive TCGAPI and eBay refresh

The October 14 release is based on production commit `5096ca27113f319836af15d9a0112faaa4ef748f`, with the scoped refresh changes described here. It does not deploy unrelated market-data migrations or change Cards/Sets schemas or public response contracts. See `PROJECT_CONTEXT.md` for activation and observation status.

## Ranking and durable coverage

Eligible individual cards exclude code cards, missing card numbers, and sealed products. Explicit TCGAPI product type takes precedence; otherwise a populated non-`None` rarity identifies an individual card.

Rank uses **50% popularity, 25% release recency, 25% price**. Each component uses a midrank percentile among present values, giving equal values equal scores; missing values score zero. A single present value scores one. Card ID breaks final ties. Popularity sums the current UTC day plus six preceding daily view/click buckets, each capped at 2,000 cards and retained for eight days in cache Redis. Initial activation may have fewer than seven days of collected interest. Cache loss makes unavailable interest zero; it does not reset durable coverage. Recency uses set release date. Price uses the latest stored positive, ungraded USD TCGAPI observation, ordered by observation time and ID.

The top 1,500 are frozen for seven days starting at activation. Durable Redis stores the cycle, per-provider successful checks and attempts, retry queues, and catalog cursors under `cardboarddex:passive:v2`. Rollover records the previous cycle's missed coverage before replacing membership, retaining 12 summaries. Each provider's cursor survives cycle rollover. The 12 hottest priority members are selected using current recent-interest scores; hot refreshes are eligible after three hours and satisfy weekly coverage too.

## Scheduling and failures

The existing alternating schedule remains: TCGAPI at `:00/:30`, eBay at `:15/:45`. Eight-card batches reserve five weekly-priority slots, two hot slots, and one catalog slot without duplicates. Unused slots go first to uncovered priority members, then retry/catalog work. The remaining catalog advances in stable card-ID order with an independent cursor for each provider, wrapping at the end. This provides daily progress, not daily refreshes of the entire catalog.

A failed or interrupted attempt becomes retry-eligible after one hour. The durable retry queue is capped at 1,000 entries per provider; overflow is explicitly reported. A due priority retry can use a priority slot. The catalog lane alternates due catalog retries with fresh cursor progress, preventing permanent failures from monopolizing catalog advancement. Additional spare slots can service due retries. Eligibility is not a guarantee of immediate retry when quota or capacity is exhausted.

Cursor advancement, attempts, and provisional retries are saved atomically before calling the collector. Successful empty responses count as checked; provider/commit failures do not. A process crash after the database commit but before Redis acknowledgment can repeat a check, but observation deduplication prevents fabricated comps. Identical quotes do not become new observations merely because the check date changed; a new listing or changed quote can create a comp. eBay results remain active asking prices, not completed sales. Title parsing remains in `backend/parsers/title_matcher.py`.

The existing 900-second shared token-owned execution lease and 840-second task limit remain. Every scheduled HTTP request also checks lease ownership. An expired worker cannot spend another request or overwrite its successor's progress. Durable Redis failures stop scheduled work. Catalog and manual collectors share quotas; avoid running manual jobs alongside ingestion.

## Request budgets

| Provider | Global daily ceiling | Scheduled-pricing sublimit |
| --- | ---: | ---: |
| TCGAPI | 2,000 | 1,500 |
| eBay | 500 | 450 |

A Redis Lua reservation checks and increments both applicable counters atomically immediately before each HTTP attempt. Retries and eBay OAuth calls consume allowances. Blocked requests do not increment counters. A crash after reservation but before transport conservatively consumes the reserved allowance. Limits reset by UTC day.

The schedule permits 384 card attempts/day/provider, including 240 reserved weekly-priority slots. Requests are not equivalent to cards: TCGAPI may use bulk capability probing and individual fallback, and providers may retry. Weekly coverage is conditional on provider availability, quotas, catalog-job contention, and errors. The report exposes missed coverage rather than asserting that scheduling alone guarantees it.

## Configuration and operator report

- `PASSIVE_REFRESH_ENABLED=true`
- `PRICE_COLLECTION_CARD_LIMIT=8` (the coordinator caps scheduled batches at eight)
- `PASSIVE_PRIORITY_CARD_COUNT=1500`
- `TCGAPI_SCHEDULED_REQUEST_LIMIT=1500`
- `EBAY_SCHEDULED_REQUEST_LIMIT=450`

Run `python -m jobs.passive_refresh_report` in the backend environment. On production:

```sh
docker exec app-backend-1 python -m jobs.passive_refresh_report
```

The read-only JSON report includes cycle deadlines/history, checked/remaining/overdue counts, last successful check and last run, cursor position and advances/wraps, retry backlog/overflow, attempts versus successes, and current global/scheduled quota usage. Timestamps are UTC Unix seconds. Structured `passive_refresh`, `passive_cycle_started`, and `passive_cycle_finished` logs accompany execution. Live Comps reads accepted observations through its existing polling API; visits never start provider jobs.

## Rollout and monitoring

Worker concurrency remains one. On the 1 GB host, worker limits are 192 MiB RAM / 256 MiB total RAM plus swap; Beat is 64/96 MiB. API and PostgreSQL tuning remain unchanged. `/opt/cardboarddex/ingestion.paused` remains the deployment guard.

`cardboarddex-ingestion-monitor.timer` runs each minute. It records resource and coverage samples in the system journal and `/var/lib/cardboarddex/ingestion-monitor/latest.json`. It creates the pause marker, disables worker/Beat automatic restart, and stops Beat then worker on OOM/container restart, three consecutive API probe failures, five minutes of memory below 150 MiB available / swap-in above 1 MiB/s / I/O wait above 10%, or missing/stale backups beyond 6.5 hours. Monitor errors are logged as service failures; they must also be investigated. It never automatically resumes ingestion.

Inspect `journalctl -u cardboarddex-ingestion-monitor.service` and `systemctl status cardboarddex-backup.service`. Completion of the 48-hour stability window and seven-day production coverage check requires actual elapsed operation; simulation results are not production verification. After any regression, investigate before removing the pause marker and recreating exactly one worker and Beat.

Verification includes ranking/ties/missing data, independent provider progress, cursor wrap, atomic concurrent quota exhaustion, lease replacement, crash recovery, an actual Redis restart, and seven-day healthy/outage simulations using disposable PostgreSQL/Redis. Healthy simulation checked all 1,500 cards for both providers while catalog progress continued. Outage simulation reported overdue coverage while continuing cursor advancement.

Production activation: October 14, 2026 at 06:25:48 UTC on `cardboarddex-1gb`, release `passive-652c868fcf5b`. Initial pool creation preceded activation at 06:19:46 UTC. At 18:17 UTC both providers had 202 successful checks, 145/1,500 priority coverage and 26 catalog advances, with no retry backlog or stability regressions. The 48-hour review is due October 16 at 06:25:48 UTC; first weekly coverage review is due October 21 at 06:19:46 UTC. These are pending production checks, not completed verification.
