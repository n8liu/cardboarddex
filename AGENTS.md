# Project Overview
We are building a Trading Card Price Tracker (similar to PriceCharting).
The backend handles automated ingestion of catalog and market pricing data (Pokémon Price Tracker / PPT), plus direct eBay asking-listing comparisons.

# AI Agent Rules
1. NEVER use generic try/except blocks without logging the exact error. We are dealing with messy third-party APIs.
2. The database schema is sacred. Do not modify the `Cards` or `Sets` table without my explicit permission.
3. All eBay title parsing logic MUST reside in `backend/parsers/title_matcher.py` and must include comprehensive Unit Tests testing edge-case titles (e.g., "Charizard PSA 10 proxy").
4. Think step-by-step. Whenever asked to build a new feature, output a markdown plan of the files you intend to change before writing any code.
