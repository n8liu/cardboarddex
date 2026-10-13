# Passive TCGAPI and eBay refresh

Implementation is local; production ingestion has not been resumed by this change.

The existing Beat schedule runs TCGAPI at :00/:30 and eBay at :15/:45 UTC.
Each scheduled batch selects up to `PRICE_COLLECTION_CARD_LIMIT` (default 5)
cards. Up to three slots go to popular cards; the remaining slots go to the
rest of the catalog. Unused popular slots flow to the catalog. At least one
catalog slot is reserved even with a smaller batch configuration.

Popularity uses actual card views/clicks recorded by the existing analytics
path, combining today's and yesterday's UTC buckets (a 24–48 hour window).
Each bucket retains at most 2,000 cards and expires after 48 hours. The top 12
are the popular pool. Existing lifetime trending scores and observation counts
are not used. Cache loss temporarily returns collection to catalog rotation.

Popular cards are eligible after one hour; other cards after 24 hours. These
are minimum intervals, not freshness guarantees: quota, batch size, popularity,
provider failures, and catalog size determine actual turnaround. With defaults,
12 continuously popular cards compete for six popular slots per hour per
provider, so a complete popular rotation takes roughly two hours. Catalog cards
rotate through at least 96 slots per day per provider when batches are full;
a large catalog cannot all refresh daily at this budget.

Freshness is checked independently for each provider using existing
ProviderCardState rows. A TCGAPI update cannot postpone an eBay refresh.
Scheduled attempts also have provider-specific cooldowns, including failures and
empty responses, so repeated failures do not monopolize batches. Durable Redis
holds attempt timestamps; cache Redis holds disposable popularity counts.
No schema changes are required.

A shared 900-second token-owned Redis lease prevents the two scheduled pricing
jobs from overlapping. Celery enforces an 840-second hard task limit. Scheduled
collection fails closed if durable Redis is unavailable. Each batch checks the
existing daily request counter before starting; each actual provider request
still passes through the existing limiter. Default ceilings remain 2,000 TCGAPI
and 500 eBay requests/day. The batch schedule permits up to 240 card attempts
per provider per day, but requests and card attempts are not equivalent.
Catalog sync and manual tools share request ceilings but do not use this batch
lease; do not run manual collectors alongside scheduled ingestion.

The browser reads stored observations through the existing API. Opening a card
records interest; it does not fetch providers or launch a task on every visit.
Live Comps continues its existing visible-tab polling. Newly accepted observations
appear there; unchanged observations may be deduplicated. eBay Browse results
are active asking prices, not completed sales. Other cached dashboards retain
their documented cache windows (see performance.md).

## Configuration

- `PASSIVE_REFRESH_ENABLED=true`: scheduled pricing enabled when worker/Beat run.
  Setting false disables these two pricing tasks, not catalog/history tasks.
- `PRICE_COLLECTION_CARD_LIMIT=5`: maximum cards per provider batch.
- `PASSIVE_POPULAR_CARD_COUNT=12`: size of recent-interest pool.
- `PASSIVE_POPULAR_BATCH_SIZE=3`: maximum popular slots per batch.
- `PASSIVE_POPULAR_REFRESH_HOURS=1`: popular minimum refresh/retry interval.
- `PASSIVE_CATALOG_REFRESH_HOURS=24`: catalog minimum refresh/retry interval.

## Production activation

The existing `/opt/cardboarddex/ingestion.paused` deployment guard is preserved.
Do not interpret deploying this code as resuming ingestion. Prior worker/Beat
activation on the documented 512 MB host caused whole-host stalls and 502s.
Confirm current instance capacity and container limits before resuming. A RAM
upgrade alone does not change the Compose worker's 96 MB memory limit.

After releasing the reviewed backend image, validate one small targeted batch
for each provider, then resume a single worker (concurrency 1) and one Beat
using the existing Lightsail operations procedure. Remove the pause marker only
as part of that controlled activation. Observe at least a complete daily cycle,
including catalog sync/backup overlap: API health/latency, swap, OOM events,
worker exits, provider errors, daily quota counters, ProviderCardState freshness,
and newly stored observations. If unstable, stop worker and Beat and restore
the pause marker. No paid infrastructure change is included in this work.
