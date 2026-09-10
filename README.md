# TCGTerminal

A full-stack Pokémon trading card price tracker and market analytics tool. It ingests catalog data and market pricing from TCG API, matching them with verified eBay sold listings and graded slab comps (PSA, BGS, CGC, SGC).

---

## Features

### Catalog & Search
- Over 32,800 English and Japanese cards across 237+ sets.
- Tracks multiple printing variants (Holofoil, Reverse Holo, 1st Edition, Unlimited).
- Search and filter by set, card number, name, and sealed product status.

### Market Movers
- 24-hour, 7-day, and 30-day top price gainers and decliners.
- In-memory stale-while-revalidate (SWR) cache on the backend to handle upstream rate limits smoothly.

### Grading Arbitrage Calculator
- Compares raw card market prices against PSA 10 and PSA 9 comps to calculate potential grading profits and ROI.
- Includes adjustable grading fee presets (PSA Bulk, Value, Regular, CGC/SGC) and break-even safety filters.

### Sealed Product Signals
- Multi-factor scoring model for booster boxes, ETBs, and bundles based on supply scarcity, buylist liquidity, price momentum, and set age.
- Generates rating tiers from Underperform to Strong Buy.

### Volume Leaderboard
- Tracks aggregated market transaction value across top Pokémon characters with Year-over-Year momentum comparisons.

### Live Comps Feed
- Real-time feed of recent price observations, raw sales, and graded slab comps with auto-refresh support.

---

## Tech Stack

- **Frontend**: Next.js 16 (App Router), React 19, Tailwind CSS, Recharts, TypeScript
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Celery
- **Database & Cache**: PostgreSQL 16, Redis 7 (rate limiting + shared token caching)
- **Data Sources**: [TCG API](https://tcgapi.dev) (Catalog & Pricing), eBay Browse API (Comps)

docker compose up -d

cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

cd frontend
npm run dev