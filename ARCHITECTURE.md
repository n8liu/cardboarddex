# CardboardDex architecture

The Next.js frontend reads stored data from FastAPI. Public pricing/catalog requests do not fetch provider prices. Celery performs bounded PPT discovery/refresh work and separate direct eBay asking-listing collection. PostgreSQL stores catalog identities and observations; durable Redis owns quotas, leases and worker progress. Response caches are disposable and separate from quota state.

## Identity and storage

`Cards` and `Sets` retain their schema and existing IDs. PPT mappings live in additive `ppt_products`; uncertain identities are quarantined. Explicit TCGplayer IDs or exact language/set/name/number identify existing cards. New catalog products receive deterministic PPT IDs. Missing set metadata may be enriched without replacing identity.

`ppt_current_quotes` references current observations. `ppt_history` stores dimensioned monthly chunks; `ppt_checkpoints` stores resumable discovery and scheduling. Existing observations, archived provider states, daily market history and image object keys remain intact. Legacy provider identifiers in stored records, indexes and compatibility fields are intentional provenance, not active integrations.

`market_history_transitions` records immutable per-card, language, currency, printing, condition and metric boundaries. Public reads never invent cutovers. Comparable legacy points before the boundary continue into PPT points after it. Unknown conditions stay separate; graded daily averages do not continue asking prices or seven-day medians. Missing days break lines. Original PPT backfill remains available independently.

## Price selection

With the public PPT gate enabled, a matched primary raw PPT quote is preferred. A dated last-known raw quote remains available with stale status. Missing or unmapped PPT prices fall back to dated legacy market values. Graded medians require recent source dates; asking listings are not substitutes. Quarantined mappings cannot supply public PPT history.

Catalog projection version 2 materializes current candidates; rebuild and verify it before cutover. Other readers share the source-selection and history services. Binder history uses batched stored inputs and actual dates; incomplete date coverage is exposed through card counts.

## Jobs and safety

PPT requests share atomic weighted daily/minute quotas and single-flight leases through scheduled and manual paths. Old provider clients and tasks are inert compatibility entrypoints. Direct eBay retains its parser, evidence screening, quotas and schedule. Validated image downloading uses approved origins and preserves existing objects.

PPT health reports expose mapping, stale/due coverage, quarantine, transition and quota diagnostics without credentials. The deployment pause marker, isolated maintenance containers, backup restoration, rollback host and unchanged public smoke deadlines remain operational requirements. See [cutover](docs/ppt-cutover.md) and [current context](PROJECT_CONTEXT.md).
