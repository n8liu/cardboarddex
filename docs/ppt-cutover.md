# PPT cutover runbook

This is a prepared rollout procedure, not a deployment receipt. Keep the existing ingestion pause while preparing. Do not restart the retired provider during cutover or rollback. Existing card/set identities and historical source records must survive.

## 1. Preserve and rehearse

Record the active immutable image, frontend release, database revision, worker/Beat status and private configuration. Retain the source/rollback host. Take PostgreSQL and durable Redis backups, verify checksums, and restore them off-host using the existing backup procedure. Preserve quota keys and scheduler checkpoints; do not reset balances.

On the disposable restore, using the new release image, capture a preservation receipt **before** migration/import:

```sh
python -m scripts.ppt_migration_audit > /receipts/ppt-before.json
alembic upgrade head
python -m jobs.catalog_prices backfill
python -m jobs.catalog_prices verify
python -m jobs.seed_market_transitions --apply
python -m scripts.ppt_migration_audit --baseline /receipts/ppt-before.json > /receipts/ppt-after.json
python -m jobs.ppt_report
```

Run these from the backend directory/container with `/receipts` mounted to durable private storage. Audit uses a read-only repeatable snapshot and five-second SQL timeout on PostgreSQL. It hashes existing catalog identities and complete legacy price/history/state rows; added catalog identities are permitted, changed/deleted existing identities are not. A mismatch exits nonzero and stops cutover. Verify source counts and restored backup receipts as well.

Migrations through `0012_market_history_transitions` are required. No Cards/Sets schema change is introduced. Projection verification must report `ready: true` and no mismatches. Transition seeding is resumable, makes no provider requests, and never moves an existing boundary. It chooses a boundary no earlier than the current PPT quote or the day after retained legacy history. Unmapped products remain legacy fallback.

## 2. Verify reads before public visibility

Use an isolated process with `PPT_PRIMARY_ENABLED=true` and `PPT_INGESTION_ENABLED=false`. Check EN/JP cards, sealed, multiple printings, unknown conditions, unmapped/quarantined products, missing grades and stale raw quotes. Confirm earlier chart values are unchanged, matching series continue only after the stored cutover, and the separate PPT backfill view retains older provider points.

Check catalog sorting, home/movers, sealed signals, card pricing, binder totals/history, Live Comps, catalog coverage and Trending graded-sales activity. Missing graded counts remain unknown; explicit zero is valid. Raw-only refresh must not renew a graded snapshot's sync date. Direct eBay must still show screened asking-listing evidence.

Benchmark a production-sized restored PostgreSQL dataset in a separate container with five-second statement limits and peak-memory measurement. Keep public deployment smoke deadlines at 15 seconds. Exercise cold/warm reads with PPT off/on. Local SQLite tests are not a substitute for these measurements.

## 3. Deploy while paused

Apply the rehearsed migrations using the exact new release image, then repeat preservation receipts, projection backfill/verification and transition seeding on the intended database. Coordinate with the deployment lock and keep worker/Beat stopped. Use a separate container with the worker memory budget; **never `docker exec` an extra Python process inside the 160 MiB API container**.

The existing maintenance pattern is:

```sh
docker compose -p app --env-file "$APP_ENV_FILE" -f "$release/docker-compose.prod.yml" \
  run --rm --no-deps -T celery-worker python -m jobs.ppt_report
```

Here `release`, `APP_ENV_FILE`, and exported `BACKEND_IMAGE` must refer to the reviewed release and private configuration, using the same immutable-image validation and deployment lock as `scripts/lightsail/refresh_live_stats.sh`. Substitute the reviewed one-off command from step 1; mount receipt storage when auditing. This does not start the worker service or Beat.

Deploy backend/frontend with PPT ingestion still disabled. Enable `PPT_PRIMARY_ENABLED=true` only after the private read checks pass. Refresh Live Comps totals through the isolated maintenance path and verify advancing snapshots. Cache versions isolate the new response semantics; allow browser/CDN TTLs to expire. Verify public smoke checks, source labels and unchanged API restart counts before proceeding.

## 4. Bounded provider pilot, then ingestion decision

Configure `PPT_API_KEY` only in the private backend environment. Defaults are `PPT_DAILY_CREDIT_LIMIT=20000`, `PPT_MINUTE_WEIGHT_LIMIT=55`, `PPT_BATCH_SIZE=8`. Start a bounded pilot with a smaller daily allowance in an isolated environment/process. If the key already spent credits externally, start after UTC reset or conservatively account for that spend before requesting. Never clear Redis quota keys.

Enable ingestion only for the explicitly reviewed pilot process and run one `python -m jobs.sync_ppt` batch through the shared quota/lease path. Inspect `python -m jobs.ppt_report`, source responses, mapping/quarantine, stored quote/history freshness and the preservation receipt. `python -m jobs.update_card --card-id ID --ppt-only` uses the same gated client for a mapped card. Unmapped IDs need discovery/matching, not forced reassignment.

Resuming scheduled ingestion is a separate operational decision after the pause cause and all release checks are resolved. Then load the reviewed flags and run exactly one worker and one Beat. PPT uses bounded 15-second dispatches; direct eBay retains its own schedule and quotas. The retired tasks remain inert to safely drain old messages. Remove old provider credentials from private configuration after confirming all deployed processes use this release; do not delete historical data or durable progress.

The systemd ingestion monitor runs a separate copy under `/opt/cardboarddex/operations`; deploying an application image does not update it. While paused, check `systemctl cat cardboarddex-ingestion-monitor.service` and confirm its `ExecStart` matches the path below. Back up and update that script from the reviewed current release:

```sh
sudo cp -p /opt/cardboarddex/operations/scripts/lightsail/monitor_ingestion.py /opt/cardboarddex/operations/scripts/lightsail/monitor_ingestion.py.pre-ppt
sudo install -m 0755 /opt/cardboarddex/current/scripts/lightsail/monitor_ingestion.py /opt/cardboarddex/operations/scripts/lightsail/monitor_ingestion.py
```

After resumption, verify a fresh sample includes `ppt` health and PPT credit counters. An old TCGAPI counter is not evidence of current PPT ingestion. Check worker logs for successful `sync_ppt` tasks and advancing product freshness; successful health-report publication alone does not establish provider ingestion success.

Observe quotas/cooldowns, due coverage by segment, quarantine, grading freshness, database/Redis growth, backups, API latency, restarts and memory for 48 hours. Keep the existing automatic pause thresholds and review weekly catalog coverage. Elapsed stability cannot be simulated or declared complete at deployment.

## Rollback

Stop new ingestion and retain the pause marker. Disable PPT public visibility to serve dated legacy fallback; preserve all new tables, quotes, transitions and quota state. Roll back to a reviewed image with ingestion disabled; do not reactivate legacy jobs. A pre-migration image may lack the retirement guard, so worker/Beat must remain stopped. Do not downgrade populated transitions or drop PPT tables. Restore database data only through the established backup recovery procedure after accounting for writes since the backup.

## Intentional legacy references

Stored `tcgapi` source values, old observation fingerprints/local ID hashes, schema/index names, archive filters, old API aliases and inert task/client adapters remain for identity, provenance and compatibility. They are not network integrations. Historical documentation is under `docs/archive/pre-ppt/`; its commands are superseded by this runbook.
