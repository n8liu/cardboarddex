# CardboardDex

Pokémon card and sealed-product analytics using **Pokémon Price Tracker (PPT)** for catalog discovery, raw market prices and graded sales aggregates. Direct eBay Browse comparisons remain active asking listings, not verified completed sales.

The application includes catalog search, price history, market movers, graded comparisons, Trending, sealed signals, release calendars, Live Comps and a binder. Coverage reflects stored, successfully matched products; missing prices and sales counts are unknown.

## Development

- Frontend: Next.js App Router, React, Tailwind CSS and Recharts in `frontend`.
- Backend: FastAPI, SQLAlchemy, PostgreSQL, Celery and durable Redis in `backend`.
- Copy `.env.example` to a private environment file, configure PostgreSQL/Redis and keep provider credentials server-side. Frontend uses `NEXT_PUBLIC_API_URL`.
- Backend: install `backend/requirements.txt`, run `alembic upgrade head` from `backend`, then `uvicorn app.main:app --reload`.
- Frontend: run `npm ci`, then `npm run dev` from `frontend`. Read the installed Next.js guides before changing framework code.

## PPT migration

Follow [the cutover runbook](docs/ppt-cutover.md) before enabling PPT. This implementation is local; deployment and production verification are separate.

`PPT_INGESTION_ENABLED` controls requests; `PPT_PRIMARY_ENABLED` controls public pricing. Both default to false. Limits default to 20,000 credits/day and 55 weighted requests/minute. Never clear durable quota keys to retry.

The retired provider cannot make requests, including through old queued task names. Existing card/set IDs, image keys, price observations and history remain. “Market price” charts continue with PPT after an immutable per-series boundary. Historical provenance remains truthful; PPT backfill is available separately. Unmapped cards retain dated legacy values. Missing days are not filled with invented prices.

Trending uses **PPT graded sales activity**, ranked by reported `salesByGrade` counts. These counts have provider-defined coverage; they are not 7/30/90-day sales totals. Raw sales volume, price updates and direct eBay asking listings are separate measures.

## Operations and validation

- [Current project context](PROJECT_CONTEXT.md)
- [Architecture](ARCHITECTURE.md)
- [PPT data contract and quotas](docs/pokemon-price-tracker.md)
- [Projection rebuild](docs/catalog-price-projection.md)
- [Direct eBay refresh](docs/passive-refresh.md)
- [Performance verification](docs/performance.md)

Run backend `pytest` from `backend`; frontend `npm test`, `npm run typecheck`, and `npm run build` from `frontend`. PostgreSQL-specific checks require a disposable database. Local tests do not establish production latency, provider coverage or the 48-hour stability window.

Historical documentation is retained in [the pre-migration archive](docs/archive/pre-ppt/README.md); its commands and activation claims are not current instructions.
