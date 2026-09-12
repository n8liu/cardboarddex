# CardboardDex Project Context

This is the handoff document for agents working in this repository. Read this file and `AGENTS.md` before changing code. `ARCHITECTURE.md` describes the system boundaries in more detail.

- **GitHub Repository**: [https://github.com/n8liu/cardboarddex.git](https://github.com/n8liu/cardboarddex.git)

## Product goal

CardboardDex is a focused Pokémon trading-card price tracker and National Pokédex browser. PokéAPI serves as the canonical Pokédex and species reference (names, dex IDs, generations, audio cries, and high-resolution official artwork). TCG API is the single catalog and market-price API. eBay is the primary source of verified market comps and graded-card comps.

```text
PokéAPI -> 1,025 Pokémon species + stats + audio cries + official artwork
TCG API -> canonical sets/cards + comprehensive market observations -> PostgreSQL
eBay -> raw listings -> conservative title matching -> verified comps
PostgreSQL -> FastAPI -> Next.js
Card images -> FastAPI cache headers -> Next image optimizer -> Cloudflare R2 / AWS S3 + CDN
```

The browser communicates only with FastAPI (and direct PokéAPI detail caching via Next.js ISR). API keys and provider calls remain server-side.

## Non-negotiable project rules

1. Never use generic or bare `try/except`. Third-party failures must log the exact exception type, message, request path, parameters, status, and useful card context.
2. The existing `sets` and `cards` schemas are sacred. Do not change their columns, constraints, indexes, or migrations without explicit permission.
3. All eBay title interpretation must live in `backend/parsers/title_matcher.py`, with comprehensive edge-case tests.
4. Before implementing a feature, publish a Markdown plan listing every file intended to change.
5. Implement one tested, runnable phase at a time.

## Technology

- Repository: [https://github.com/n8liu/cardboarddex.git](https://github.com/n8liu/cardboarddex.git)
- Frontend: Next.js 16 App Router, Tailwind CSS, Recharts, dynamic client/server cache synchronization, IBM Plex Mono typography.
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2, Alembic.
- Data: PostgreSQL 16 (`cardboarddex` database and user).
- Background work: Celery and Redis with dual-layer rate limiter (burst pacing + daily safety ceiling) and alternating 15-minute price cycling.
- External sources: [PokéAPI](https://pokeapi.co/), [TCG API Cards](https://tcgapi.dev/api/cards/), [TCG API Prices](https://tcgapi.dev/api/prices/), and eBay Developers APIs only.
- Future target: Hybrid Cloudflare Edge (DNS, DDoS WAF, R2 image storage with $0 egress) + AWS Core (RDS PostgreSQL, ElastiCache Redis, ECS Fargate for API & Celery).

## Current state as of 2026-09-11 (updated 2026-09-11)

### Implemented and verified

- **Automated CI/CD & Hybrid Cloud Deployment Architecture (Cloudflare + AWS)**:
  - Containerized backend using multi-stage [`backend/Dockerfile`](backend/Dockerfile) and [`backend/.dockerignore`](backend/.dockerignore) supporting FastAPI (`uvicorn`), Celery Worker, Celery Beat scheduler, and Alembic database migrations.
  - Implemented GitHub Actions CI/CD workflows with monorepo path-filtering:
    1. [`.github/workflows/backend-ci-cd.yml`](.github/workflows/backend-ci-cd.yml): Bytecode compilation checks and 125 `pytest` unit tests (100% pass rate); on `main`, authenticates to AWS via keyless OIDC (`sts:AssumeRoleWithWebIdentity`), builds & pushes to Amazon ECR (`cardboarddex-backend`) with GHA build caching, executes Alembic migrations, and deploys zero-downtime rolling updates across ECS Fargate services (`cardboarddex-api-service`, `cardboarddex-worker-service`, `cardboarddex-beat-service`).
    2. [`.github/workflows/frontend-ci-cd.yml`](.github/workflows/frontend-ci-cd.yml): Node 22 environment running TypeScript typechecking (`tsc --noEmit`) and Next.js build validation on PRs and pushes to `main`.
  - Configured Cloudflare Pages Git integration with Next.js edge adapter (`npx @cloudflare/next-on-pages` with build output `.vercel/output/static` and `nodejs_compat`).
  - Added [`frontend/.npmrc`](frontend/.npmrc) (`legacy-peer-deps=true`) and explicit `react-is` in [`frontend/package.json`](frontend/package.json) ensuring clean Webpack module resolution for `recharts`.
  - Added `respx` and `pytest-cov` in [`backend/requirements.txt`](backend/requirements.txt) for robust HTTP mocking across eBay and TCG API unit tests.
  - Authored comprehensive setup guide [`docs/ci-cd-setup-guide.md`](docs/ci-cd-setup-guide.md) detailing IAM OIDC trust policy, ECR repository, ECS Fargate cluster, Secrets Manager, and Cloudflare Pages setup.

- **Japanese eBay Comp Ingestion & Title Parser Suffix Normalization**:
  - Resolved parameter pass-through in [`backend/jobs/collect_ebay_prices.py`](backend/jobs/collect_ebay_prices.py) passing `is_target_japanese=bool(card.set and card.set.series == "Pokemon Japan")` to `parse_ebay_title`.
  - Refined foreign language filtering in [`backend/parsers/title_matcher.py`](backend/parsers/title_matcher.py) with `RE_NON_JAPANESE_FOREIGN` so Japanese titles (`"Japanese"`, `"Japan"`, `"JP"`, `"JPN"`) are retained while other foreign languages remain rejected.
  - Implemented `extract_core_card_name()` to normalize Japanese titles with set-number suffixes (e.g. `Ivysaur - 002/165`) and parentheticals (`(Master Ball Pattern)`, `(Mirror Holofoil)`), increasing Japanese comp match rates by up to **14.5x** (e.g. SV2a Ivysaur AR jumped from 2 to 29 verified comps).
  - Added dedicated unit tests in `backend/tests/test_title_matcher.py`, bringing the test suite to **109 passing tests** (100% pass rate).

- **Shared Redis Analytics Caching Layer**:
  - Centralized shared `get_redis()` connection factory with graceful degradation in [`backend/app/common/redis.py`](backend/app/common/redis.py).
  - Added shared Redis caching with in-process fallbacks (TTL 300s) to:
    1. [`grading_service.py`](backend/app/services/grading_service.py) (`cardboarddex:grading_profit:{hash}`).
    2. [`sealed_service.py`](backend/app/services/sealed_service.py) (`cardboarddex:sealed_signals:{hash}`).
    3. [`catalog_service.py`](backend/app/services/catalog_service.py) (`cardboarddex:top_volume:{key}`), migrating process-local `_pokemon_volume_cache` across all API workers.

- **Card Detail ➔ National Pokédex Species Bridge**:
  - Added `findPokemonForCardName()` in [`frontend/lib/pokedex-data.ts`](frontend/lib/pokedex-data.ts) matching card names to canonical Pokédex species entries.
  - Integrated into [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx) with hero species badge (`[#0002 Ivysaur] →`), dedicated `Pokédex (Ivysaur)` action button, and a new `Pokédex Species` row in the specifications table linking directly to `/pokemon/[dex_id]`.
  - Updated logo avatar in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) from `"T"` to `"CD"` (CardboardDex).
  - Guarded client-side `getCardSets()` in [`frontend/components/catalog-browser.tsx`](frontend/components/catalog-browser.tsx) to eliminate redundant set re-fetching on mount, and added 24-hour ISR caching in [`frontend/lib/api.ts`](frontend/lib/api.ts).

- **Backend Architecture & Service Layer Decomposition**:
  - Extracted business logic from `backend/app/routers/cards.py` (reduced from 1,819 lines to 864 lines, a >52% reduction) into dedicated services under `backend/app/services/`:
    1. [`catalog_service.py`](backend/app/services/catalog_service.py): Card summaries, species query matchers, word-boundary isolation, and top volume rankings.
    2. [`grading_service.py`](backend/app/services/grading_service.py): Arbitrage spreads, raw vs. PSA 10/9 comps, ROI calculations, fee simulation, and sorting.
    3. [`sealed_service.py`](backend/app/services/sealed_service.py): 4-factor quantitative sealed scoring and product classification.
  - Centralized shared data formatters in [`backend/app/common/formatters.py`](backend/app/common/formatters.py) (`to_decimal`, `parse_iso_datetime`, `normalize_text`, `normalize_card_number`, `escape_like`, `extract_float`), eliminating copy-pasted helpers across ingestion jobs and routers.
  - Added dedicated unit tests in `backend/tests/test_services.py`, `backend/tests/test_title_matcher.py`, `backend/tests/test_cards_api.py`, `backend/tests/test_collect_prices.py`, `backend/tests/test_cycle_prices.py`, and `backend/tests/test_update_pokemon.py`, bringing the test suite to **109 passing tests** (100% pass rate).


- **Single-Command & Batch Pokémon Price Ingestion (TCG API + eBay)**:
  - Added dedicated single-card updater CLI [`backend/jobs/update_card.py`](backend/jobs/update_card.py) to sequentially update both TCG API market prices and eBay comps with a single command:
    ```bash
    .venv/bin/python jobs/update_card.py 28402
    .venv/bin/python jobs/update_card.py "Rayquaza Legends Awakened"
    ```
  - Added dedicated Pokémon character updater CLI [`backend/jobs/update_pokemon.py`](backend/jobs/update_pokemon.py) to update all cards for a specific Pokémon character across both TCG API market prices and eBay comps with progress tracking, rate-limit delays, and error handling:
    ```bash
    .venv/bin/python jobs/update_pokemon.py "Pikachu"
    .venv/bin/python jobs/update_pokemon.py "Charizard" --limit 20
    ```
  - Added `--pokemon <NAME>` and `card_ids: list[str]` support to [`backend/jobs/cycle_prices.py`](backend/jobs/cycle_prices.py), [`backend/jobs/collect_prices.py`](backend/jobs/collect_prices.py), [`backend/jobs/collect_ebay_prices.py`](backend/jobs/collect_ebay_prices.py), and [`backend/jobs/update_card.py`](backend/jobs/update_card.py).
  - Added canonical card resolver `get_cards_for_pokemon()` in [`backend/app/services/catalog_service.py`](backend/app/services/catalog_service.py) with character search-term expansion, digital code-card filtering, and Mew/Mewtwo boundary isolation.
  - Added dedicated unit tests in `backend/tests/test_update_pokemon.py`, bringing the test suite to **105 passing tests** (100% pass rate).

- **Sealed Product eBay Comp Matching Engine**:
  - Implemented dedicated sealed merchandise title resolution in [`backend/parsers/title_matcher.py`](backend/parsers/title_matcher.py) and [`backend/jobs/collect_ebay_prices.py`](backend/jobs/collect_ebay_prices.py).
  - Enforces strict form-factor matching (Booster Boxes, ETBs, Booster Bundles, Collection Cases, Binder Collections, Tins, Blister Packs, UPCs).
  - Isolates sealed cases from single units (`case_mismatch`), filters out single promo extractions from sealed boxes, rejects empty/opened boxes, and separates Pokémon Center exclusive ETBs.
  - Generates verified observations with `condition="Sealed"`, `printing="Sealed"`, and `variant_id=ebay:{card_id}:sealed`.
  - Added 8 dedicated unit tests (32 tests in `test_title_matcher.py`).

- **"Shop on eBay" Direct Marketplace Routing**:
  - Built reusable [`components/shop-ebay-button.tsx`](frontend/components/shop-ebay-button.tsx) featuring a custom 4-color vector eBay logo (`e` red, `b` blue, `a` yellow, `y` green) and white background with a crisp black border (`bg-white border border-black`).
  - High-intent query builder `buildEbaySearchUrl()` intelligently formats queries:
    - Singles: combines `"Pokemon"`, card name, card number with set total (e.g., `199/165`), and set name.
    - Sealed products: strips dummy card numbers (`#`, `N/A`) and generates clean queries.
  - Integrated primary hero button on the card profile page ([`app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx)) and companion button in the price dashboard header ([`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx)).

- **Top 50 Volume Page Direct Pokédex & Card Showcase Navigation**:
  - Clicking any Pokémon icon or name on the Top 50 volume leaderboard ([`components/top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx)) now navigates directly to `/pokemon/[dex_number]` (e.g. `/pokemon/6`), matching the Pokédex page behavior.
  - Displays the full species profile, audio cry, stats, and `<PokemonCardsView>` containing all matching database trading cards with set filters and price comps.
  - Added universal `← Back` navigation in [`components/back-to-pokedex-button.tsx`](frontend/components/back-to-pokedex-button.tsx).

- **Live Comps Ingestion & Freshness Optimization**:
  - Set `{ cache: "no-store" }` on `getCardPricing()` in `frontend/lib/api.ts`, eliminating the 10-minute Next.js static cache delay when new eBay comps are recorded.
  - Preserved individual distinct eBay listings in `latestByVariant` in `frontend/components/price-dashboard.tsx` using `provider_card_id`.

- **Card Profiles Raw eBay Isolation, Volatility Metric & Multi-Series Chart**:
  - Strictly isolated card profile telemetry cards (`Lowest Verified (Raw)`, `Avg Listing (Raw)`, and `Median Listing (Raw)`) in [`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx) to active raw (ungraded) eBay listings only, removing catalog estimates and graded slabs from unauthenticated baseline pricing.
  - Replaced legacy "Store Buylist" with a quantitative **"Volatility"** metric calculating active seller price dispersion ($CV = \sigma / \mu \times 100\%$) alongside standard deviation ($\sigma = \$X.XX$) and financial risk classification (`Low`, `Moderate`, `High`).
  - Upgraded [`components/price-history-chart.tsx`](frontend/components/price-history-chart.tsx) to support 4 synchronized, color-coded lines across dates:
    - 🟢 **Raw eBay Listings** (`#10b981`, Emerald)
    - 🟣 **TCG API Updated Listing** (`#8b5cf6`, Violet)
    - 🟡 **PSA 10 eBay Listings** (`#f59e0b`, Amber)
    - 🔵 **PSA 9 eBay Listings** (`#0284c7`, Sky Blue)
  - Implemented **dynamic Y-axis scaling** based on displayed lines with $\ge 2$ points, preventing isolated 1-point outliers from compressing the scale of primary lines.
  - Added **continuous forward-filling** to today's date (`today`) so every active line extends cleanly to the present until updated, including single-point series.
  - Implemented `<MultiLineTooltip />` displaying all active series simultaneously on hover with individual color dots and formatted currency amounts.
  - Added an interactive timeframe filter button group directly below the chart with instant client-side date slicing for **1 Month (1M)**, **3 Month (3M)**, and **1 Year (1Y)**, with left-edge baseline anchoring.
  - Added interactive sorting for the "Latest variants & pricing data" table allowing one-click sorting by **Date**, **Price**, **Printing Name** (A–Z / Z–A), and **Variant / Condition** with bidirectional toggles (`↑` / `↓`), quick filter toolbar buttons, and clickable table headers.
  - Set `export const dynamic = "force-dynamic"` on [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx) to guarantee instant reflection of new eBay scraping runs without static cache delay.

- **Card Profiles "Avg Listing Price" KPI & Clean Variant Tables**:
  - Replaced legacy "Lowest w/ Shipping" card in [`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx) with a high-fidelity **"Avg Listing Price"** (Average Listing Price) metric card.
  - Dynamically calculates the arithmetic mean across verified active eBay listings with a real-time listing count badge (e.g. "Mean of 21 active eBay listings"), gracefully falling back to TCG active listing estimates or backend `avg_listing_price`.
  - Cleaned the variants table column from "Lowest / Shipping" to "Lowest Price", stripping shipping clutter from card profiles.
  - Added `avg_listing_price` field to `CardPricingResponse` in [`backend/app/schemas/cards.py`](backend/app/schemas/cards.py) and [`backend/app/routers/cards.py`](backend/app/routers/cards.py) with comprehensive unit tests (98 passing backend tests).

- **Frontend Shared Primitives & Bundle Optimization**:
  - Reusable UI primitives under `frontend/components/ui/`:
    - [`back-to-top.tsx`](frontend/components/ui/back-to-top.tsx): Floating glassmorphic "Go to top" button with smooth scrolling and responsive scroll threshold.
    - [`infinite-scroll-sentinel.tsx`](frontend/components/ui/infinite-scroll-sentinel.tsx): `IntersectionObserver`-backed streaming pagination sentinel with manual load more fallback and end indicator.
    - [`search-input.tsx`](frontend/components/ui/search-input.tsx): Monospace search bar with vector search icon, hotkey indicator, and instant clear button.
    - [`empty-state.tsx`](frontend/components/ui/empty-state.tsx) and [`stat-kpi.tsx`](frontend/components/ui/stat-kpi.tsx): Uniform terminal telemetry cards and empty states.
  - Centralized query parameter serialization in `frontend/lib/api.ts` via `buildQueryString()`.
  - Extracted featured Pokémon into `frontend/lib/featured-pokemon.ts` (<1 KB), reducing landing page bundle compilation time from 3.8s to 1.7s.

- **Unified Infinite Scroll Pagination (Catalog Standard)**:
  - Replaced legacy button paginations with continuous infinite scrolling across all 5 major data feeds:
    1. **Card Catalog** (`/catalog`)
    2. **Market Movers** (`/market-movers`)
    3. **Sealed Investment Signals** (`/sealed-signals`)
    4. **Grading Profitability** (`/grading-profit`)
    5. **Live Comps & Ingestion Feed** (`/live-updates`)
  - Features automatic background fetching via `IntersectionObserver` (320px root margin) with manual fallback buttons.

- **Side-by-Side View for Live Comps (`/live-updates`)**:
  - Added a 2-column side-by-side grid (`grid grid-cols-1 lg:grid-cols-2 gap-3.5`) to [`components/live-updates-dashboard.tsx`](frontend/components/live-updates-dashboard.tsx), maximizing data density on wide desktop screens.
  - Interactive view mode toggle in the control bar allowing users to switch between **Side by Side** and **Full Width** on demand.

- **Global Floating "Go to Top" Button**:
  - Added floating smooth-scrolling button to the bottom-right corner across:
    - `/catalog` ([`components/catalog-browser.tsx`](frontend/components/catalog-browser.tsx))
    - `/market-movers` ([`components/market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx))
    - `/sealed-signals` ([`components/sealed-signals-dashboard.tsx`](frontend/components/sealed-signals-dashboard.tsx))
    - `/grading-profit` ([`components/grading-profit-dashboard.tsx`](frontend/components/grading-profit-dashboard.tsx))
    - `/live-updates` ([`components/live-updates-dashboard.tsx`](frontend/components/live-updates-dashboard.tsx))
    - `/pokedex` ([`components/pokedex-browser.tsx`](frontend/components/pokedex-browser.tsx))

- **Theme Alignment & Minimalist Redesign (Movers, Sealed, Grading)**:
  - Aligned Market Movers, Sealed Signals, and Grading Profitability to the landing page's minimalist terminal aesthetic:
    - `font-mono` typography and light `bg-[#f7f8f6]` canvas.
    - Status headers with pulsating emerald indicators (`MOMENTUM RADAR`, `INVESTMENT SIGNALS`, `ARBITRAGE CALCULATOR`).
    - 4-card telemetry KPI grids matching landing page `PLATFORM_STATS`.
    - Stripped word bloat, marketing slogans, bulky black callouts, and rotated promotional ribbons in favor of sleek, data-dense cards.

- **Informative & Simplistic Landing Page (Default Route `/`)**:
  - The default landing page (`/`) is a dedicated, minimalistic **Landing Page** ([`components/landing-page.tsx`](frontend/components/landing-page.tsx)) embodying the IBM Plex Mono technical terminal design language.
  - **Live System Telemetry & Status**: Live pulse badge (`LIVE DATA ENGINE ACTIVE | TCG API + EBAY COMPS`) and 5 key metric cards: **54,480+ cards tracked**, **482 sets synchronized**, **1,025 Pokédex species**, **66,500+ active market prices**, and **15-min staggered pricing refresh engine**.
  - **Universal Quick Search & Jump Bar**: Integrated search input for cards, sets, or species with popular filter chips (*Charizard*, *Pikachu*, *Gengar*, *Umbreon*, *Mewtwo*, *151*, *Evolving Skies*, *Crown Zenith*) and direct CTAs for Pokédex and Catalog.
  - **6 Core Intelligence Modules**: Minimalist interactive cards linking to each core capability:
    1. *National Pokédex* (`/pokedex`)
    2. *Card Catalog* (`/catalog`)
    3. *Market Movers* (`/market-movers`)
    4. *Grading Profitability* (`/grading-profit`)
    5. *Sealed Signals* (`/sealed-signals`)
    6. *Top 50 Volume & Live Comps* (`/top-volume` & `/live-updates`)
  - **Featured Species Showcase**: Visual grid showcasing iconic Pokémon across generations with official high-res artwork, Dex #, and primary type badges linking to `/pokemon/[id]`.

- **National Pokédex Browser (Dedicated Route `/pokedex`)**:
  - Hosted at `/pokedex` ([`app/pokedex/page.tsx`](frontend/app/pokedex/page.tsx)) and powered by [`components/pokedex-browser.tsx`](frontend/components/pokedex-browser.tsx), cataloging all **1,025 Pokémon** across **9 generations** (Gen I Kanto through Gen IX Paldea).
  - Built with canonical static registry ([`lib/pokedex-data.ts`](frontend/lib/pokedex-data.ts)) and direct PokéAPI client ([`lib/pokeapi.ts`](frontend/lib/pokeapi.ts)) with 24-hour Next.js ISR caching (`revalidate: 86400`).
  - **Single-Page Progressive Loading / Infinite Scroll**: Smooth progressive streaming using `IntersectionObserver`, dynamic batch expansion, animated progress bar ("Showing X of Y Pokémon"), "Load More" action, "Show All" instant expander, and shared `<BackToTop />`.
  - **Generation Section Dividers**: Visual full-width divider banners separating each generation with Roman numeral badges, Dex # range, and Pokémon counts.
  - Interactive generation tabs, 18 type filter pills, instant search (name or #dex number), and sorting by Dex # or Name.
  - **Evolution Family Search & Topological Grouping**:
    - Powered by a canonical static evolution registry ([`lib/pokemon-evolutions.ts`](frontend/lib/pokemon-evolutions.ts)) covering all **1,025 Pokémon** across **541 evolution families**.
    - When searching, direct query matches expand to include the entire evolution line (pre-evolutions and evolutions), seamlessly handling cross-generation evolutions (e.g. *Mankey* -> *Primeape* -> *Annihilape #979*, *Eeveelutions*, *Applin*, *Kleavor*).
    - In default Dex sorting (`Dex # (Low → High)`), family members are sequentially grouped in stage order (Root/Baby → Stage 1 → Stage 2) at the primary match's index (e.g., *Pichu #172* is placed alongside *Pikachu #25* and *Raichu #26*).
    - **Interactive User Toggle**: Control bar features an `Evolutions` toggle button (`showEvolutions`, default ON, URL synced with `?evo=0`) allowing users to toggle between full evolution families and strict direct name matches.
    - **Visual Stage Badging**: Search cards display clean, styled status badges: `★ Direct Match (Stage Name)`, `Pre-Evo (Stage Name)`, and `Evolution (Stage Name)`.
    - **Generation Divider Guard**: Suppresses inter-generation divider headers during active evolution searches so family cards stay grouped cleanly without section breaks.

- **Dedicated Pokémon Detail & Trading Cards Showcase (`/pokemon/[id]`)**:
  - Route `/pokemon/[id]` ([`app/pokemon/[id]/page.tsx`](frontend/app/pokemon/[id]/page.tsx)) provides a rich species profile combining PokéAPI data with CardboardDex trading cards.
  - **Pokédex Profile Sequential Cycling & Flanking Arrows** ([`components/pokemon-cycle-nav.tsx`](frontend/components/pokemon-cycle-nav.tsx)):
    - Flanking interactive arrow buttons (`<PokemonArrowButton />`) positioned directly to the left and right of the Pokémon artwork with hover preview tooltips (sprite thumbnail, Dex #, and name).
    - Top breadcrumb cycling header (`<PokemonCycleHeader />`) featuring previous Pokémon (`← #0005 Charmeleon`), direct Pokédex list link, and next Pokémon (`#0007 Squirtle →`).
    - Seamless continuous wrap-around between #1 (Bulbasaur) and #1025 (Pecharunt).
    - Keyboard shortcut cycling (`<PokemonKeyboardCycle />`): press `ArrowLeft` or `ArrowRight` to cycle adjacent profiles instantly without mouse interaction (auto-bypassed when focused in search or input fields).
  - **Hero & Species Profile**: High-resolution official artwork, English/Japanese naming, genus, height, weight, canonical Pokédex flavor text, and base stats BST breakdown.
  - **Interactive Audio Cry Player** ([`components/pokemon-audio-player.tsx`](frontend/components/pokemon-audio-player.tsx)): Plays authentic Pokémon game cries with animated equalizer bars.
  - **Market Intelligence Bar**: Aggregated cards tracked, highest market price, lowest entry price, and quick link to the catalog.
  - **Trading Cards Grid** ([`components/pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx)): Real-time database cards matching the Pokémon with set filter dropdown, sorting, language toggle, and card items linking to `/cards/[id]`.

- **Card Profile Set Navigation & Direct Catalog Routing (`/cards/[id]`)**:
  - In [`app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx), made the set identity interactive across the entire card profile:
    - Clickable category set badge above the card title (`[SET_NAME] →`) linking to `/catalog?set=[set_id]`.
    - Dedicated hero action button: `Browse Set ([SET_NAME])` alongside `Shop on eBay` for immediate collection discovery.
    - Clickable Set row in the specifications table linking directly to the set's cards.
    - Added `findPokemonForCardName()` in [`lib/pokedex-data.ts`](frontend/lib/pokedex-data.ts) to resolve species names from card titles (stripping mechanics like *ex*, *vmax*, *vstar*, *tag team* and trainer prefixes) and provide a direct link to the corresponding `/pokemon/[dex_id]` profile.
  - Seamlessly pre-filters the catalog browser to the specific set, updates the set dropdown, and loads all corresponding trading cards.

- **Typography, Theming & Navigation Header**:
  - **IBM Plex Mono**: Applied globally across the application via Google Fonts preconnect in `app/layout.tsx` and custom typography styling in `app/globals.css`.
  - **Top Navigation Bar ([`components/nav-header.tsx`](frontend/components/nav-header.tsx))**:
    - **Sticky Minimalist Header on Scroll**: Uses `sticky top-0 z-40` with a dynamic scroll listener. At the top of the page, it remains seamless and opaque; as the user scrolls down, it smoothly transitions to a minimalist frosted-glass surface (`bg-white/92 backdrop-blur-md shadow-2xs border-slate-200`) that follows the page without obstructing content.
    - Stripped all unicode emojis to harmonize with the technical terminal/monospace design language.
    - Centered navigation links with clean, uppercase monospace titles: `POKÉDEX`, `CATALOG`, `MOVERS`, `SEALED`, `GRADING`, `TOP 50`, and `LIVE COMPS`.
    - Crisp SVG icons replace unicode emojis across all search inputs, filter sections, button labels, and empty states.

- **Catalog & Set Foundation (English & Japanese)**:
  - Catalog and pricing integration is consolidated under `backend/app/tcgapi/`.
  - TCG API supplies Pokémon sets, cards, image URLs, and per-printing market prices for both English (`game=pokemon`) and Japanese (`game=pokemon-japan`) expansions.
  - Complete database synchronization: **482 sets** (233 English, 249 Japanese), **54,480+ cards**, and **66,500+ active price observations** stored in PostgreSQL.
  - Code cards are automatically excluded from catalog search and browsing.
  - Unrated / sealed items hidden by default (`hide_sealed=true`), with an interactive sidebar toggle.
  - Catalog sorting supports `price_desc` (default), `price_asc`, `number_asc`, `number_desc`, `name`, and `set`.

- **Automated Price Cycling & Alternating 15-Minute Engine**:
  - Unified price cycling engine implemented in [`backend/jobs/cycle_prices.py`](backend/jobs/cycle_prices.py).
  - **Alternating Staggered Mode**: Runs updates every 15 minutes, alternating between **TCG API market prices** (minute :00, :30) and **eBay verified comps** (minute :15, :45), giving each provider a balanced 30-minute refresh rate without API burst spikes.
  - Orders cards by least-recently-synced (`ProviderCardState.last_synced_at.asc().nullsfirst()`).

- **eBay Integration, Title Matching & Shared Token Cache**:
  - eBay OAuth 2.0 application access token client and Browse API search adapter implemented under `backend/app/ebay/client.py` with **Redis-backed token sharing** (`cardboarddex:ebay:oauth_access_token`).
  - Conservative title resolution engine implemented in `backend/parsers/title_matcher.py` with strict word-boundary negative keyword rejection and authentic grading extraction (PSA, BGS, CGC, SGC).
  - Over **17,400+ matched eBay comps** and **1,120+ graded PSA/BGS/CGC/SGC slabs** active in PostgreSQL.

- **Expected Grading Profitability Tab ([`components/grading-profit-dashboard.tsx`](frontend/components/grading-profit-dashboard.tsx))**:
  - Backend endpoint `GET /cards/grading-profit` calculates real-time arbitrage spreads, net profit ($), and ROI (%) between raw cards and PSA 10 / PSA 9 comps across 165+ verified arbitrage pairs.
  - Interactive Grading Fee simulator with live fee slider ($10–$100) and instant presets ($15, $19, $25, $50, $75).

- **Quantitative Sealed Investment Signals Tab ([`components/sealed-signals-dashboard.tsx`](frontend/components/sealed-signals-dashboard.tsx))**:
  - Quantitative analytics engine powered by `GET /cards/sealed-signals`.
  - Deterministic 4-factor scoring model: Supply Scarcity (30%), Buylist Liquidity (25%), Momentum Velocity (25%), and Out-of-Print Vintage Age (20%).
  - Buy signals: `STRONG BUY` ($\ge 75$), `BUY` ($60\text{--}74$), `HOLD` ($45\text{--}59$), `UNDERPERFORM` ($<45$).

- **Top 50 Trending Dashboard Tab ([`components/top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx))**:
  - Restructured 3-column layout powered by backend endpoints `GET /cards/trending`, `POST /cards/track-action`, and `POST /cards/trending/reset`.
  - **Column 1 (Trending Cards)**: Most searched and clicked trading cards, ranked by a blended score of real-time Redis clicks, verified price observation frequency, market value, and 7-day price movement.
  - **Column 2 (Popular Pokémon)**: Most searched and viewed Pokémon characters, ranked by user search heat, character click volume, and card catalog depth.
  - **Column 3 (Volume Leaders)**: Top Pokémon by market dollar volume ($) with active rolling timeframes (`24h`, `7d` default, `30d`, `all_time`, `2026_ytd`), sales transaction comps count, and period-over-period momentum.
  - Responsive multi-column layout with view switcher (`All 3 Columns`, `Cards`, `Pokémon`, `Volume`), timeframe filter pills, and live search. Real user clicks and searches are tracked in Redis via `POST /cards/track-action`.
  - **Single-Increment Analytics Fix**: Resolved duplicate counting by establishing the destination page load as the single source of truth and exempting Trending tab internal navigation with `?ref=trending`.
  - **Pokédex Navigation Reset**: Tab switches reset scroll to `(0, 0)`; scroll position is only restored when returning directly from that Pokémon's profile page.

- **National Pokédex 1,025 Species Dataset & Card Attribution ([`common/pokemon_data.py`](backend/app/common/pokemon_data.py), [`services/catalog_service.py`](backend/app/services/catalog_service.py))**:
  - Centralized `POKEMON_DEX_NUMBERS` containing official Pokédex numbers for all 1,025 Pokémon species.
  - Implemented helpers `get_pokemon_dex_number()`, `get_pokemon_canonical_name()`, and `get_pokemon_sprite_url()` to guarantee valid official PokeAPI artwork endpoints.
  - Master regex matcher `match_to_pokemon()` matches card titles across all 1,025 Pokémon species sorted by length descending, ensuring multi-word and later-generation species (e.g. Zekrom #644, Rayquaza #384, Greninja #658) are correctly attributed without missing icons or `#0000` dex numbers.

- **Instant Tab & Page Shell Loading with Live Status Indicators**:
  - Created reusable [`PageLoadingStatus`](frontend/components/page-loading-status.tsx) component featuring an animated radar ping, spinner, and real-time status text informing the user that the data engine is actively streaming comps.
  - Standardized dedicated `loading.tsx` route handlers across all tab pages and detail views:
    - [`top-volume/loading.tsx`](frontend/app/top-volume/loading.tsx): 3-column Trending skeleton + status badge.
    - [`catalog/loading.tsx`](frontend/app/catalog/loading.tsx): Filters and card grid skeleton + status badge.
    - [`pokedex/loading.tsx`](frontend/app/pokedex/loading.tsx): Generation filters and Pokédex grid skeleton + status badge.
    - [`market-movers/loading.tsx`](frontend/app/market-movers/loading.tsx): Dual gainers/losers skeleton + status badge.
    - [`grading-profit/loading.tsx`](frontend/app/grading-profit/loading.tsx): Arbitrage cards grid skeleton + status badge.
    - [`sealed-signals/loading.tsx`](frontend/app/sealed-signals/loading.tsx): 4-factor signal cards skeleton + status badge.
    - [`live-updates/loading.tsx`](frontend/app/live-updates/loading.tsx): Ticker feed skeleton + status badge.
    - [`pokemon/[id]/loading.tsx`](frontend/app/pokemon/[id]/loading.tsx): Species detail header and cards skeleton + status badge.
    - [`cards/[id]/loading.tsx`](frontend/app/cards/[id]/loading.tsx): Image frame, matrix, chart, and sales table skeleton + status badge.
    - [`loading.tsx`](frontend/app/loading.tsx): Global instant root fallback.
  - Delivers **0ms instant page shell navigation** without blocking the browser while server components await API data.

- **Interactive Landing Page Live Search Autocomplete Dropdown ([`components/search-autocomplete.tsx`](frontend/components/search-autocomplete.tsx))**:
  - Replaced static search input in [`landing-page.tsx`](frontend/components/landing-page.tsx) with a responsive typeahead autocomplete dropdown.
  - Categorizes real-time results into 3 distinct sections:
    1. **Pokémon Species**: Instant matching across all 1,025 Pokédex entries with official artwork thumbnail, name, Pokédex `#`, and elemental type badges.
    2. **Expansions & Sets**: Fast client-side matching across all 468 sets with representative booster/product artwork and series name.
    3. **Cards & Products**: Debounced API queries against `searchCards()` with card image and real-time market price.
    4. **Full Catalog Search Action**: One-click or Enter key submission to search the entire expansion catalog.
  - Backend endpoint `GET /cards/sets` enriched with representative product/card `image_url` for all 468 sets.
  - Complete keyboard accessibility (`ArrowDown`, `ArrowUp`, `Enter`, `Escape`) and click-outside dismissal.

- **Live Updated Items & Market Comps Tab ([`components/live-updates-dashboard.tsx`](frontend/components/live-updates-dashboard.tsx))**:
  - Backend endpoint `GET /cards/live-updates` streams all real-time price observations, verified eBay comps, graded slab sales, and TCG API price syncs in chronological order.
  - Auto-refresh ticker (15s polling with live pulse and pause/resume toggle).
  - Side-by-Side 2-column view with responsive toggle and floating Back-to-Top button.

- **Backend Performance, Comp Matching & Caching (Targeted Enhancements)**:
  - **Japanese eBay Comp Matching** ([`jobs/collect_ebay_prices.py`](backend/jobs/collect_ebay_prices.py)): Passed `is_target_japanese=is_japanese` to the eBay comp collector so Japanese cards query and match Japanese eBay listings correctly.
  - **European Foreign Language Rejection & Core Name Extraction** ([`parsers/title_matcher.py`](backend/parsers/title_matcher.py)): Added `RE_NON_JAPANESE_FOREIGN` to filter out German, French, Italian, and Spanish listings without rejecting Japanese comps, and `extract_core_card_name()` to isolate base species names from card mechanic suffixes. Expanded title matcher unit tests to 36 tests.
  - **Centralized Redis Client** ([`app/common/redis.py`](backend/app/common/redis.py)): Unified Redis connection pool and access via `get_redis_client()` with connection pooling and graceful offline fallback.
  - **Analytical Calculation Caching** ([`services/catalog_service.py`](backend/app/services/catalog_service.py)): Added Redis caching with 300 s TTL for expensive analytical aggregation endpoints: `calculate_grading_profit()`, `calculate_sealed_signals()`, and `calculate_top_pokemon_volume()`.
  - **Catalog Sets SSR Client Guard & ISR** ([`components/catalog-browser.tsx`](frontend/components/catalog-browser.tsx), [`lib/api.ts`](frontend/lib/api.ts)): Guarded client `getCardSets()` to prevent redundant client-side re-fetching when sets are pre-loaded via SSR, and added 24-hour Next.js ISR caching (`revalidate: 86400`) on `getSets()`.
  - **Redis-backed market movers cache** ([`routers/cards.py`](backend/app/routers/cards.py)): Replaced in-process `_MOVERS_CACHE` dict (broken across multiple workers) with a shared Redis key `cardboarddex:movers:{game}:{period}` (TTL 900 s). An in-process `_MOVERS_LOCAL_FALLBACK` dict serves as a graceful degradation layer when Redis is temporarily unavailable. Eliminates redundant TCG API calls when running multiple uvicorn workers or ECS tasks.
  - **Live-updates KPI aggregate query** ([`routers/cards.py`](backend/app/routers/cards.py)): Replaced 3 separate `COUNT(*)` table scans (fired on every 15-second frontend poll) with a single combined `CASE`-aggregate query, Redis-cached for 60 s under `cardboarddex:live_updates:kpi`. Reduces DB round-trips per poll from 4 to 1 (or 0 on cache hit).
  - **Observation payload resolved once per row** ([`routers/cards.py`](backend/app/routers/cards.py)): Extracted `_build_obs_item()` nested helper inside `get_card_prices`. `_resolve_obs_payload()` is now called exactly once per `PriceObservation` row (was called 7× per row inside an inline list comprehension) — eliminates ~21,000 redundant dict merges on a max-size 3,000-observation response.
  - **Redis-backed broken image ID registry** ([`routers/cards.py`](backend/app/routers/cards.py)): Replaced `_BROKEN_IMAGE_IDS: set[str]` (reset on every server restart) with per-card Redis keys `cardboarddex:broken_img:{card_id}` with a 24-hour TTL. Broken IDs now persist across deploys and self-heal after images are restored upstream.
  - **Celery task overlap protection** ([`celery_app.py`](backend/app/celery_app.py)): Added `task_acks_late=True` and `worker_prefetch_multiplier=1` to prevent silent task loss on worker crash. Added `expires` (860 s) and `time_limit` (840 s) to all alternating 15-minute beat tasks so a stalled run is discarded before the next window fires, preventing double API quota consumption. Daily sync task gets `expires=3540` / `time_limit=3480`.
  - **Structured `httpx.Timeout`** ([`tcgapi/client.py`](backend/app/tcgapi/client.py), [`ebay/client.py`](backend/app/ebay/client.py)): Replaced flat 60 s / 30 s scalar timeouts with `httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)` on all outbound HTTP calls. Prevents hung upstream connections from stalling FastAPI worker threads for up to a full minute.

- **Testing & Verification**:
  - Backend pytest suite: **125 passed** with 100% pass rate (`tests/test_trending.py`, `tests/test_services.py`, `tests/test_cards_api.py`, `tests/test_collect_prices.py`, `tests/test_cycle_prices.py`, `tests/test_update_pokemon.py`, `tests/test_foundation.py`, `tests/test_title_matcher.py`, `tests/test_sync_catalog.py`, `tests/test_tcgapi_client.py`, `tests/test_ebay_client.py`).
  - Frontend: TypeScript check (`npm run typecheck`) and Webpack build pass cleanly with **0 errors**. All routes compiled and optimized.

### Database and catalog state

The local PostgreSQL database (`cardboarddex`) has been populated with canonical TCG API IDs using `python -m jobs.sync_catalog --all` and `python -m jobs.sync_catalog --game pokemon-japan --all`. Both English and Japanese sets are supported seamlessly: English sets default to `series="Pokemon"` / `series=None`, while Japanese sets are tagged `series="Pokemon Japan"`. Over **482 sets**, **54,480+ cards**, and **66,500+ active price observations** (including 17,400+ verified eBay comps, 1,120+ graded slabs, and per-printing TCG market prices) are active in PostgreSQL. All card records link to active TCGPlayer/TCG API CDN assets proxied through `/cards/:id/image`.

## Canonical provider behavior

### TCG API

- Base URL: `https://api.tcgapi.dev/v1`.
- Authentication: server-side `X-API-Key`.
- Supported Games:
  - English Pokémon: `game=pokemon` (400+ sets, 34,000+ cards).
  - Japanese Pokémon: `game=pokemon-japan` (453 sets, 40,334 cards covering Japanese sets, Art Rares, Character Rares, and promos).
- Catalog endpoints: `GET /sets?game=pokemon|pokemon-japan` and `GET /sets/:id/cards`.
- Card identity: the TCG API card ID is stored as the canonical `cards.id` for new rows.
- Pricing endpoints (see [Prices API](https://tcgapi.dev/api/prices/)):
  - `GET /cards/:id/prices`: returns per-printing pricing (supports optional `?printing=` filter).
  - `GET /prices/top-movers`: top price gainers and losers (supports `game=pokemon|pokemon-japan`, `direction=up|down`, `period=24h|7d|30d`, `printing`, `type`, `limit`).
  - `GET /bulk/prices`: batch price lookup for up to 500 card IDs (`?ids=1,2,3`).
- Supported printing & variant types: `Normal`, `Holofoil`, `Reverse Holofoil`, `1st Edition`, `Unlimited`.
- Price data fields returned: `printing`, `market_price`, `low_price`, `median_price`, `lowest_with_shipping`, `buylist_price`, `price_change_24h`, `price_change_7d`, `price_change_30d`, and `last_updated_at`.
- Request safety: Redis-backed daily cutoff defaults to 2,000 requests with sub-second sliding-window burst pacing.
- Images: remote provider URLs remain private database implementation details; frontend responses expose only `/cards/:id/image`.

### eBay

- eBay is the primary source for real-world market comps, graded slabs (PSA, BGS, CGC, SGC), active listing comparisons, and sealed Pokémon merchandise (Booster Boxes, ETBs, Booster Bundles, Collection Cases, Binder Collections).
- **Client & OAuth**: `backend/app/ebay/client.py` authenticates via OAuth 2.0 Client Credentials against `api.ebay.com/identity/v1/oauth2/token` and manages auto-refreshing Application Access Tokens cached in Redis (`cardboarddex:ebay:oauth_access_token`).
- **Marketplace Comps Ingestion**: `backend/jobs/collect_ebay_prices.py` queries eBay Browse API (`/buy/browse/v1/item_summary/search`) with rate limiting (`ebay_daily_request_limit`) and flexible search by card name, number, set, ID, or sealed product title.
- **Title Parsing & Resolution**: All eBay title interpretation strictly resides in `backend/parsers/title_matcher.py`. Enforces word-boundary negative keyword rejections (proxies, fakes, custom cards, lots, digital codes, foreign languages, autographs, speculative `"PSA 10?"` claims, and empty/opened sealed boxes). For sealed merchandise, strictly isolates sealed cases from single units and filters out single promo card extractions.
- **Audit & Persistence**: Raw responses are logged to `raw_ebay_listings` (migration `0003_ebay_raw_listings.py`) without touching `cards` or `sets`. Verified matches are deduplicated into `price_observations` with direct eBay item URLs and clean `variant_id` tags (`ebay:{card_id}:sealed` for sealed items).
- **Frontend Integration**: Detail dashboard renders verified eBay comps with interactive direct links to the eBay listing page in the "Latest variants" table.

## Runtime commands

From `backend/`:

```bash
.venv/bin/pytest
PYTHONPATH=. .venv/bin/python -m compileall -q app jobs tests parsers

# Catalog Ingestion
python -m jobs.sync_catalog --all
python -m jobs.sync_catalog --game pokemon-japan --all
python -m jobs.sync_catalog --game all --limit 50

# Price Collection & Alternating Daemon
python jobs/cycle_prices.py --continuous --interval 900 --tcg-limit 50 --ebay-limit 20
python jobs/cycle_prices.py --card-id 28402
python jobs/cycle_prices.py --pokemon "Pikachu"
python jobs/update_card.py --card-id 28402
python jobs/update_card.py "Rayquaza Legends Awakened"
python jobs/update_pokemon.py "Pikachu"
python jobs/update_pokemon.py "Charizard" --limit 20
python jobs/update_card.py --pokemon "Rayquaza"
python jobs/collect_prices.py --limit 50
python jobs/collect_prices.py --card-id 29919
python jobs/collect_prices.py "Rocket's Moltres"
python jobs/collect_ebay_prices.py --limit 50
python jobs/collect_ebay_prices.py "Charizard Base Set"
python jobs/collect_ebay_prices.py "151 Binder Collection"
python jobs/collect_ebay_prices.py "Lugia ex"

# Background Celery Worker
celery -A app.celery_app worker --beat --loglevel=info
```

From `frontend/`:

```bash
npm run dev
npm run typecheck
npm run build
```

From the repository root:

```bash
docker compose up -d
```

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL (`postgresql+psycopg://cardboarddex:cardboarddex@localhost:5432/cardboarddex`). |
| `REDIS_URL` | Celery broker/result backend and shared request limiter (`redis://localhost:6379/0`). |
| `TCGAPI_API_KEY` | Required server-side TCG API key. |
| `TCGAPI_BASE_URL` | Defaults to `https://api.tcgapi.dev/v1`. |
| `TCGAPI_DAILY_REQUEST_LIMIT` | Redis-backed request cutoff; defaults to 2000. |
| `TCGAPI_SYNC_SET_LIMIT` | Maximum newest sets synchronized per run; defaults to 250. |
| `PRICE_COLLECTION_CARD_LIMIT` | Maximum cards processed per pricing batch; defaults to 5. |
| `EBAY_CLIENT_ID` | eBay OAuth client ID (App ID). |
| `EBAY_CLIENT_SECRET` | eBay OAuth client secret (Cert ID). |
| `EBAY_MARKETPLACE_ID` | Defaults to `EBAY_US`. |
| `EBAY_DAILY_REQUEST_LIMIT` | Redis-backed request cutoff; defaults to 500. |
| `BACKEND_CORS_ORIGINS` | Comma-separated frontend origins (allows ports 3000 and 3001). |
| `NEXT_PUBLIC_API_URL` | Browser-visible FastAPI base URL and Next image origin (`http://localhost:8000`). |
| `PSA_VALUE_FEE` | Editable PSA fee used by margin calculations (defaults to $24.99). |

Never commit `.env` or API credentials.

## Prioritized next steps

### 1. Historical Sold-Sales Analytics & Marketplace Insights

- File/verify eBay Application Growth Check for `buy.marketplace.insights` scope to enable historical completed sales ingestion.
- Compute 30/90-day volume-weighted averages, transaction volume, and PSA 10 grading margins against raw market values.
- Add `/cards/:id/sales` and `/cards/:id/stats` endpoints to power dedicated comps filters on the detail page.

### 2. Catalog ingestion optimizations (deduplication & resumable sync buffer)

- Implement in-memory and database-level deduplication for sets and cards to eliminate redundant database writes.
- Introduce Redis-backed `CatalogSyncBuffer` to checkpoint `(set_id, page)` progress, enabling graceful pause on daily request limit (`ProviderRequestLimitExceeded`) and seamless resumption on subsequent runs.
- Optimize TCG API set pagination and page-by-page card ingestion in `TCGAPIClient`.

### 3. Move media and runtime infrastructure to Cloudflare + AWS (Hybrid Architecture)

- Put domain DNS, DDoS protection, and edge caching on Cloudflare.
- Store card images in Cloudflare R2 ($0 egress fees, standard S3 API) and deliver through Cloudflare CDN.
- Run PostgreSQL on RDS, Redis/Celery coordination on ElastiCache, and API/workers on ECS Fargate with secrets in AWS Secrets Manager.

### 4. Product-quality pass

- Add frontend unit and browser tests for search, sidebar filters, responsive layouts, image fallback, and card detail navigation.
- Add observability for provider quota use, sync freshness, failed images, job duration, and eBay match/reject ratios.
- Add watchlists and accounts only after catalog identity and sold-comps quality are stable.