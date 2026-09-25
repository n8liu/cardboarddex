# CardboardDex Project Context

Updated: 2026-09-24 UTC. This handoff retains detailed product and implementation context, with dated deployment records and explicit known limitations. Repository: [n8liu/cardboarddex](https://github.com/n8liu/cardboarddex).

Read [AGENTS.md](AGENTS.md) before changing code, including the installed Next.js documentation requirement. Treat source code and dated verification as authoritative when older documents disagree. [ARCHITECTURE.md](ARCHITECTURE.md) describes the system boundaries but still contains outdated deployment and eBay implementation notes.

## Project rules

1. Log the exact error and useful request/card context for third-party failures; do not silently swallow exceptions. Keep credentials and sensitive response fields out of logs.
2. Do not change the existing `cards` or `sets` columns, constraints, indexes, or migrations without explicit permission.
3. Keep all eBay title interpretation in [backend/parsers/title_matcher.py](backend/parsers/title_matcher.py), with edge-case unit tests.
4. Before implementing a feature, publish a Markdown plan listing the files to change. Deliver one tested, runnable phase at a time.
5. Ask before committing or pushing unless already authorized.
6. Update this handoff after implementation when behavior, configuration, verification, or outstanding work changes. Do not append repeated feature histories.

## Product and data boundaries

CardboardDex provides an English/Japanese Pokémon card catalog, price comparisons, a National Pokédex, and a browser-based collection binder.

- **TCG API:** canonical card/set catalog and per-printing market-price observations.
- **eBay Browse API:** active asking-price listings matched by title, including raw cards, graded slabs, and sealed products. A matched title is not proof of authenticity or a completed sale.
- **PokéAPI:** Pokémon details; a bundled registry supports browsing 1,025 species and evolution families.
- **PostgreSQL:** catalog, provider state, price observations, and raw eBay listing records.
- **Redis:** Celery broker/results, provider quotas, analytics, caches, and the eBay application-token cache.

Provider credentials stay server-side. The browser calls FastAPI and also loads external fonts/media; PokéAPI detail fetching is implemented in the frontend's server-rendering path. Binder names/pages/slot-to-card-ID mappings persist in localStorage. Card IDs are sent to the backend for valuation and the resulting valuation is cached server-side.

Catalog image responses use `/cards/{id}/image`. The backend downloads provider images or redirects to configured S3/CDN assets; the Next image optimizer is configured for supported origins. S3 URLs may therefore be visible to clients. CloudFront/custom-domain delivery remains a deployment follow-up, not a verified requirement for existing image delivery.

## Stack and source map

- Frontend: Next.js 16 App Router, React 19, Tailwind CSS 4, Recharts, TypeScript, Vitest. Exact versions: [frontend/package.json](frontend/package.json).
- Backend: Python 3.11+ declared; Docker/CI use Python 3.12. FastAPI, SQLAlchemy 2, Alembic, Celery, Redis, HTTPX, boto3.
- Production deployment: Cloudflare Pages (frontend) with AWS Lightsail Linux VPS ($5.00/month server base; Docker Compose running FastAPI, Celery worker+Beat, PostgreSQL 16 Alpine, Redis 7 Alpine, Cloudflare Tunnel connector) in `us-west-2`, and S3 card asset bucket.
- Local PostgreSQL/Redis: [docker-compose.yml](docker-compose.yml). Backend Docker/CI install [backend/requirements.txt](backend/requirements.txt); they do not currently consume `backend/uv.lock`.

| Area | Entry points |
| --- | --- |
| API setup, CORS, health, headers | [backend/app/main.py](backend/app/main.py) |
| Settings, database, Redis, rate limiting | [backend/app/config.py](backend/app/config.py), [backend/app/database.py](backend/app/database.py), [backend/app/common](backend/app/common) |
| Search, sets, Pokémon card queries | [backend/app/routers/catalog.py](backend/app/routers/catalog.py), [backend/app/services/catalog_service.py](backend/app/services/catalog_service.py) |
| Card detail, prices, images | [backend/app/routers/cards.py](backend/app/routers/cards.py) |
| Movers, grading, sealed signals, live updates | [backend/app/routers/market.py](backend/app/routers/market.py), [backend/app/services](backend/app/services) |
| Trending, action tracking, portfolio valuation | [backend/app/routers/analytics.py](backend/app/routers/analytics.py), [backend/app/services/portfolio_service.py](backend/app/services/portfolio_service.py) |
| Provider adapters and quotas | [backend/app/tcgapi/client.py](backend/app/tcgapi/client.py), [backend/app/ebay/client.py](backend/app/ebay/client.py), [backend/app/providers/limiter.py](backend/app/providers/limiter.py) |
| Catalog, pricing, image jobs | [backend/jobs](backend/jobs), [backend/app/celery_app.py](backend/app/celery_app.py) |
| Browser/server API access and fallback valuation | [frontend/lib/api.ts](frontend/lib/api.ts), [frontend/lib/portfolio.ts](frontend/lib/portfolio.ts) |
| Binder state and UI | [frontend/context/binder-context.tsx](frontend/context/binder-context.tsx), [frontend/components/binder](frontend/components/binder) |
| Pokédex data and species details | [frontend/lib/pokedex-data.ts](frontend/lib/pokedex-data.ts), [frontend/lib/pokeapi.ts](frontend/lib/pokeapi.ts) |
| Deployment workflows | [.github/workflows/backend-ci-cd.yml](.github/workflows/backend-ci-cd.yml), [.github/workflows/frontend-ci-cd.yml](.github/workflows/frontend-ci-cd.yml) |

## Implemented features and interaction details

The following retains the product's visual specifications, interaction behavior, and component locations. These descriptions do not override the pricing, privacy, caching, or deployment limitations recorded below.

- **Interactive Physical Pokémon Portfolio Binder & Valuation Suite (`/binder`)**:
  - **Authentic White Collector Album Binder Experience** ([`frontend/components/binder/binder-page-view.tsx`](frontend/components/binder/binder-page-view.tsx), [`frontend/app/binder/page.tsx`](frontend/app/binder/page.tsx)):
    - **Physical Binder Aesthetics (White Theme)**: Rendered in a clean, pristine White Collector's Album theme matching CardboardDex's design language: crisp white leatherette cover textures (`.binder-leather-cover`), perimeter dashed stitching (`.binder-stitch`), refined silver/chrome metallic corner brackets, heavy metallic 3-ring chrome spine with circular hole punches (`.binder-ring`, `.binder-hole-punch`), and welded polypropylene pocket sleeves (3x3 grid) with diagonal gloss reflections (`.binder-sleeve-gloss`).
    - **Flexible Page Layouts**: Supports **Two-Page Spread (Open Binder)** on desktop displaying 18 slots side-by-side with center rings, as well as **Single Page** 9-pocket mode.
    - **Multi-Page Management**: Smooth page navigation (`Page 1 of N`), direct page tabs (`[P.1]`, `[P.2]`, `[+ Add Page]`), delete page, and keyboard shortcuts (`[` / `]` or `ArrowLeft` / `ArrowRight`).
  - **Client-Side `localStorage` Persistence (Binder Metadata and Card IDs)** ([`frontend/context/binder-context.tsx`](frontend/context/binder-context.tsx)):
    - Stores binder/page names, page IDs, version, and slot-index-to-card-ID mappings under `cardboarddex_binder`; prices are fetched separately. Card IDs are uploaded for backend valuation.
    - Real-time cross-tab synchronization with `storage` and `cardboarddex_binder_updated` window events.
  - **Portfolio Valuation & Historical Valuation Chart (known correctness issues below)** ([`frontend/components/binder/portfolio-value-chart.tsx`](frontend/components/binder/portfolio-value-chart.tsx), [`backend/app/services/portfolio_service.py`](backend/app/services/portfolio_service.py)):
    - Aggregates portfolio market value from cached provider observations using multi-currency formatting (`USD`, `EUR`, `JPY`, `GBP`; fixed conversion rates) and rolling `AnimatedNumber`.
    - Computes 24h, 7d, and 30d value deltas ($ and %) and highlights the Crown Jewel (highest-value card in the binder).
    - Interactive `Recharts` ComposedChart styled in a white card chassis with historical portfolio valuation curves, timeframe filters (`7D`, `1M`, `3M`, `1Y`, `ALL`), SVG emerald gradient fill, dotted crosshair, and date scrubbing.
    - Single-roundtrip batch backend endpoint `POST /cards/portfolio-valuation` with Redis caching (`cardboarddex:portfolio:{hash}`, TTL 300s) and resilient client-side fallback hydration ([`frontend/lib/portfolio.ts`](frontend/lib/portfolio.ts)).
  - **Interactive Pocket Sleeves & Card Picker Spotlight Modal** ([`frontend/components/binder/binder-sleeve-slot.tsx`](frontend/components/binder/binder-sleeve-slot.tsx), [`frontend/components/binder/card-picker-modal.tsx`](frontend/components/binder/card-picker-modal.tsx)):
    - Empty pockets feature dashed slot indicators and glowing `+ Insert Card` actions.
    - Filled pockets display cards with full 3D `HoloCard` tilt perspective and rarity-reactive foil shaders, slot ribbons, live market price tags, and drag-and-drop reorganization between slots.
    - Spotlight modal with debounced search across the ingested card catalog, quick-filter chips (*Charizard*, *Pikachu*, *Gengar*, *Grails $100+*, *Under $20*), language toggles, and 1-click slot insertion.
  - **Top-Right Toolbar & Card Detail Integration** ([`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx), [`frontend/components/binder/add-to-binder-button.tsx`](frontend/components/binder/add-to-binder-button.tsx), [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx)):
    - Positioned as a dedicated top-right action button in the header toolbar, intentionally isolated from the central page navigation links and replacing the static "TCG & eBay Comps" badge. Features a 9-pocket binder icon, text label, and dynamic card count badge (e.g. `Binder 2`).
    - Integrated `<AddToBinderButton>` on card detail pages (`/cards/[id]`) and fallback view with quick-add to next available slot and in-binder slot badge.

- **Interactive Micro-Animations & Productivity Quality of Life (QoL) Suite**:
  - **Holographic Foil 3D Tilt Effect & Rarity-Reactive Shaders on Card Hover** ([`frontend/components/ui/holo-card.tsx`](frontend/components/ui/holo-card.tsx)):
    - Integrated across all card grids in [`frontend/components/card-grid.tsx`](frontend/components/card-grid.tsx), [`frontend/components/pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx), and the hero card on [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx).
    - Mouse-driven 3D card tilt using CSS perspective (`perspective: 800px; transformStyle: preserve-3d`) calculating dynamic `rotateX`, `rotateY`, and `scale3d(1.025)`.
    - **Rarity-Reactive Foil Shaders**: Automatically adapts foil patterns based on card rarity:
      - **Gold / Secret / Hyper Rare**: Warm radiant metallic gold sheen (`#ffd700`, `#ffaa00`, `#ffe680`).
      - **Cosmic Starburst (Special Illustration Rare / Illustration Rare / Art Rare)**: Twinkling celestial starfield with chromatic dispersion.
      - **Ultra / Laser Prism (Ultra Rare / Full Art / VMAX / VSTAR / ex)**: High-contrast diagonal laser spectrum beams.
      - **Classic Holo / Reverse Holo**: Smooth prismatic rainbow sweep.
      - **Satin Glare (Common / Uncommon / Standard)**: Clean soft white specular spotlight without rainbow tints.
  - **Pokémon Type-Themed Atmospheric Ambient Lighting** ([`frontend/app/pokemon/[id]/page.tsx`](frontend/app/pokemon/[id]/page.tsx)):
    - Multi-stop atmospheric gradient lighting tuned to canonical primary and secondary Pokémon types (e.g. Charizard warm ember, Gengar phantom violet, Blastoise oceanic cyan).
    - Features glowing accent border bar, ambient radial spotlight mesh across the hero canvas, and a floating dual-tone glowing podium behind the official artwork.
  - **Interactive Price Chart Area Glow, Dotted Crosshair & Smooth Curve Animations** ([`frontend/components/price-history-chart.tsx`](frontend/components/price-history-chart.tsx)):
    - Upgraded from static `LineChart` to interactive `ComposedChart` with SVG linear gradients (`#rawGradient` with soft 16% emerald area fill).
    - Enabled smooth 700ms cubic-bezier curve draw-in animations (`isAnimationActive={true}`).
    - Added a dotted vertical crosshair line (`strokeDasharray: "3 3"`) and active dots with drop-shadow for interactive date scrubbing.
  - **Species Trading Cards View Parity & Skeleton Cascades** ([`frontend/components/pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx)):
    - Upgraded card grid on `/pokemon/[id]` to use `HoloCard` with rarity foil shaders, multi-currency switching via `useCurrency()`, staggered cascade entrance (`animate-card-cascade`), and base64 SVG shimmer blur placeholders (`shimmerBlurDataUrl`).
    - Replaced generic spinner box with 6-card staggered cascading skeletons during filter and sort updates.
  - **Staggered Card Grid & Table Entrance Cascade**:
    - Added `@keyframes card-cascade` and `.animate-card-cascade` using spring cubic-bezier easing (`300ms cubic-bezier(0.16, 1, 0.3, 1) backwards`) in [`frontend/app/globals.css`](frontend/app/globals.css).
    - Applied staggered `animationDelay` across [`card-grid.tsx`](frontend/components/card-grid.tsx), [`card-table-view.tsx`](frontend/components/card-table-view.tsx), [`pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx), and [`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx), preventing abrupt content popping.
  - **Dynamic Rolling Number Count-Up for Telemetry Stats** ([`frontend/components/ui/animated-number.tsx`](frontend/components/ui/animated-number.tsx)):
    - Smoothly transitions numeric values using `requestAnimationFrame` and an ease-out cubic curve (`1 - (1 - progress)^3`).
    - Respects `prefers-reduced-motion` and supports custom formatters (multi-currency, percentages, and compact abbreviations).
    - Integrated for Set Totals in [`catalog-browser.tsx`](frontend/components/catalog-browser.tsx), Top Surge %, Steepest Drop %, Gainers, and Drops in [`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx), and Tracked Volume & Comps count in [`top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx).
  - **Catalog Dual-Handle Price Range Slider & Backend Price Filtering**:
    - **Dual-Handle Range Slider** ([`frontend/components/ui/price-range-slider.tsx`](frontend/components/ui/price-range-slider.tsx)): Features two draggable styled dots on both ends ($1 to $5,000+ / Any) operating across 12 non-linear stepped price milestones (`[1, 10, 25, 50, 100, 150, 200, 250, 500, 1000, 2500, 5000]`), enabling fine-grained price selection across both budget and mid-tier brackets ($10, $25, $50, $100, $150, $200, $250) while scaling up to grails ($1,000, $2,500, $5,000+). Includes connecting emerald highlight bar, pointer capture dragging, keyboard navigation (`ArrowLeft`/`ArrowRight`/`Home`/`End`), dynamic currency-aware readout badge (`All Prices`, `Under $25`, `$10 – $50`, `$100 – $200`, `$100+`), and milestone tick labels.
    - **Sidebar Integration & Quick Filter Sync** ([`frontend/components/catalog-browser.tsx`](frontend/components/catalog-browser.tsx)): Positioned in the sidebar filter panel; bi-directionally synchronizes with Quick Filter chips (`Under $10`, `$10 – $50`, `$100+ Grails`, `All`) and browser URL query parameters (`?min_price=X&max_price=Y`).
    - **Server-Side Price Querying & Pagination** ([`backend/app/routers/cards.py`](backend/app/routers/cards.py), [`backend/app/services/catalog_service.py`](backend/app/services/catalog_service.py)): Supported `min_price` and `max_price` query parameters in `GET /cards/search` and `GET /cards/sets/{set_id}/stats`, executing database-level subquery filtering on latest market prices with Redis caching and live Set Total price aggregation.
    - **SSR Pre-Fetching** ([`frontend/app/catalog/page.tsx`](frontend/app/catalog/page.tsx)): Pre-fetches filtered cards and set statistics on server components for bookmarked or shared URLs without layout shift.
  - **Quick Filter Chips for Catalog & Movers**:
    - **Catalog Browser** ([`catalog-browser.tsx`](frontend/components/catalog-browser.tsx)): 1-click price filter pills (`All Cards`, `Under $10`, `$10 – $50`, `$100+ Grails`, `Illustration / Specials`) filtering cards through the catalog query state.
    - **Market Movers** ([`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx)): 1-click velocity filter pills (`All Movers`, `Mega Surge (+25%+)`, `Steep Dips (-15%+)`, `High Value ($50+)`, `Budget (<$15)`).
  - **Global Command Palette (`Cmd + K` / `Ctrl + K`)** ([`frontend/components/command-palette.tsx`](frontend/components/command-palette.tsx)):
    - Full-screen spotlight modal listening for `Cmd + K`, `Ctrl + K`, or clicking the header search shortcut.
    - Direct route navigation (`Pokédex`, `Catalog`, `Movers`, `Sealed`, `Grading`, `Trending`, `Live Comps`).
    - Multi-Currency switching (`USD`, `EUR`, `JPY`, `GBP`) directly inside the palette.
    - Live instant Pokémon species search matching against `POKEDEX_DATA`.
    - Live debounced card search via `searchCards()` with thumbnails and real-time market prices.
    - Full keyboard navigation (`↑`, `↓`, `Enter`, `Esc`). Mounted globally in [`frontend/app/layout.tsx`](frontend/app/layout.tsx) with a trigger badge in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx).
  - **High-Density Trader Table View**:
    - Created [`frontend/components/card-table-view.tsx`](frontend/components/card-table-view.tsx) providing a compact, 50px-height tabular view (Rank, Thumbnail, Title & Set, Rarity, TCG Market Value, Last Updated, and Quick Comp Links).
    - Toggleable between Visual Cards and Trader Table in [`catalog-browser.tsx`](frontend/components/catalog-browser.tsx) and [`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx), persisting in `localStorage`.
  - **Multi-Currency Switcher**:
    - Implemented [`frontend/context/currency-context.tsx`](frontend/context/currency-context.tsx) supporting `USD` ($), `EUR` (€), `JPY` (¥), and `GBP` (£) with localized formatting and persistence in `localStorage`.
    - Integrated selector in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) and connected site-wide across all cards, deltas, and aggregated set totals.
  - **Sliding Gliding Pill Navigation Header**:
    - Hardware-accelerated sliding background pill in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) that glides to destination buttons with responsive resize tracking.

- **Zero-Shift Route Loading with Instant Headers & In-Section Indeterminate Progress**:
  - Route shells use stable headings and in-section progress indicators; data grids can still render skeleton placeholders.
  - Route loading states render the final page title, pill badge, and description immediately.
  - Created [`frontend/components/section-loading-bar.tsx`](frontend/components/section-loading-bar.tsx) positioned directly above the data grid, displaying an animated pulse indicator, status label, and continuous indeterminate progress bar (`.section-progress-indeterminate`).

- **Cloudflare Pages Production Resilience & Error Isolation**:
  - Live production frontend deployed at `https://cardboarddex.app` and `https://cardboarddex.pages.dev`.
  - Added smart API endpoint resolution in [`frontend/lib/api.ts`](frontend/lib/api.ts) and [`frontend/next.config.ts`](frontend/next.config.ts): production targets `https://api.cardboarddex.app` through Cloudflare Tunnel, including when a stale Pages environment variable still supplies the generated AWS URL. Local development retains `http://localhost:8000`; generated `*.on.aws` image access has been removed.
  - Dynamic API URL resolution with trailing slash normalization inside `request<T>()`, `getCard()`, `getCardPricing()`, `trackUserAction()`, and `cardImageUrl()` prevents stale module-level hostnames in edge/serverless runtimes.
  - Added [`frontend/components/card-detail-client-fallback.tsx`](frontend/components/card-detail-client-fallback.tsx) with client-side fallback hydration: if Edge SSR encounters a network or runtime error, the card profile dynamically loads data and pricing comps directly from the browser rather than failing with a hard 404 `notFound()`.
  - Added client-side fallback fetching on mount across all dashboards ([`catalog-browser.tsx`](frontend/components/catalog-browser.tsx), [`pokemon-cards-view.tsx`](frontend/components/pokemon-cards-view.tsx), [`market-movers-dashboard.tsx`](frontend/components/market-movers-dashboard.tsx), and [`top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx)) so that if an initial SSR payload is empty or errored (e.g. edge timeouts, provider quota limits), fresh data is fetched client-side immediately upon mount.
  - Instant default load for Live Comps ([`live-updates-dashboard.tsx`](frontend/components/live-updates-dashboard.tsx)): removed the first-mount skip guard so recent comps load immediately on initial page open rather than waiting 15 seconds or requiring filter interaction.
  - Implemented comprehensive error boundary in [`frontend/app/error.tsx`](frontend/app/error.tsx) with technical details toggle, direct action buttons (`Retry Action`, `Reload Application`, `Return to Pokédex`), and API health status check.
  - Added graceful SSR error catching on `/catalog`, `/cards/[id]`, `/live-updates`, and `/top-volume` routes, rendering UI shells rather than 500 error pages on transient backend outages.
  - Disabled navigation prefetching (`prefetch={false}`) in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) to prevent burst 404 / RSC fetch floods on Cloudflare Pages edge, and added `wrangler.toml` specifying `compatibility_flags = ["nodejs_compat"]`.

- **Card Detail ➔ National Pokédex Species Bridge**:
  - Added `findPokemonForCardName()` in [`frontend/lib/pokedex-data.ts`](frontend/lib/pokedex-data.ts) matching card names to canonical Pokédex species entries.
  - Integrated into [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx) with hero species badge (`[#0002 Ivysaur] →`), dedicated `Pokédex (Ivysaur)` action button, and a new `Pokédex Species` row in the specifications table linking directly to `/pokemon/[dex_id]`.
  - Updated logo avatar in [`frontend/components/nav-header.tsx`](frontend/components/nav-header.tsx) from `"T"` to `"CD"` (CardboardDex).
  - Guarded client-side `getCardSets()` in [`frontend/components/catalog-browser.tsx`](frontend/components/catalog-browser.tsx) to eliminate redundant set re-fetching on mount, and added 24-hour ISR caching in [`frontend/lib/api.ts`](frontend/lib/api.ts).

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

- **Card Profiles Raw eBay Isolation, Volatility Metric & Multi-Series Chart**:
  - Strictly isolated card profile telemetry cards (`Lowest Verified (Raw)`, `Avg Listing (Raw)`, and `Median Listing (Raw)`) in [`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx) to raw (ungraded) eBay listing observations, removing catalog estimates and graded slabs from the raw-listing baseline.
  - Replaced legacy "Store Buylist" with a quantitative **"Volatility"** metric calculating seller asking-price dispersion ($CV = \sigma / \mu \times 100\%$) alongside standard deviation ($\sigma = \$X.XX$) and financial risk classification (`Low`, `Moderate`, `High`).
  - Upgraded [`components/price-history-chart.tsx`](frontend/components/price-history-chart.tsx) to support 4 synchronized, color-coded lines across dates:
    - 🟢 **Raw eBay Listings** (`#10b981`, Emerald)
    - 🟣 **TCG API Updated Listing** (`#8b5cf6`, Violet)
    - 🟡 **PSA 10 eBay Listings** (`#f59e0b`, Amber)
    - 🔵 **PSA 9 eBay Listings** (`#0284c7`, Sky Blue)
  - Implemented **dynamic Y-axis scaling** based on displayed lines with $\ge 2$ points, preventing isolated 1-point outliers from compressing the scale of primary lines.
  - Added **continuous forward-filling** to today's date (`today`) so every active line extends cleanly to the present until updated, including single-point series.
  - Implemented `<MultiLineTooltip />` displaying all active series simultaneously on hover with individual color dots and formatted currency amounts, ordered hierarchically from PSA 10 eBay at the top down to Raw eBay at the bottom.
  - Added an interactive timeframe filter button group directly below the chart with instant client-side date slicing for **1 Month (1M)**, **3 Month (3M)**, and **1 Year (1Y)**, with left-edge baseline anchoring.
  - Added interactive sorting for the "Latest variants & pricing data" table allowing one-click sorting by **Date**, **Price**, **Printing Name** (A–Z / Z–A), and **Variant / Condition** with bidirectional toggles (`↑` / `↓`), quick filter toolbar buttons, and clickable table headers.
  - Set `export const dynamic = "force-dynamic"` on [`frontend/app/cards/[id]/page.tsx`](frontend/app/cards/[id]/page.tsx) to request dynamic rendering. Backend response caching and the browser memory cache can still delay updates.

- **Card Profiles "Avg Listing Price" KPI & Clean Variant Tables**:
  - Replaced legacy "Lowest w/ Shipping" card in [`components/price-dashboard.tsx`](frontend/components/price-dashboard.tsx) with a high-fidelity **"Avg Listing Price"** (Average Asking Price) metric card.
  - Dynamically calculates the arithmetic mean across title-matched eBay listing observations with a real-time listing count badge (e.g. "Mean of 21 active eBay listings"), gracefully falling back to TCG active listing estimates or backend `avg_listing_price`.
  - Cleaned the variants table column from "Lowest / Shipping" to "Lowest Price", stripping shipping clutter from card profiles.
  - Added `avg_listing_price` field to `CardPricingResponse` in [`backend/app/schemas/cards.py`](backend/app/schemas/cards.py) and [`backend/app/routers/cards.py`](backend/app/routers/cards.py) with backend unit tests.

- **Frontend Shared Primitives & Bundle Optimization**:
  - Reusable UI primitives under `frontend/components/ui/`:
    - [`back-to-top.tsx`](frontend/components/ui/back-to-top.tsx): Floating glassmorphic "Go to top" button with smooth scrolling and responsive scroll threshold.
    - [`infinite-scroll-sentinel.tsx`](frontend/components/ui/infinite-scroll-sentinel.tsx): `IntersectionObserver`-backed streaming pagination sentinel with manual load more fallback and end indicator.
    - [`search-input.tsx`](frontend/components/ui/search-input.tsx): Monospace search bar with vector search icon, hotkey indicator, and instant clear button.
    - [`empty-state.tsx`](frontend/components/ui/empty-state.tsx) and [`stat-kpi.tsx`](frontend/components/ui/stat-kpi.tsx): Uniform terminal telemetry cards and empty states.
  - Centralized query parameter serialization in `frontend/lib/api.ts` via `buildQueryString()`.
  - Extracted featured Pokémon into `frontend/lib/featured-pokemon.ts` to keep the landing page's featured-data dependency small.

- **Unified Infinite Scroll Pagination (Catalog Standard)**:
  - Replaced legacy button paginations with continuous infinite scrolling across all 5 major data feeds:
    1. **Card Catalog** (`/catalog`)
    2. **Market Movers** (`/market-movers`)
    3. **Sealed Investment Signals** (`/sealed-signals`)
    4. **Grading Profitability** (`/grading-profit`)
    5. **Live Comps & Ingestion Feed** (`/live-updates`)
  - Features automatic background fetching via `IntersectionObserver` (320px root margin) with manual fallback buttons.

- **Theme Alignment & Minimalist Redesign (Movers, Sealed, Grading)**:
  - Aligned Market Movers, Sealed Signals, and Grading Profitability to the landing page's minimalist terminal aesthetic:
    - `font-mono` typography and light `bg-[#f7f8f6]` canvas.
    - Status headers with pulsating emerald indicators (`MOMENTUM RADAR`, `INVESTMENT SIGNALS`, `ARBITRAGE CALCULATOR`).
    - 4-card telemetry KPI grids matching landing page `PLATFORM_STATS`.
    - Stripped word bloat, marketing slogans, bulky black callouts, and rotated promotional ribbons in favor of sleek, data-dense cards.

- **Informative & Simplistic Landing Page (Default Route `/`)**:
  - The default landing page (`/`) is a dedicated, minimalistic **Landing Page** ([`components/landing-page.tsx`](frontend/components/landing-page.tsx)) embodying the IBM Plex Mono technical terminal design language.
  - **Live System Telemetry & Status**: Live pulse badge (`LIVE DATA ENGINE ACTIVE | TCG API + EBAY COMPS`) and 5 key metric cards with animated rolling count-ups ([`animated-number.tsx`](frontend/components/ui/animated-number.tsx)): catalog cards, sets, Pokédex species, market observations, and the staggered pricing-batch schedule. Displayed catalog totals have included hardcoded snapshots; they are not a live inventory guarantee.
  - **Universal Quick Search & Jump Bar**: Integrated search input for cards, sets, or species with popular filter chips (*Charizard*, *Pikachu*, *Gengar*, *Umbreon*, *Mewtwo*, *151*, *Evolving Skies*, *Crown Zenith*), direct CTAs for Pokédex and Catalog, and dedicated Command Palette shortcut (`Cmd + K` / `Ctrl + K`).
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
  - Catalog supports English and Japanese data; dated local/production inventory snapshots are retained in Deployment status below.
  - Code cards are automatically excluded from catalog search and browsing.
  - Unrated / sealed items hidden by default (`hide_sealed=true`), with an interactive sidebar toggle.
  - Catalog sorting supports `price_desc` (default), `price_asc`, `number_asc`, `number_desc`, `name`, and `set`.
  - **Filtered Set Total Price Tag**: Added real-time set market value aggregation (backend endpoint `GET /cards/sets/:id/stats` with Redis 300s cache) and interactive terminal telemetry tag in the top right of the cards view on `/catalog`. Displays complete set dollar value (or filtered subquery total), active priced card ratio (e.g. `165/165 priced`), and average card price tooltip, with SSR pre-fetching in `app/catalog/page.tsx` for instant zero-layout-shift rendering.

- **Expected Grading Profitability Tab ([`components/grading-profit-dashboard.tsx`](frontend/components/grading-profit-dashboard.tsx))**:
  - Backend endpoint `GET /cards/grading-profit` calculates estimated spreads, profit ($), and ROI (%) between raw observations and PSA 10 / PSA 9 asking-price comps. Fixed probabilities and omitted costs limit the model; see open work.
  - Interactive Grading Fee simulator with live fee slider ($10–$100) and instant presets ($15, $19, $25, $50, $75).

- **Quantitative Sealed Investment Signals Tab ([`components/sealed-signals-dashboard.tsx`](frontend/components/sealed-signals-dashboard.tsx))**:
  - Heuristic analytics engine powered by `GET /cards/sealed-signals`.
  - Deterministic 4-factor scoring model: Supply Scarcity (30%), Buylist Liquidity (25%), Momentum Velocity (25%), and Out-of-Print Vintage Age (20%).
  - Buy signals: `STRONG BUY` ($\ge 75$), `BUY` ($60\text{--}74$), `HOLD` ($45\text{--}59$), `UNDERPERFORM` ($<45$).

- **Top 50 Trending Dashboard Tab ([`components/top-volume-dashboard.tsx`](frontend/components/top-volume-dashboard.tsx))**:
  - Restructured 3-column layout powered by backend endpoints `GET /cards/trending`, `POST /cards/track-action`, and `POST /cards/trending/reset`.
  - **Column 1 (Trending Cards)**: Most searched and clicked trading cards, ranked by a blended score of real-time Redis clicks, price observation frequency, market value, and 7-day price movement.
  - **Column 2 (Popular Pokémon)**: Most searched and viewed Pokémon characters, ranked by user search heat, character click volume, and card catalog depth.
  - **Column 3 (Volume Leaders)**: Top Pokémon by summed observation value ($) with rolling timeframes (`24h`, `7d` default, `30d`, `all_time`, `2026_ytd`), observation count, and period-over-period momentum.
  - Responsive multi-column layout with view switcher (`All 3 Columns`, `Cards`, `Pokémon`, `Volume`), timeframe filter pills, and live search. Real user clicks and searches are tracked in Redis via `POST /cards/track-action`.
  - **Navigation Attribution**: Card detail GETs record views except when `?ref=trending`; explicit tracking uses `POST /cards/track-action`. Cached requests and untrusted clients limit how accurately these represent unique user activity.
  - **Pokédex Navigation Reset**: Tab switches reset scroll to `(0, 0)`; scroll position is only restored when returning directly from that Pokémon's profile page.

- **National Pokédex 1,025 Species Dataset & Card Attribution ([`common/pokemon_data.py`](backend/app/common/pokemon_data.py), [`services/catalog_service.py`](backend/app/services/catalog_service.py))**:
  - Centralized `POKEMON_DEX_NUMBERS` containing official Pokédex numbers for all 1,025 Pokémon species.
  - Helpers `get_pokemon_dex_number()`, `get_pokemon_canonical_name()`, and `get_pokemon_sprite_url()` resolve canonical species identity and construct official-artwork URLs.
  - Master regex matcher `match_to_pokemon()` matches card titles across all 1,025 Pokémon species sorted by length descending, ensuring multi-word and later-generation species (e.g. Zekrom #644, Rayquaza #384, Greninja #658) are correctly attributed without missing icons or `#0000` dex numbers.

- **Interactive Landing Page Live Search Autocomplete Dropdown ([`components/search-autocomplete.tsx`](frontend/components/search-autocomplete.tsx))**:
  - Replaced static search input in [`landing-page.tsx`](frontend/components/landing-page.tsx) with a responsive typeahead autocomplete dropdown.
  - Categorizes results into three sections plus a full-catalog search action:
    1. **Pokémon Species**: Instant matching across all 1,025 Pokédex entries with official artwork thumbnail, name, Pokédex `#`, and elemental type badges.
    2. **Expansions & Sets**: Fast client-side matching across the fetched sets with representative booster/product artwork and series name.
    3. **Cards & Products**: Debounced API queries against `searchCards()` with card image and fetched market price.
    4. **Full Catalog Search Action**: One-click or Enter key submission to search the entire expansion catalog.
  - Backend endpoint `GET /cards/sets` enriched with representative product/card `image_url` for the fetched sets.
  - Complete keyboard accessibility (`ArrowDown`, `ArrowUp`, `Enter`, `Escape`) and click-outside dismissal.

- **Live Updated Items & Market Comps Tab ([`components/live-updates-dashboard.tsx`](frontend/components/live-updates-dashboard.tsx))**:
  - Backend endpoint `GET /cards/live-updates` streams all real-time price observations, title-matched eBay comps, graded slab asking-price observations, and TCG API price syncs in chronological order.
  - Auto-refresh ticker (15s polling with live pulse and pause/resume toggle).
  - Side-by-Side 2-column view with responsive toggle and floating Back-to-Top button.

- **Frontend Bundle Optimization & ISR Prerendering**:
  - **Dynamic Command Palette Code-Splitting** ([`frontend/components/command-palette-lazy.tsx`](frontend/components/command-palette-lazy.tsx), [`frontend/app/layout.tsx`](frontend/app/layout.tsx)): Deferred the large Pokédex dataset from initial page loads by dynamically importing `CommandPalette` on the client with `ssr: false`.
  - **Static Generation & ISR** ([`frontend/app/page.tsx`](frontend/app/page.tsx), [`frontend/app/pokedex/page.tsx`](frontend/app/pokedex/page.tsx)): Enabled static HTML prerendering on the homepage and 24h Incremental Static Regeneration (`revalidate = 86400`) on `/pokedex`. Actual latency depends on deployment and cache behavior.

## Backend, caching, and rendering details

### Route ownership and loading components

| Router | Public routes |
| --- | --- |
| `catalog.py` | `/cards/search`, `/cards/sets`, `/cards/sets/{set_id}/stats`, `/cards/pokemon/{name}` |
| `market.py` | `/cards/market-movers`, `/cards/grading-profit`, `/cards/sealed-signals`, `/cards/live-updates` |
| `analytics.py` | `/cards/top-pokemon-volume`, `/cards/trending`, `/cards/trending/reset`, `/cards/track-action`, `/cards/portfolio-valuation` |
| `cards.py` | `/cards/{card_id}`, `/cards/{card_id}/prices`, `/cards/{card_id}/image` |

- Business logic lives in catalog, grading, sealed, trending, and portfolio services. `cards.py` retains some compatibility re-exports; use the owning router/service for new changes.
- [page-loading-status.tsx](frontend/components/page-loading-status.tsx) and [section-loading-bar.tsx](frontend/components/section-loading-bar.tsx) provide shared status/progress visuals. Route `loading.tsx` files cover catalog, card/species detail, Pokédex, binder, and analytical dashboards; grid skeletons and client fallback states complement the route shells.
- [back-to-top.tsx](frontend/components/ui/back-to-top.tsx) supplies the floating scroll action across catalog, movers, grading, sealed, live updates, and Pokédex views. Species navigation also uses sessionStorage to restore its last viewed position.

### Catalog queries and cache layers

- Catalog search uses `_SEARCH_LOCAL_CACHE` (60-second TTL) and Redis `cardboarddex:catalog:search:{params}` (300-second TTL). Sets use `_SETS_LOCAL_CACHE` (300 seconds) and `cardboarddex:catalog:sets:{game}` (3,600 seconds).
- Search and set statistics accept `min_price`/`max_price`, filter latest-price subqueries, and support server-rendered bookmarked URLs. Catalog search uses the composite observation index `ix_price_observations_search_lookup`.
- [api.ts](frontend/lib/api.ts) supplies Next revalidation options for search/set-statistics requests and a separate browser GET cache (60 seconds) with in-flight request deduplication. The browser cache currently ignores callers' `no-store` intent and does not evict old keys.
- [catalog-browser.tsx](frontend/components/catalog-browser.tsx) avoids an immediate redundant set fetch when SSR already supplied sets. [next.config.ts](frontend/next.config.ts) configures AVIF/WebP, qualities 70/75/80, and a minimum cache TTL of 2,678,400 seconds (31 days). SVG optimization is allowed with attachment disposition and a sandboxed image CSP; local-IP allowance is enabled only for the configured local API origin.
- `.card-cv` and `.table-row-cv` use `content-visibility: auto` to reduce offscreen work. [shimmer.ts](frontend/lib/shimmer.ts) generates base64 SVG blur placeholders.
- The catalog summary code assumes USD for TCG observations. Validate currency/printing consistency before broadening provider support.
- Redis-backed analytical caches use `cardboarddex:grading_profit:{hash}`, `cardboarddex:sealed_signals:{hash}`, and `cardboarddex:top_volume:{key}` with 300-second TTLs. Their local fallbacks currently have no eviction.

### Market, trending, and pricing responses

- Market movers cache both directions under `cardboarddex:movers:{game}:{period}` for 900 seconds, with `_MOVERS_LOCAL_FALLBACK` for local/stale fallback. Concurrent misses are not coalesced across workers.
- `_build_mover_item()` accepts alternate upstream keys for card identity, price, and percentage change. `_compute_db_market_movers()` falls back to provider state and observations. Its final arbitrary-candidate fallback needs removal; nonempty results do not establish actual movement.
- [market.py](backend/app/routers/market.py) creates the interactive TCG client without the job quota-acquisition callback. Review quota accounting for interactive provider fetches independently of Celery limits.
- Live updates aggregate provider/graded counts with a combined `CASE` query and Redis `cardboarddex:live_updates:kpi` (60 seconds). The unfiltered total count is also cached for 60 seconds.
- Card prices resolve each observation payload once via `_resolve_obs_payload()`/`_build_obs_item()`, exposing selected pricing fields rather than raw provider payloads.
- Latest-variant grouping includes `provider_card_id` to preserve distinct eBay listings. Raw asking-price averages use `_trim_outliers_iqr()` when enough observations exist.
- `GET /cards/{id}/prices` accepts a bounded `days` parameter, but observations with null `provider_updated_at` currently bypass the cutoff and response rows are not capped.
- Trending records card views/clicks, Pokémon activity, and search terms. In-memory tracking dictionaries have a 2,000-entry cap; Redis sorted sets are periodically trimmed. Cache invalidation uses `scan_iter()`, and `TrackActionRequest.entity_id` has length/pattern validation. These controls do not prevent fabricated activity or bound every analytical response cache.
- All eBay observations are asking-price comps. The UI's historical “sales” labels and volume calculations are documented limitations.

### Images and API protections

- `get_card_image()` validates card IDs against an alphanumeric/underscore/hyphen pattern with a 64-character maximum.
- With `S3_BUCKET_NAME`, it checks the public asset URL and returns a cacheable `307` redirect when present. Otherwise it fetches the provider image, synchronously uploads through a shared boto3 client, and returns the bytes.
- S3 keys are `cards/{card_id}.png`; stored Content-Type comes from the downloaded image. Asset responses use one-year immutable cache headers. Image URLs are stable rather than content-versioned.
- Missing/broken images use a local SVG placeholder and Redis `cardboarddex:broken_img:{card_id}` for 24 hours. Failed requests can therefore continue showing placeholders until expiry.
- [sync_images_to_s3.py](backend/jobs/sync_images_to_s3.py) uses a thread pool for download/upload work. Options include `--limit`, `--all`, `--set-id`, `--workers`, `--overwrite`, `--bucket`, and `--region`; there is no `--concurrency` or `--card-id` option.
- TCG outbound calls use HTTPX connect/read/write/pool timeouts of 5/30/10/5 seconds; eBay uses 5/25/10/5. Requests retry selected 429/5xx failures with backoff. These are per-operation timeouts, not whole-job deadlines.
- The API's Redis rate limiter uses fixed windows; its in-memory fallback uses a sliding window. Images have a separate 6,000/minute bucket. Proxy-header trust and heavy-endpoint enforcement remain open issues.
- CORS uses exact configured origins plus an anchored production/preview/development regex. CORS does not authenticate non-browser clients.
- Successful API responses receive CSP, HSTS, nosniff, framing, and referrer headers. Generic 500 responses mask exception details while logging errors server-side. Frontend HTML needs its own policy.
- `POST /cards/trending/reset` requires `X-Admin-Token`; unconfigured admin access is disabled. Listing links are restricted to HTTP(S) and eBay/TCGPlayer domains.
- PostgreSQL pooling uses `pool_size=15`, `max_overflow=15`, `pool_timeout=5.0`, and `pool_recycle=1800`. Total connections still depend on process/task count.
- Public read routes set Cache-Control directives, but headers alone do not prove Cloudflare caches a response or establish a cache-hit percentage.

### Job durability and deployment mechanics

- Catalog ingestion checks existing observation fingerprints to avoid duplicate inserts. Current tables separate catalog identity, provider state, normalized observations, and raw eBay listings; catalog schemas remain protected.
- Price batches prefer least-recently-synced cards. Manual CLI targeting supports canonical card IDs, card-name queries, and Pokémon species through `get_cards_for_pokemon()`, including name expansions and Mew/Mewtwo isolation.
- Scheduled pricing tasks expire after 860 seconds with an 840-second hard limit. Catalog sync expires after 3,540 seconds with a 3,480-second hard limit. Late acknowledgement/prefetch settings do not replace distributed overlap protection.
- The Dockerfile builds dependencies in a separate stage and runs the application as an unprivileged user. It can run FastAPI or a worker command supplied by Docker Compose.
- Prepared backend CI runs application/deployment tests, publishes an AMD64 SHA-tagged image, and deploys its digest with matching Compose configuration over verified SSH. It checks schema revision without applying migrations. The recovery image is active; source publication remains pending as recorded below.
- Frontend CI uses Node 22, `npm ci`, TypeScript checking, and a webpack production build. It currently omits `npm test`.
- Cloudflare Pages Git integration was previously configured with `@cloudflare/next-on-pages`; both Wrangler files name `.vercel/output/static` as the output and enable `nodejs_compat`. The adapter is not pinned in `frontend/package.json`; verify the live Pages build configuration before changing deployment tooling.
- `frontend/.npmrc` enables `legacy-peer-deps=true`, and `react-is` is an explicit dependency for Recharts compatibility.
- `/health?details=true` reports database/Redis connectivity, not latency or active connection counts. `/health/quotas` exists but reads keys inconsistent with the provider limiter.

## Provider and job behavior

### TCG API

[TCGAPIClient](backend/app/tcgapi/client.py) defaults to `https://api.tcgapi.dev/v1` with server-side `X-API-Key`. It calls `/sets`, `/sets/{id}/cards`, `/cards/{id}`, `/cards/{id}/prices`, `/prices/top-movers`, and `/bulk/prices`. Game identifiers are `pokemon` and `pokemon-japan`; canonical provider IDs identify catalog cards, with long IDs normalized by `local_card_id()`.

[Catalog sync](backend/jobs/sync_catalog.py) upserts sets/cards and stores pricing observations/provider state. Japanese sets use `series="Pokemon Japan"`. Pagination, deduplication, and Redis cursor helpers already exist; reliable per-page resumption remains unfinished. The quota-error path checkpoints the final selected set rather than the last successfully processed set. Also, `--all` currently passes `None` into a function that falls back to the configured set limit, so it does not guarantee an unlimited sync.

### eBay

[EbayClient](backend/app/ebay/client.py) uses OAuth client credentials and Browse item-summary search. Application tokens are shared through Redis. [collect_ebay_prices.py](backend/jobs/collect_ebay_prices.py) records raw listings and deduplicated observations after [title matching](backend/parsers/title_matcher.py). The matcher covers proxy/fake, lot, language, speculative grade, and sealed-product edge cases.

No completed-sales ingestion is implemented. Raw listing rows are updated on repeat ingestion; they are not an immutable event archive.

### Provider payloads and matching rules

TCG request details supported by the adapter:

| Endpoint | Parameters / behavior |
| --- | --- |
| `GET /sets` | `game`, `page`, `per_page`; pagination uses provider metadata or page length. |
| `GET /sets/{id}/cards` | Paginated card ingestion; attaches set identity to each record. |
| `GET /cards/{id}` | Provider card detail for identity/pricing ingestion. |
| `GET /cards/{id}/prices` | Optional `printing` filter. |
| `GET /prices/top-movers` | `game`, `direction`, `period`, `printing`, `type`, `limit`. |
| `GET /bulk/prices` | Comma-separated `ids`; batch size must respect the provider's current contract. |

- Pricing fields used include `printing`, `market_price`, `low_price`, `median_price`, `lowest_with_shipping`, `buylist_price`, `price_change_24h`, `price_change_7d`, `price_change_30d`, `total_listings`, and provider update timestamps.
- Printing values include Normal, Holofoil, Reverse Holofoil, 1st Edition, and Unlimited where provided. Missing fields/variants vary by card; do not assume every response contains them.
- The eBay OAuth endpoint is `https://api.ebay.com/identity/v1/oauth2/token`; Browse search is `/buy/browse/v1/item_summary/search`. The application-token Redis key is `cardboarddex:ebay:oauth_access_token`.
- Raw listings are stored in `raw_ebay_listings` (migration `0003_ebay_raw_listings.py`), including item ID, title, price/currency, listing URL, seller feedback, dates, match/rejection details, and raw payload. Matched observations retain source item identity and title-match metadata.
- The parser rejects proxies/fakes/custom cards, lots/bulk, digital codes, foreign-language mismatches, alterations/autographs, speculative grades such as “PSA 10?”, and empty/opened sealed products.
- Japanese targets receive `is_target_japanese`; `RE_NON_JAPANESE_FOREIGN` rejects other languages while permitting Japanese terms. `extract_core_card_name()` normalizes suffixes such as `Ivysaur - 002/165` and printing parentheticals such as Master Ball Pattern/Mirror Holofoil.
- Grading extraction supports PSA, BGS, CGC, and SGC. These are parsed seller claims, not independent grading-certificate verification.
- Sealed matching distinguishes booster boxes, ETBs, bundles, cases, tins, blisters, binder collections, and UPCs; isolates cases from single units and Pokémon Center variants; rejects single-promo extractions.
- Sealed observations use `variant_id=ebay:{card_id}:sealed` with sealed condition/printing. Raw/graded variants include company and grade/condition information.
- Direct eBay shopping queries combine “Pokemon”, card name/number, and set name; sealed queries omit dummy numbers. Listing URLs are surfaced through the detail dashboard's variants table.

### Scheduling and limits

[Celery Beat](backend/app/celery_app.py) schedules TCG price batches at minutes `:00/:30`, eBay batches at `:15/:45`, and both-game catalog sync at 03:00 UTC. These are batch schedules, not a promise that every card refreshes every 15 minutes.

Provider limits use Redis daily counters and per-second burst pacing; defaults are 2,000 TCG and 500 eBay requests/day. Celery uses JSON serialization, late acknowledgements, prefetch one, task expiration, and hard time limits. These settings do not provide a distributed singleton lock. Run only one Beat scheduler and verify overlap behavior during rolling deployments.

## Deployment status

Recovery follow-up: **2026-09-24 UTC**. Earlier recoveries relapsed under dashboard/image load. The capacity-fix release below adds database and request-concurrency controls; do not treat the earlier smoke checks as proof of sustained stability.

- Current host: `cardboarddex-ipv6`, 512 MB Lightsail instance in `us-west-2a`. Recovery enabled dual-stack networking on the same disk, changing the bundle from `$3.50/month nano_ipv6_3_0` to `$5/month nano_3_0`, within the existing server budget. Its public IPv4 address is dynamic; query AWS before connecting. The old `32.187.254.253` address is obsolete.
- GitHub uses `LIGHTSAIL_HOST=cardboarddex-ipv6` and `LIGHTSAIL_SSM_TARGET=mi-04eda276674cf91be`. The older `mi-07cf7e6e80daf232f` registration is stale. Recovery SSH uses short-lived Lightsail access certificates and host keys independently verified through AWS. No new persistent SSH authorized key was installed.
- The original backend workflow passed tests and image build, then failed with `TargetNotConnected`; all 30 SSM checks reported `ConnectionLost`. After publication of `b4111b2`, run `35939942195` reached SSH but failed strict host verification because GitHub still stored the pre-migration host keys. GitHub `LIGHTSAIL_KNOWN_HOSTS` now contains the AWS-verified current keys, and `LIGHTSAIL_SSH_KEY` now contains the existing Lightsail default key after successful authentication. No server-authorized key was added. The backup workflow failed because its latest completed archive was over 64 hours old. The host showed sustained swap/disk stalls, exhausted CPU burst capacity, and an API process with roughly 424 MB swapped out.
- The previously active release was `31b2efd92e46f38a9a6be7740fbae3aed7a19542`, image digest `sha256:1a844284d1e1fd42d8bbece2ff5aeea9f11fe3e60402ff473e4c70a8ae24467a`. This remains the previous release for reference; deploying it would restore the unbounded query behavior. The capacity recovery image is now active; ingestion is paused after full-service recovery repeatedly stalled the host.

### Recovery changes and artifact

- Latest verification after the paused recovery: 13 public checks passed, two direct-AWS checks skipped, but a subsequent concurrent image burst timed out while a backup was running. Local readiness still returned 200. At approximately 06:38 UTC, `vmstat` measured 91–92% CPU steal and heavy swapping; Lightsail reported burst capacity falling to 0% at 06:33 UTC. The outage is not fully resolved even with ingestion paused. Avoid repeated load tests/restarts that consume the remaining capacity; a sustainable capacity/workload decision remains outstanding. S3 independently confirmed a completed backup at schema `0005_price_obs_analytics_cover`; the additional backup requested at 06:34 UTC was still running at last inspection.

- Latest capacity image: `cardboarddex-backend:recovery-20260924-capacity`, digest `sha256:62a75b7c74ed9f4c2f1b7bccc3ec8f252fe467e9d6bf2bc4b5e5c2b216b984d3`, release `/opt/cardboarddex/releases/recovery-20260924-capacity`. It adds a configurable API thread limit (four in production), releases image-request database sessions before external I/O, and serializes S3 client initialization. All 174 backend tests pass in the AMD64 image; 15 opt-in live tests are skipped there.
- PostgreSQL runs with JIT off, parallel query workers disabled, and a 12-second statement timeout. Migration `0005_price_obs_analytics_cover` adds only a covering index on `price_observations`; `cards` and `sets` are unchanged. It was tested through upgrade/downgrade/re-upgrade on disposable PostgreSQL 16, then applied online in production and validated. The migration session has a five-minute index-build timeout. A representative aggregate uses an index-only scan, zero heap fetches, and completes in 200 ms. Normal deployment still checks revisions and never runs migrations automatically.
- With ingestion paused for verification, all 13 public endpoint tests passed (two direct-AWS tests skipped). A simultaneous page-load check returned all 24 images within 1.87 seconds, Live Comps in 1.60 seconds, Trending in 0.58 seconds, and readiness in 0.33 seconds. API OOM/restart counts remained zero. Restoring worker and Beat subsequently reproduced HTTP 502 and a whole-host stall before a second load test could begin. Full-service stability is not established. After another preserved-disk restart, the capacity release completed deployment with ingestion paused. `/opt/cardboarddex/ingestion.paused` prevents the release script and its rollback from starting ingestion; existing worker/Beat containers also have restart policy `no` so reboot preserves the pause. Eight deployment tests cover normal and paused success/failure paths. New catalog/pricing ingestion is unavailable during this pause.

- A later catalog failure was a separate 15-second client timeout. Production EXPLAIN measured the broad price sort at 25.7 seconds: 28,551 correlated price lookups and sorts. A single ranked latest-price relation measured 3.1 seconds on the same database. Broad price sorts/range filters now use that relation; selective name/set searches retain indexed per-card lookups. Timestamp ties use observation ID consistently. No schema changes were required. The new `search:v2` cache namespace ensures old cached responses do not mask verification.

- Dashboard queries now aggregate price histories in PostgreSQL; grading materializes at most four observations per card without JSON payloads, and sealed products use the latest observation by timestamp/ID. These initial query changes did not alter database schema; the later price-observation index migration is described above.
- Compose uses 16 MB PostgreSQL shared buffers, one-minute steady-state health checks with five-second startup probes, and a lightweight curl readiness probe. The 512 MB host has a 512 MB LZ4 zram swap device at priority 100; the existing 2 GB disk swap remains fallback. `cardboarddex-zram.service` enables this before Docker at boot. Bootstrap and release scripts install it only on small hosts.
- Dynamic login-status scripts were disabled to avoid expensive status-generation processes. Unused Snap services and the desktop disk-management service were disabled during recovery; no firmware/disk service masking was applied. Snap is not the active SSM installation.
- CI now fails before SSH if SSM never becomes Online and preserves AWS errors. Release verification requires successful privileged backup-timer activation instead of silently swallowing failure.
- Published and tested AMD64 recovery image: `cardboarddex-backend:recovery-20260923-memory`, digest `sha256:b9713a8ab6bda24de4971ad73669094aaa6f293f9945db8b94add7c15c9fc740`. This image was superseded by the search fix below; the limits-only release is retained for rollback.
- Search-fix image: `cardboarddex-backend:recovery-20260924-search`, digest `sha256:cbcef6c0b4b8a8660d7aa8f473afa4d5f39848b527c9f0b1c8af2fbf6e89cc60`, historically deployed at `/opt/cardboarddex/releases/recovery-20260924-search`, now retained as `/opt/cardboarddex/previous`; `/opt/cardboarddex/current` points to the capacity release. The updated release script completed all verification steps successfully. It passes 171 backend tests inside the AMD64 image (nine opt-in live checks skipped). Initial uncached public searches took 3.47 seconds for the exact 24-card request, 2.93 seconds for 23 cards, and 3.15 seconds for ascending prices. With ingestion restored, a fresh uncached 24-card search took 2.99 seconds. All seven public smoke tests pass, including the 15-second frontend deadline (two direct-AWS tests remain intentionally skipped).
- Deployment initially stalled checking multiple images while ingestion was resident. The host was restarted with application processes stopped, and only the backend image was pulled before API startup. The release script now drains ingestion before image pulls/schema checks, serializes pulls, and restores the previous release if a pull fails; regression tests cover that failure.
- The original fixes were published as `b4111b2`. Follow-up runtime limits, query/concurrency fixes, the price-observation index migration, deployment sequencing, and regression tests remain local pending commit/push approval; publish them before rerunning deployment, or main will remove the new limits.

### Backups and verification

- Existing backup bucket: `cardboarddex-backups-349558247779-us-west-2`, with private access, TLS, SSE-S3, six-hourly retention of seven days and weekly retention of 28 days. Production credentials remain in protected host files and ignored local operational files; never print or commit them.
- The backup timer was active, but repeated runs timed out after 30 minutes during the outage. The recovery backup `six-hourly/20260924T000429Z` completed at 00:05:30 UTC in about one minute; its manifest freshness and revision `0004_price_obs_search_index` were independently verified from S3. GitHub backup verification, including the full disposable restore, [passed](https://github.com/n8liu/cardboarddex/actions/runs/35936844062). With the follow-up limits active, backup `six-hourly/20260924T045921Z` completed successfully at 04:59:49 UTC.
- Historical checks for the first recovery image passed (168 backend tests, seven live tests skipped); these results predate the later relapses and do not establish current stability. Regression tests cover bounded history materialization, latest-price selection, SSM failure handling, backup-timer deployment failures, and safe zram initialization. All 36 deployment tests pass, including disposable container restore tests. Compose validation and shell syntax checks pass. Seven public smoke tests pass with bounded ingestion running, including the exact initial `/cards/sets` and price-descending `/cards/search` requests with production-origin GET CORS headers; two direct-AWS checks are intentionally skipped because the API binds to loopback behind Cloudflare. The four affected dashboard endpoints return 200, and SSM reports Online. A completed eBay task wrote 146 observations with zero provider errors. TCG bulk pricing returned a tier restriction and the existing individual-request fallback succeeded.
- The screenshot outage was HTTP 530 / Cloudflare tunnel error 1033; missing CORS headers came from the edge error response. SSH and SSM were also unreachable. Tunnel logs showed timeouts around 03:53 UTC; available system logs did not establish the precise initiating process. A preserved-disk restart restored access.
- API RAM/total RAM+swap limits are 160/224 MiB; worker 96/160 MiB; Beat 48/80 MiB. Python processes use `MALLOC_ARENA_MAX=2`, and worker children recycle after ten tasks. These bound application memory growth; they do not prove the host has sufficient sustained capacity. Initial checks with all services running showed no OOM events, roughly 342 MiB compressed into 114 MiB, and idle disk I/O. The 05:00 UTC scheduled pricing task completed five cards with zero provider errors, while API readiness remained successful; API, worker, and Beat had zero restarts. Those initial successes were followed by another outage. Keep ingestion paused until capacity is resolved and verify a complete workload cycle before declaring sustained stability.
- See [the Lightsail runbook](docs/lightsail-migration.md) for migration history and recovery restrictions. Do not delete or replace the only instance to bypass AWS account limits without explicit authorization.

## R2 image delivery implementation (pending activation)

- R2/CDN implementation uses a local verified manifest, direct public image URLs, and a bounded GitHub runner synchronization job. Cards/Sets schemas are unchanged.
- Live Cloudflare setup, credentials, initial backfill, cutover, and the 24-hour observation remain pending; no CPU savings are claimed yet. CDN mode and scheduled synchronization default to disabled.
- See [R2 image setup and cutover](docs/r2-images.md) for exact configuration, validation, costs, and rollback. Production ingestion must stay paused during rollout.
- Local verification: 190 backend tests passed (15 live checks skipped), 40 deployment/tooling tests passed (two container checks skipped), 22 frontend tests passed, TypeScript and production build passed. Cloudflare provisioning has only been previewed; no live R2 credentials or activation were available in this session.

## Configuration

Backend settings are loaded from environment variables and the repository-root `.env` by [Settings](backend/app/config.py). The following are **code defaults**, not verified production values.

| Variable | Purpose / default |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy connection URL; defaults to `sqlite:///./cardboarddex.db`. Configure PostgreSQL for development/production as appropriate. |
| `REDIS_URL` | Durable broker/results, quotas, OAuth tokens and checkpoints; `redis://localhost:6379/0`. |
| `CACHE_REDIS_URL` | Disposable response caches and analytics; falls back to `REDIS_URL` locally. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | API defaults 3/2; production worker overrides 2/0. |
| `POSTGRES_HOST` / `POSTGRES_PASSWORD` | Production connection configuration; safely constructs a URL instead of interpolating passwords. |
| `TCGAPI_API_KEY` | Server-side TCG API credential; unset by default. |
| `TCGAPI_BASE_URL` | `https://api.tcgapi.dev/v1`. |
| `TCGAPI_DAILY_REQUEST_LIMIT` | `2000`. |
| `TCGAPI_SYNC_SET_LIMIT` | `250` newest sets per game by default. |
| `PRICE_COLLECTION_CARD_LIMIT` | `5` cards per scheduled collection batch by default. |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | Server-side OAuth credentials; unset by default. |
| `EBAY_MARKETPLACE_ID` | `EBAY_US`. |
| `EBAY_DAILY_REQUEST_LIMIT` | `500`. |
| `S3_BUCKET_NAME` | Optional bucket for image caching/sync. |
| `AWS_REGION` | Image-storage client region; `us-west-2`. |
| `CLOUDFRONT_DOMAIN` | Optional asset hostname without a scheme. |
| `BACKEND_CORS_ORIGINS` | Comma-separated origins; defaults to localhost/127.0.0.1 on ports 3000/3001. `main.py` additionally allows matching production/preview origins. |
| `NEXT_PUBLIC_API_URL` | Browser-visible API base URL; resolved by [next.config.ts](frontend/next.config.ts) and [api.ts](frontend/lib/api.ts). Never put credentials here. |
| `PSA_VALUE_FEE` | Grading-fee assumption; `24.99`. |
| `ADMIN_API_KEY` | Token for privileged routes through `X-Admin-Token`; admin actions disabled when unset. |
| `ENABLE_API_DOCS` | `false`; controls Swagger, ReDoc, and OpenAPI routes. |
| `RATE_LIMIT_PER_MINUTE` | `300`; image paths use a separate hardcoded `6000`/minute bucket. |
| `RATE_LIMIT_TRACK_ACTION_PER_MINUTE` | `30`. |
| `RATE_LIMIT_HEAVY_PER_MINUTE` | `60`, but currently not wired to endpoints. |

Earlier references to `S3_CARD_ASSETS_BUCKET` and `S3_CUSTOM_DOMAIN` do not match these settings. `AWS_DEFAULT_REGION` is not the application's `aws_region` setting.

Never commit `.env`, provider credentials, database passwords, or Tunnel tokens.

## Development and verification commands

From the repository root, `docker compose up -d` starts PostgreSQL and Redis. Review the exposed-port issue below before using it on a remotely reachable host.

From `backend/`, with the virtual environment and intended environment configured:

```bash
.venv/bin/uvicorn app.main:app --reload
.venv/bin/alembic upgrade head

# Isolated test configuration: avoid the configured database/Redis.
DATABASE_URL=sqlite:// REDIS_URL=redis://127.0.0.1:1/0 TCGAPI_API_KEY= EBAY_CLIENT_ID= EBAY_CLIENT_SECRET= .venv/bin/pytest
PYTHONPATH=. .venv/bin/python -m compileall -q app jobs tests parsers
```

Jobs below write to the configured database/S3 and consume provider quota. Use an activated backend virtual environment; check `--help` for other supported options.

```bash
python -m jobs.sync_catalog --game all --limit 50
python -m jobs.sync_catalog --game pokemon --limit 50
python -m jobs.sync_catalog --game pokemon-japan --limit 50
python -m jobs.cycle_prices --card-id 28402
python -m jobs.cycle_prices --pokemon "Pikachu"
python -m jobs.update_card --card-id 28402
python -m jobs.update_card "Rayquaza Legends Awakened"
python -m jobs.update_card --pokemon "Rayquaza" --limit 20
python -m jobs.update_pokemon "Charizard" --limit 20
python -m jobs.collect_prices --limit 50
python -m jobs.collect_prices --card-id 29919
python -m jobs.collect_prices "Rocket's Moltres"
python -m jobs.collect_ebay_prices --limit 20
python -m jobs.collect_ebay_prices "Charizard Base Set"
python -m jobs.collect_ebay_prices "151 Binder Collection"
python -m jobs.sync_images_to_s3 --limit 100 --workers 5
python -m jobs.sync_images_to_s3 --all --workers 10
celery -A app.celery_app worker --beat --loglevel=info
```

Catalog options also include `--resume` and `--reset-cursor`; use them only with the checkpoint limitations above understood. The image-sync CLI supports `--set-id` for targeting a set.

For manual continuous cycling, use `python -m jobs.cycle_prices --continuous --interval 900 --tcg-limit 50 --ebay-limit 20` as an alternative scheduler, not alongside Beat against the same workload.

From `frontend/`:

```bash
npm ci
npm run dev
npm test
npm run typecheck
npm run build
```

From `backend/`, the explicit live verification command is:

```bash
RUN_LIVE_DEPLOYMENT_TESTS=1 .venv/bin/pytest -m live tests/test_deployment_endpoints.py -v
```

Set `AWS_BACKEND_URL` to the legacy endpoint from the recorded infrastructure table only while testing migration parity. Omit it after retirement.

Opt-in deployment tests and direct-AWS parity checks: [docs/ecs-tunnel-migration.md](docs/ecs-tunnel-migration.md). `RUN_LIVE_DEPLOYMENT_TESTS=1` enables public endpoint calls; `AWS_BACKEND_URL` additionally enables the two direct-AWS checks.

Latest audit verification (2026-09-15):

- Backend: 151 passed, five live-test skips, using isolated database/Redis configuration.
- Frontend: 20 tests passed across five test files.
- `npm audit --omit=dev`: no known production-dependency vulnerabilities reported at that time.
- Mocked checks reproduced image redirect bypass, proxy-header trust, retained expired cache entries, and portfolio look-ahead bias.
- Public homepage headers lacked CSP and framing protection. Live IAM/RDS/S3 permissions, Python advisories, and comprehensive historical secret scanning were not audited.
- Build/typecheck success was recorded by the preceding migration work; those checks were not rerun for the security audit or this documentation-only cleanup.

## Open work, in priority order

### 1. Security and availability

- **Image fetching:** validate redirects/destinations and enforce image type/size limits in `TCGAPIClient.get_image()`. The existing hostname allowlist only checks the initial URL.
- **Caches and request cost:** bound and evict expired portfolio/grading/sealed/volume caches, avoid retaining invalid requests, enforce heavy-endpoint limits, and bound expensive history queries.
- **Proxy trust:** accept client-IP headers only from trusted proxies; confirm direct-origin closure after cutover.
- **Redis:** avoid synchronous network calls on the async middleware path; configure explicit connection/read timeouts.
- **Development services:** bind Compose PostgreSQL/Redis to loopback; configure authentication/network isolation where remote access is required.
- **Frontend headers:** deploy an application-compatible CSP and framing restrictions on HTML responses. API headers do not protect the separate frontend document.
- **Cloud secrets/IAM (verify live):** the runbook reports secrets in ECS environment entries; move to secret references. Restrict the guide's wildcard OIDC subject and AWS resource permissions; grant OIDC permission only to deployment jobs.

### 2. Pricing correctness and privacy

- Remove current-price backfilling of missing historical portfolio prices; expose historical coverage. Preserve duplicate holding quantities and consistent printing identity.
- Fix fallback valuation's oldest-observation selection and unbounded per-card request fan-out. Reconcile percentage-change versus currency-amount semantics across calculations.
- Replace sold-sales wording for active listings/catalog observations. Observation frequency is affected by ingestion and does not measure transaction volume.
- Replace arbitrary mover fallbacks with insufficient-data states. Expose grading probabilities, missing costs, and sealed-score assumptions; use explicit ordering for latest sealed observations.
- Make browser caching honor `no-store`, bound cache size, and date or refresh FX rates.
- Document binder uploads and third-party media/font requests. Redact sensitive provider error payloads and keep operational diagnostics protected.

### 3. Operations and follow-up features

- ECS/ALB/RDS retirement is complete. Production remains on the $5/month Lightsail server base with all residual snapshots deleted; reliability rollout and verified scheduled backups remain active as recorded above.
- Standardize locked Python dependencies and vulnerability checks; add `npm test` to frontend CI and regression coverage for the findings above.
- Fix quota diagnostics to read the same Redis keys as the limiter. Separate liveness from readiness and protected diagnostics.
- Repair catalog `--all` and checkpoint semantics before relying on resumable ingestion. Verify one Beat scheduler during deployments.
- Add freshness, provider-quota, failed-image, job-duration, and match/reject monitoring.
- Verify available eBay programs/scopes before implementing completed-sales ingestion. Add sold-sales statistics and accounts/watchlists after pricing identity and data quality are reliable.
