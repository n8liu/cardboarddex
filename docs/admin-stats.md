# Admin traffic statistics — phase one

`/admin/stats` is a public login shell; every statistics response is authenticated by FastAPI. It does not expose statistics in HTML or server rendering. No admin link is added to the public navigation. The existing Trending system remains separate. Search, binder, and outbound-link interaction events are deferred to phase two.

## Custom frontend origin

The default admin allowlist includes `https://cardboarddex.nliu.org`. An existing `ADMIN_ALLOWED_ORIGINS` environment variable overrides that default: append the exact HTTPS origin to the production value and recreate the API container to load it. The same setting also authorizes telemetry requests; general API CORS is configured separately.

Origin authorization alone does not enable cross-site browser sessions. The current `SameSite=Strict` admin cookie is not sent from `cardboarddex.nliu.org` to `api.cardboarddex.app`. Use the same-site `https://cardboarddex.app/admin/stats` for authenticated browser access until a same-site API/proxy or a separately reviewed cross-site cookie configuration is available. TestClient authentication tests verify server authorization, not browser cookie policy.

## Definitions and data

- Total visits (page views): browser initial mount/reload, pathname changes, and restored documents from the back/forward cache. Repeat views from the same browser increase visits without increasing unique visitors; equal counts are valid when every browser has only one recorded view. Query-string/filter changes, prefetch, API requests, and auto-refresh polling do not count. Only recognized public routes are accepted. A failed page shell may still count as a visit.
- Unique visitors: distinct HMACs of persistent random browser UUIDs in the period (shared across tabs and reloads, not grouped by IP); this is not a count of verified people. Storage clearing and other devices produce new visitors.
- Sessions: backend-issued IDs after 30 minutes without a tracked page view. Counts measure sessions active in a period, not sessions started in it. No heartbeat or interaction-based activity is implemented in this phase.
- Daily boundaries and all date selections use UTC. Current-day comparisons include the partial current day. Period uniques and sessions are deduplicated across days. Country and page rows can overlap.
- Country: trusted Cloudflare `CF-IPCountry`, otherwise `ZZ` (Unknown). IP addresses are not stored in analytics tables. Existing infrastructure/rate-limit logs have their own policies.
- The browser sends only event UUID, visitor UUID, and normalized pathname. It sends no search text, binder data, referrers, or admin cookies to telemetry. Known bot user agents are excluded, but this is not bot-proof or fraud-proof measurement. Browser blockers, opt-outs, and delivery failures undercount traffic.
- Detailed events have a 90-calendar-day UTC window including today. The retention job physically deletes expired records in 1,000-row transactions. Minimal visitor HMAC/first-seen/last-seen/session records and daily view totals persist for lifetime counts. Deleting/rotating the identity secret breaks visitor continuity; keep it stable and backed up.
- Stats use SQL aggregation over the date-indexed event table, never materialize all events, and never join catalog data. Reports are limited to the last 90 days and top 20 pages. Older period breakdowns are unavailable; lifetime views and visitors remain available.
- The footer explains tracking and provides an opt-out. `Do Not Track: 1` is honored. A blocked localStorage means tracking is skipped. Development and loopback traffic are excluded unless explicitly enabled.

The dashboard separates selected-period metrics from lifetime totals, shows views per visitor (views divided by period uniques), and shows country/page shares of period views. Additional views are views minus period uniques, not a count of returning people. Today is a partial UTC day. Existing historical counts are preserved; missed cache restores cannot be backfilled. Local refinement verification on 2026-10-10: 42 frontend tests, 13 analytics backend tests, TypeScript, and production build passed; this refinement has not been deployed.

## Configuration and local verification

Backend environment:

```
ADMIN_API_KEY=<existing strong admin secret>
ADMIN_COOKIE_SECURE=false
ADMIN_ALLOWED_ORIGINS=http://localhost:3000
ANALYTICS_ENABLED=true
ANALYTICS_IDENTITY_SECRET=<independent random secret of at least 32 characters>
ANALYTICS_TRUSTED_PROXY_CIDRS=
```

