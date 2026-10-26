# CardboardDex

Pokémon card and sealed-product analytics using **Pokémon Price Tracker (PPT)** for catalog discovery, raw market prices and graded sales aggregates. Direct eBay Browse comparisons are active asking listings, not verified completed sales.

The application includes catalog search, price history, market movers, graded comparisons, Trending, sealed signals, release calendars, Live Comps and a binder. Coverage reflects stored, successfully matched products; missing prices and sales counts are unknown.

**Market movers lists single cards only; the sealed page lists sealed products only.** Both use `sealed_product()` in `backend/app/services/product_metadata.py`, so a product never appears on both. Explicit PPT or legacy product metadata decides first; without metadata, a blank rarity means sealed.

## Development

- Frontend: Next.js App Router, React, Tailwind CSS and Recharts in `frontend`.
- Backend: FastAPI, SQLAlchemy, PostgreSQL, Celery and durable Redis in `backend`.
- Copy `.env.example` to a private environment file, configure PostgreSQL/Redis and keep provider credentials server-side. Frontend uses `NEXT_PUBLIC_API_URL`.
- Backend: install `backend/requirements.txt`, run `alembic upgrade head` from `backend`, then `uvicorn app.main:app --reload`.
- Frontend: run `npm ci`, then `npm run dev` from `frontend`. Read the installed Next.js guides before changing framework code.
- Local Trending needs a seeded snapshot (`python -m jobs.refresh_trending`) or `TRENDING_ON_DEMAND_FALLBACK=true`. Never enable the fallback in production.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PPT_INGESTION_ENABLED` | false | Allows PPT provider requests (worker only). |
| `PPT_PRIMARY_ENABLED` | false | Serves PPT prices publicly. |
| `CATALOG_CURRENT_PRICES_ENABLED` | false | Catalog price sorts use the verified projection. The API refuses to start unless `python -m jobs.catalog_prices verify` reports ready. **Production requires `true`**; the legacy path misses the 5s deadline and returns 503. |
| `LIVE_FEED_SHARED_CACHE_ENABLED` | true | Unfiltered first-page Live Comps polls share one query per 10s across viewers. |
| `PPT_DAILY_PACING_ENABLED` | true | Spreads the daily PPT credits evenly to 22:00 UTC. |
| `MARKET_SNAPSHOTS_ON_DEMAND_FALLBACK` | false | Local fallback for Movers/Sealed/Grading when Redis is unavailable. Never enable in production. |
| `TRENDING_ON_DEMAND_FALLBACK` | false | Local development only. Builds a missing Trending snapshot on request. |

PPT limits default to 20,000 credits/day and 55 weighted requests/minute. Never clear durable quota keys to retry.

## PPT migration

PPT is the active provider in production. See [project context](PROJECT_CONTEXT.md) for dated cutover evidence and the [operations runbook](OPERATIONS.md) for current safeguards.

The retired provider cannot make requests, including through old queued task names. Existing card/set IDs, image keys, price observations and history remain. “Market price” charts continue with PPT after an immutable per-series boundary. Historical provenance remains truthful; PPT backfill is available separately. Unmapped cards retain dated legacy values. Missing days are not filled with invented prices.

Trending uses **PPT graded sales activity**, ranked by reported `salesByGrade` counts. These counts have provider-defined coverage; they are not 7/30/90-day sales totals. Raw sales volume, price updates and direct eBay asking listings are separate measures.

## Production deploys

A push to `main` builds the backend image and runs `scripts/lightsail/release.sh` on the 1 GB Lightsail host. The release script **never migrates**. Its schema check rejects a release with a new migration and rolls back. For a release that adds a migration:

1. Stop worker and Beat.
2. Run `alembic upgrade head` in a worker-budget `run` container with `PGOPTIONS='-c statement_timeout=0'` (the server default is 12s), plus any verify step the migration needs.
3. Re-run the release.

Never run extra processes inside the 160 MiB API container. If `/opt/cardboarddex/ingestion.paused` exists, the release leaves worker and Beat stopped. See the [Lightsail scripts README](scripts/lightsail/README.md) and [operations runbook](OPERATIONS.md).

## Edge caching (Cloudflare)

Public API reads send `Cache-Control: public, max-age=0, s-maxage=…, stale-while-revalidate=…`. Browsers always revalidate, and a shared cache can hold a response until the backend would rebuild it. `s-maxage` follows the response cache's fresh window: catalog 60s, home 300s; market snapshots up to 300s. Card prices use 120s, live totals 30s, and stale responses 10s. A 503 is always `no-store`.

Cloudflare only caches these if a Cache Rule allows it. This is a one-time dashboard step that a release does not apply:

1. Cloudflare dashboard → `cardboarddex.app` zone → **Caching → Cache Rules → Create rule**.
2. When: hostname equals `api.cardboarddex.app`, method is `GET`, and URI path starts with `/cards/`, `/home/` or `/market/`. Exclude paths starting with `/admin/` or `/telemetry/`.
3. Then: **Eligible for cache**. Edge TTL: **Use cache-control header if present**. Browser TTL: **Respect origin**.
4. Check: `curl -sI 'https://api.cardboarddex.app/cards/search?limit=24' | grep -i cf-cache-status` shows `MISS`, then `HIT` on a repeat.

The per-IP rate limiter only counts requests that reach the origin.

## Operations and validation

- [Current project context](PROJECT_CONTEXT.md)
- [Architecture](ARCHITECTURE.md)
- [Operations runbook](OPERATIONS.md): snapshots, quotas, pauses, migration precautions and release checks
- [Lightsail scripts and timer installation](scripts/lightsail/README.md)

Run backend tests with isolated database/Redis settings from the operations runbook. From `frontend`, run `npm test`, `npm run typecheck` and `npm run build`. PostgreSQL-specific checks require disposable services. Local tests do not establish production latency, provider coverage or the 48-hour stability window.

Historical notes remain in the ignored local `docs/` directory and are not required by a fresh clone.
