# Catalog price projection v2

The additive `0011_catalog_prices` tables materialize catalog candidates without changing Cards/Sets. Version 2 retains dated stale raw PPT candidates while graded quotes still require recent evidence. Matched current PPT raw prices take precedence when the public gate is enabled; otherwise dated legacy values remain. Projection readiness is versioned, so version 1 verification cannot activate version 2.

From `backend`, in an isolated worker-budget container targeting the intended database:

```sh
python -m jobs.catalog_prices backfill
python -m jobs.catalog_prices verify
```

Backfill is resumable in bounded batches (`--max-batches` optional). Verification must report `ready: true` with no mismatched cards. `repair` repairs derived candidates and verifies again. These commands do not request provider data or delete source observations. Do not use `--restart` routinely.

Apply migrations through 0012 and seed transitions as described in [cutover](ppt-cutover.md). Verify source-selection parity, query plans, cold/warm latency and memory on a disposable production-sized restore before public rollout. Keep five-second SQL and 15-second public smoke deadlines. Prior version 1 measurements are [archived](archive/pre-ppt/catalog-price-projection.md), not proof for this release.
