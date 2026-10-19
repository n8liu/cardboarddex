# Direct eBay passive refresh

The passive coordinator now serves direct eBay only, at minutes :15/:45. PPT has its own bounded scheduler and weighted credit accounting; see [PPT](pokemon-price-tracker.md). Legacy provider schedules are retired unconditionally. Existing durable legacy cursors remain archived and are not reused as PPT cursors.

The eBay priority pool uses popularity, recency and the shared market-price selector. Matched PPT product kind takes precedence over archived classification. Eight-card batches allocate priority/hot/catalog work with persistent retries and leases. eBay Browse results are asking listings, not verified completed sales; title parsing and evidence screening remain unchanged.

The global eBay limit is 500 requests/day; scheduled work is capped at 450. `PASSIVE_REFRESH_ENABLED`, `PRICE_COLLECTION_CARD_LIMIT`, `PASSIVE_PRIORITY_CARD_COUNT` and `EBAY_SCHEDULED_REQUEST_LIMIT` retain their meanings. Requests, retries and OAuth consume reservations. Do not clear quota keys.

Run `python -m jobs.passive_refresh_report` for eBay progress and `python -m jobs.ppt_report` for PPT diagnostics in an isolated worker-budget container. Never add a Python process inside the serving API container.

The ingestion monitor retains memory/restart/API/backup pause thresholds, includes PPT quota and health snapshots, and never resumes ingestion automatically. Worker concurrency remains one. Preserve `/opt/cardboarddex/ingestion.paused` during cutover preparation; see [the runbook](ppt-cutover.md).

Historical activation, coverage simulations and earlier dual-provider schedules are archived in [the prior record](archive/pre-ppt/passive-refresh.md). Their elapsed observation windows do not verify the new migration.
