<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Project Overview
We are building a Trading Card Price Tracker (similar to PriceCharting).
The backend handles automated ingestion of catalog and market pricing data (Pokémon Price Tracker / PPT), plus direct eBay asking-listing comparisons.

# Tech Stack
- Frontend: Next.js (App Router), TailwindCSS, Recharts for graphs.
- Backend: Python (FastAPI), PostgreSQL, SQLAlchemy.
- Async Jobs: Celery with Redis for eBay scraping rate-limits.

# AI Agent Rules
1. NEVER use generic try/except blocks without logging the exact error. We are dealing with messy third-party APIs.
2. The database schema is sacred. Do not modify the `Cards` or `Sets` table without my explicit permission.
3. All eBay title parsing logic MUST reside in `backend/parsers/title_matcher.py` and must include comprehensive Unit Tests testing edge-case titles (e.g., "Charizard PSA 10 proxy").
4. Think step-by-step. Whenever asked to build a new feature, output a markdown plan of the files you intend to change before writing any code.
