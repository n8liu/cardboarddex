# CardboardDex operations

This tracked runbook covers the active stored-data pipeline. Local notes under ignored `docs/` are optional historical material and are not shipped in a fresh clone. Read `PROJECT_CONTEXT.md` for dated deployment evidence; verify the live host before treating old evidence as current.

## Data sources and preservation

PPT supplies catalog identities, raw market quotes and graded aggregates. `PPT_INGESTION_ENABLED` controls provider requests; `PPT_PRIMARY_ENABLED` controls public visibility. Direct eBay prices are asking listings, not completed sales. Identity and listing eligibility checks apply before statistics. Preserve Cards/Sets schemas and IDs, observation provenance, image keys, durable quotas and checkpoints. Missing prices and sales counts remain unknown.

The catalog projection (`CATALOG_CURRENT_PRICES_ENABLED=true` in production) must be rebuilt and verified before activation. Run `python -m jobs.catalog_prices --help` for supported rebuild, repair and verify commands. Migrations do not run automatically in `release.sh`; stop writers before a projection backfill. Never use `alembic stamp` to bypass a schema mismatch.

Historical provider cutovers require an off-host restored backup, identity/history preservation audit, verified projection and explicit per-series transitions. The existing transition seeding command is `python -m jobs.seed_market_transitions --help`. Do not reseed production or resume ingestion as a side effect of a UI/API release.

## Stored market snapshots

Movers, Sealed and Grading Profit share a worker snapshot publisher. Beat checks every fifteen minutes; each snapshot rebuilds when missing or twelve hours old. Redis retains a successful snapshot for thirty-six hours so a failed rebuild can continue serving it. Keys separate PPT and legacy visibility; grading also versions the asking-price selection rules.

Movers builds every supported language and period together, keeps up to 1,000 rows per direction and reports full matching totals. Grading snapshots store prices; requested grading fees, filters and sorting remain interactive. Sealed applies filters to stored scores and reads history only for the requested page. Image URLs resolve in the API so worker containers do not need the image manifest.

Missing, expired or inaccessible snapshots return 503 with `Retry-After: 60` and `Cache-Control: no-store`. Public requests do not rebuild them. `MARKET_SNAPSHOTS_ON_DEMAND_FALLBACK=true` permits local development fallback when Redis is unreachable; keep it false in production. A reachable but empty Redis needs a seed.

Seed using `python -m jobs.refresh_market_snapshots`; add `--force` only for an intentional rebuild. The command returns nonzero if any snapshot is not ready. Run this inside a separate worker-budget maintenance container, never with `docker exec` in the 160 MiB API container. The release script seeds snapshots before restarting workers.

## Ingestion pauses and maintenance

`/opt/cardboarddex/ingestion.paused` prevents a release from starting worker/Beat. Preserve an existing pause and the rollback host. Removing the marker does not itself start workers; verify actual container state and monitor evidence. The monitor never resumes ingestion automatically.

The separate paused-mode timers refresh stored data only:

- `cardboarddex-live-stats.timer`: Live Comps totals and Trending, every minute.
- `cardboarddex-market-snapshots.timer`: checks market rankings every fifteen minutes, rebuilding only when due.

Install both using [the Lightsail instructions](scripts/lightsail/README.md). They follow the immutable image in the current release, use worker-budget containers and acquire the deployment lock. A shared maintenance mutex allows only one maintenance container at a time; a busy tick skips and retries on its next schedule. A long market rebuild can make a release's 120-second lock wait expire safely; stop the market maintenance service before a planned release rather than deleting the lock file. Neither timer starts provider ingestion. Stop/disable the market timer before rolling back to a release without `jobs.refresh_market_snapshots`.

## Release and verification

1. Record the current release/image digest, schema, pause marker and worker/Beat state. Preserve rollback and backup state.
2. Run isolated local tests, frontend typecheck/build, shell checks and release orchestration tests.
3. If schema changes are included, stop writers and migrate in a worker-budget container. Use `PGOPTIONS='-c statement_timeout=0'` only for the controlled maintenance command when needed. Verify the catalog projection before releasing.
4. Deploy the exact reviewed image/configuration using `scripts/lightsail/release.sh`. Review seed logs and nonzero seed results; a release does not install host timers automatically.
5. Verify readiness and public catalog, Movers, Sealed, Grading Profit, Trending and Live Comps endpoints. Confirm snapshot timestamps advance and warm Movers/Grading reads run no ranking SQL.
6. Observe memory, iowait, refresh times and snapshot bytes. Keep the five-second public SQL and fifteen-second public smoke deadlines. Worker snapshot statements have a separate 120-second limit; this is not evidence that the serving API can run those queries.
7. Confirm provider ingestion separately, only when resumption is authorized. Keep the 48-hour stability check distinct from deployment success.

Production-sized performance checks use an off-host restored PostgreSQL dataset or a separate temporary worker-budget container, read-only transactions, SQL deadlines and memory measurements. Do not run benchmarks inside the serving API. A passing SQLite suite does not establish PostgreSQL latency or memory safety.

## Edge caching

Create the Cloudflare Cache Rule described in [README](README.md#edge-caching-cloudflare) through the authorized account. Origin headers alone do not enable Cloudflare caching. Verify a repeated anonymous request's cache status and age after configuration. Exclude authenticated/admin requests and never cache errors. Snapshot headers allow up to five minutes at the edge while fresh and ten seconds while stale.

## Local checks

From `backend`:

```bash
DATABASE_URL=sqlite:// REDIS_URL=redis://127.0.0.1:1/15 CACHE_REDIS_URL=redis://127.0.0.1:1/15 PPT_PRIMARY_ENABLED=false MARKET_HISTORY_ENABLED=false .venv/bin/pytest
```

From `frontend`: `npm test`, `npm run typecheck`, and `npm run build`.

PostgreSQL/Redis integration tests require disposable `CACHE_TEST_DATABASE_URL` and `CACHE_TEST_REDIS_URL`; never point them at production. Browser checks should cover desktop/mobile filters, Back navigation, compare, grading toggles and reduced-motion behavior.