Use `ADMIN_COOKIE_SECURE=false` only for local HTTP development. Generate the identity secret with a password manager or `python -c 'import secrets; print(secrets.token_urlsafe(32))'`. Never commit real values. Tracking remains disabled by default and enabling it without a sufficient secret fails settings validation.

Set these in **frontend/.env.local** or the frontend build environment (Next does not automatically load arbitrary values from the root `.env`):

```
NEXT_PUBLIC_ANALYTICS_ENABLED=true
NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL=true
```

If Next.js starts on port 3001 because 3000 is occupied, add `http://localhost:3001` to `ADMIN_ALLOWED_ORIGINS` and use `http://localhost:3001/admin/stats`. Reload/restart the backend after changing its `.env`; Uvicorn does not normally watch that file.

Apply `alembic upgrade head` from `backend/` against the intended local database, start the API and frontend, browse two public pages, then visit `/admin/stats`. Log in with `ADMIN_API_KEY`. A reload adds a view but retains the same visitor; another browser creates a visitor. Countries remain Unknown locally. Verify logout, opt-out, and date changes.

## Production rollout

1. Deploy the backend artifact with tracking disabled. Follow the existing backup/revision rollout procedure: the normal release checks revisions and does not migrate automatically. Apply `0006_site_analytics` using the new artifact **before** its revision check. The migration only creates four analytics/admin tables and two indexes; it does not alter `cards` or `sets`.
2. Configure the backend identity secret and exact admin origin allowlist. Keep `ADMIN_COOKIE_SECURE=true`. Login creates an eight-hour opaque session; only its HMAC is stored. Rotating `ADMIN_API_KEY` revokes existing sessions. Login/logout/stats require an exact Origin match; preview hosts are not implicitly trusted. Every admin/telemetry response uses `Cache-Control: no-store`. Ensure edge cache rules honor this or explicitly bypass these paths.
3. Confirm Cloudflare IP geolocation is enabled. `ANALYTICS_TRUSTED_PROXY_CIDRS` must name **only the actual immediate proxy peer(s)** seen by the API. Confirm the origin is reachable only through the intended Cloudflare Tunnel. Preserve the socket peer by running Uvicorn with `--no-proxy-headers` when enabling this trust check; otherwise forwarded client addresses can replace the peer used for validation. With the current host-network tunnel and loopback-published backend, inspect Docker's actual bridge gateway peer before choosing a /32 or /128. Do not trust all Docker/private/public networks. Verify a forged header through any alternate origin path is rejected or unreachable. Leave the setting empty (Unknown countries) until these checks pass.
4. Install the provided `deploy/lightsail/cardboarddex-analytics-retention.{service,timer}` into `/etc/systemd/system/`, run `systemctl daemon-reload`, then `systemctl enable --now cardboarddex-analytics-retention.timer`. Run the service once and inspect its journal. It executes `python -m jobs.cleanup_analytics` inside the running backend using the existing current-release/env paths, independently of Celery. Monitor timer failures; without it, old raw events are not physically removed even though reports reject old date ranges.
5. Enable backend `ANALYTICS_ENABLED=true`. Build the frontend with `NEXT_PUBLIC_ANALYTICS_ENABLED=true`, `NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL=false`. Use `https://cardboarddex.app/admin/stats`. The host-only API cookie is SameSite=Strict, so the UI/API must share the same site; `pages.dev` previews cannot use the production admin cookie.
6. Verify one new visitor, a repeat view, countries, private response headers, a rejected unauthenticated stats call, logout, and the retention timer. The footer explains collection and opt-out. No history is backfilled.

Telemetry has a 60/minute per-client limit; login 5/minute; reports 30/minute, in addition to existing global limits. The new limits only accept Cloudflare client-IP headers from configured proxy peers. Client events are untrusted and can still be fabricated. Telemetry writes use short transactions, visitor-row serialization, and unique event IDs; failures are logged and returned as 503 without blocking the site. The browser retries once with the same ID.

