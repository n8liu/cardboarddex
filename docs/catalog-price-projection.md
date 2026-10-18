# Catalog current-price projection

Implemented locally on 2026-10-18. The new read path is disabled by default with
`CATALOG_CURRENT_PRICES_ENABLED=false`. No production migration, deployment, or
flag change was performed.

## Behavior and compatibility

Catalog search, Pokémon card-row prices, and set statistics share one selected
price relation. The history path now retrieves selected fields together. The
projection path uses `catalog_price_candidates`: one latest ungraded TCGAPI row
per card, plus currently referenced primary ungraded PPT quotes. It preserves
provider precedence, timestamp/ID ordering, filters, pagination, null/zero price
behavior, currency conventions, and response schemas. Pokémon high/low summaries
retain their existing historical meaning and queries.

PPT eligibility is evaluated at request time using the existing inclusive
seven-day date rule. Expired or removed PPT quotes fall back to the stored TCGAPI
candidate without a worker or a history scan. Broad reads join unique TCGAPI rows
directly and rank only the small PPT snapshot. Selective PostgreSQL PPT reads use
a lateral lookup. SQLite uses an equivalent scalar-ID join for tests.

Migration `0011_catalog_prices` creates only the candidate and projection-state
tables and their indexes/constraints. Cards and Sets are not altered. Candidate
observation IDs are globally unique, and a partial unique index enforces one
TCGAPI candidate per card. Candidates are replaced rather than accumulated.

TCG collection/catalog sync and PPT ingestion maintain candidates in the same
transaction as source changes. Refreshes and backfill use transaction-scoped,
stably ordered per-card advisory locks, with a five-second lock timeout. PPT
removal/quarantine and updates to existing observations refresh candidates too.
Maintenance runs even while projection reads are disabled. New writer code
therefore requires migration 0011 before it starts. No provider calls or quotas
were added. Backfill performs keyset pagination in batches of 250 cards.

The API refuses startup with projection reads enabled unless the version-1 state
records a completed and verified backfill. Cache keys separate projection mode
from history mode and include the projection version; freshness periods remain
unchanged. Readers never repair candidates or fall back to historical selection
when the new mode is enabled. Administrative source edits outside maintained
writers require verification/repair before relying on the projection.

## Rollout and rollback

1. Preserve the normal database backup/rollback prerequisites. Rehearse 0011 on
   PostgreSQL 16 before production activation; local integration evidence below
   uses PostgreSQL 17 because Docker became unavailable.
2. Apply the additive migration, then deploy all maintaining writers and API with
   `CATALOG_CURRENT_PRICES_ENABLED=false`. Confirm there are no old writers left.
3. In the configured backend environment, run:

   ```sh
   python -m jobs.catalog_prices backfill
   python -m jobs.catalog_prices verify
   ```

   Backfill resumes automatically; `--max-batches 1` bounds a rehearsal run.
   `--restart` begins a complete rebuild. Verification compares all candidate
   fields against source selection in a repeatable-read transaction and records
   success only after backfill is complete. A mismatch returns a nonzero exit.
   `python -m jobs.catalog_prices repair` repairs mismatched cards and verifies
   again. Disable projection reads before restart/repair.
4. Run response-parity and performance checks on a representative restored copy.
   Enable the read flag only after verification and acceptance pass. Restart the
   API and verify catalog, Pokémon, and set-statistics canaries in both applicable
   provider modes. Watch request errors, ingestion errors, and database pressure.
5. To roll back reads, disable the flag and restart API services. Keep maintaining
   writers if possible. If rolling back writers too, disable reads first; before
   reenabling later, restart backfill and verify to cover the unmaintained window.
   Do not downgrade/drop projection tables for an application rollback.

Production deployment and PostgreSQL-16 validation are pending, not implied by
successful local tests.

## Reproducible measurements

Supply `CATALOG_TEST_DATABASE_URL` explicitly for a disposable restored database.
Do not point these commands at production. Run from `backend/`:

```sh
python -m scripts.benchmark_catalog --projection off --explain --output /tmp/catalog-before.json
python -m scripts.benchmark_catalog --projection on --explain --measure-ingestion --compare /tmp/catalog-before.json --output /tmp/catalog-after.json
pytest tests/test_catalog_prices_postgres.py
```

The benchmark bypasses response caches and measures connection acquisition, SQL
execution (including statements beginning with WITH), handler execution, and JSON
serialization separately. It does not flush PostgreSQL/OS caches, so these are
uncached application reads, not cold-disk measurements. It takes seven samples
per case/provider mode and records median, nearest-rank p95, raw samples, response
hashes, and bounded EXPLAIN ANALYZE/BUFFERS plans. Optional ingestion measurements
roll back synthetic inserts but consume sequence values.

Acceptance requires identical response hashes and dataset counts, no history
scans in projected search/set-price reads, at least 50% lower median SQL time for
broad price sorts, and no other regression exceeding both 10% and 20 ms. Pokémon
historical summary queries are intentionally excluded from the no-history check.
The benchmark exits nonzero on failure. Ingestion overhead is reported separately.

Local evidence: PostgreSQL 17, restored rehearsal backup with 54,990 cards and
395,797 observations after adding 1,500 explicitly synthetic current PPT quotes.
Backfill completed in 220 batches; all 54,990 cards verified with zero mismatches.
All 20 endpoint/provider benchmark cases had identical response hashes and passed
the acceptance gates. The baseline is the consolidated history path from phase 1.

| Query | History SQL median | Projection SQL median |
| --- | ---: | ---: |
| Legacy price descending | 102.0 ms | 45.6 ms |
| Legacy price ascending | 101.5 ms | 45.3 ms |
| PPT price descending | 312.3 ms | 58.1 ms |
| PPT price ascending | 344.5 ms | 56.9 ms |
| PPT set filter | 101.5 ms | 6.1 ms |
| PPT set statistics | 14.4 ms | 5.1 ms |

A single-card synthetic ingestion probe measured 0.24 ms median for the source
flush versus 3.02 ms including projection refresh. This does not measure provider
latency or production worker throughput. Small regressions remain within the gate:
legacy Pokémon reads measured 46.8 → 49.1 ms and set statistics 6.3 → 6.6 ms.
Raw local reports are under `.system_generated/catalog-prices/` (ignored, not a
production telemetry source).

Validation includes SQLite behavior/parity tests, the backend regression suite,
and real PostgreSQL migration, concurrent writer/backfill, uniqueness, and
transaction-rollback tests. Provider-date expiry is tested without running a
worker. Existing unrelated local changes are preserved.


Temporary validation cleanup: the PostgreSQL 17 cluster was stopped and removed.
The task-created Docker container `cardboarddex-query-validation` could not be
removed because Docker's socket disappeared. When Docker is available again,
remove that specific disposable container with
`docker rm -fv cardboarddex-query-validation`. Existing development containers
were not changed. Benchmark reports remain available in the ignored report folder.