To disable collection, turn off backend `ANALYTICS_ENABLED` immediately and rebuild the frontend with its tracking flag off. The admin dashboard can still read historical data. Avoid downgrading migration 0006 unless intentionally discarding telemetry and sessions.

## Verification commands

```
# backend/
DATABASE_URL=sqlite:// REDIS_URL=redis://127.0.0.1:1/0 PPT_MINUTE_WEIGHT_LIMIT=55 PPT_API_KEY= EBAY_CLIENT_ID= EBAY_CLIENT_SECRET= .venv/bin/pytest

# frontend/
npm test
npm run typecheck
npm run build
```


Verification on 2026-10-09: 202 backend tests passed (16 opt-in tests skipped), 38 frontend tests passed, TypeScript and production build passed. A separate PostgreSQL 16 integration test passed migration upgrade/downgrade/re-upgrade, unchanged catalog schema, concurrent initial visits/duplicate retries, and UTC reporting with a non-UTC database session. The disposable database was removed. Production deployment and country-header verification completed on 2026-10-10; see the rollout record below.

The PostgreSQL integration test is `backend/tests/test_site_analytics_postgres.py`. It is opt-in via `TEST_ANALYTICS_POSTGRES_URL`, accepts only a loopback PostgreSQL database named `analytics_test`, and must be run against a fresh disposable database because it migrates it.


## Production rollout verified — 2026-10-10 UTC

The stats feature is live at `https://cardboarddex.app/admin/stats` from commit `22869ded33d9c64e2365d440e6e5232c12142163`. The 404 was caused by frontend/backend release mismatch while Backend CI/CD was disabled. The backend was deployed manually after testing its exact AMD64 image and verifying the latest production backup by restoration.

- Database revision: `0006_site_analytics`; Cards and Sets counts remain unchanged.
- Backend tracking is enabled. Cloudflare discarded dashboard-set tracking variables during a rebuild, so its build command now sets `NEXT_PUBLIC_ANALYTICS_ENABLED=true` only for `CF_PAGES_BRANCH=main` and `NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL=false` before running the existing Next.js adapter. Preview branches set tracking false. Final Pages deployment `f2b7c1b9-bdaa-4ccd-b4a5-62d16c8ee436` succeeded; the live layout bundle was verified with the tracker enabled, public flags compiled, and the opt-out UI present.
- Use the existing **production** admin secret. The local preview secret is separate; no production admin-secret rotation was performed.
- Trusted proxy: `172.18.0.1/32`, with Uvicorn forwarded-header trust disabled through `FORWARDED_ALLOW_IPS=`. Country attribution was verified as US over the public Cloudflare path.
- The daily retention timer is installed and its initial run succeeded. Login, stats, secure cookie attributes, no-store responses, origin checks, deduplicated telemetry, and logout passed public verification. The synthetic test visit was removed from analytics afterward.
- Backend CI/CD remains disabled because its pre-existing run `34748756712` is stuck queued. Future backend commits will require a deliberate deployment until that workflow issue is resolved. Existing ingestion remains paused.

The active image digest is `sha256:fbf2bd0f5996712ac8d16db159917bf031c9a7080edf86489937b39a1af54777`; detailed receipts are recorded in `PROJECT_CONTEXT.md`.


The verified Pages build command is:

```sh
if [ "$CF_PAGES_BRANCH" = "main" ]; then export NEXT_PUBLIC_ANALYTICS_ENABLED=true; else export NEXT_PUBLIC_ANALYTICS_ENABLED=false; fi; export NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL=false; npx @cloudflare/next-on-pages
```

Keep this branch gate when changing the build command, or provide equivalent compile-time variables through a verified build configuration. Dashboard variable edits alone did not survive this project's initial rebuild. The production admin endpoint now returns 401 before login and 200 after login; a 401 is expected authentication behavior, not a missing route.
