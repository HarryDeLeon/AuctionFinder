# AuctionFinder
Application to find and compare auction items.

#Requires:
streamlit
pandas

## Deploy (Streamlit Community Cloud)
This app is ready to deploy on Streamlit Community Cloud.

### 1) Push this repository to GitHub
Make sure these files exist in the repo root:
- `app.py`
- `requirements.txt`
- `runtime.txt`

### 2) Create the app in Streamlit Community Cloud
1. Go to https://share.streamlit.io/
2. Sign in and click **New app**
3. Select your GitHub repo and branch
4. Set **Main file path** to `app.py`
5. Click **Deploy**

### 3) Private repo notes
- Private repos are supported.
- You must connect the GitHub account/org that can access the repository.
- To let others use the app, share access from Streamlit app settings after deployment.

### 4) Important persistence note
This project uses local SQLite (`auctionfinder.db`) for watchlist and saved searches.
For public/shared production usage, move persistence to a managed database (for example PostgreSQL) because local file storage on hosted apps is not ideal for multi-user durability.

## SQLite note
No extra installation is required to use SQLite in this project.  
The app uses Python's built-in `sqlite3` module and creates a local database file (`auctionfinder.db`) in the project folder.

## Current prototype features
- Search listings by keyword (item title and description).
- Filter by category and auction status.
- Filter by minimum and maximum listed/hammer price.
- Sort results by estimated total cost, listed price, or relevance.
- Estimated cost breakdown includes buyer premium, shipping, and optional fixed fees.
- Tax handling is supported in pricing logic when a tax rate is available; UI estimates currently exclude taxes.
- Active listings are explicitly labeled as estimates based on the current bid.
- Comparable-sale summary includes comparable count, median comparable total, confidence, and a transparent opportunity label.
- Listing detail expanders explain pricing components and why a listing received its opportunity signal.
- Watchlist entries persist in local SQLite storage.
- Saved searches persist in local SQLite storage and can be loaded back into filters.
- Watchlist and saved searches can be exported to CSV and imported back with validation.
- Duplicate detection flags potential duplicate records for manual review (no auto-merge).
- Modular auction source scaffolding is available in `auction_sources/` with a manual CSV source adapter and normalization pipeline.
- The app includes a prototype "Manual source import preview" toggle (sidebar) to validate and temporarily preview normalized source rows in-session.
- The manual import preview includes in-app CSV requirements help and a downloadable template.
- Manual preview imports now return a valid/rejected row summary and provide a downloadable rejected-rows CSV for correction workflows.
- A prototype auction source registry allows users to add/edit/delete source configurations in the sidebar.
- A Sprint 1 ingestion skeleton is included with crawl-run tracking and a `dummy` adapter to validate persistence and pipeline flow.
- Sprint 2 adds a first HTML adapter for LiveAuctionWorld (`source_type=html`) with URL/domain guardrails and parser fallbacks (JSON-LD first, then listing-link extraction).
- Sprint 3 hardening adds retry/backoff fetching for LiveAuctionWorld HTML, parser fixture coverage under `tests/fixtures/`, and richer source telemetry in the sidebar (last crawl status/finished time/error).
- Sprint 4 adds LiveAuctionWorld structure-aware extraction for auction cards and lot grid entries (including lot number, auctioneer, description, bid text parsing), plus controlled pagination via per-source `crawl_max_pages`.
- The main page now supports on-demand keyword web crawl ("Search web source now"), which runs a live crawl for the typed keyword across enabled HTML sources and stores matching results locally.
- The main page now supports scanning a specific auction webpage URL ("Scan auction URL now") through enabled HTML sources and ingesting lots from that page.
- A prototype internet price comparison report can analyze the top-ranked filtered listings (default top 10) and summarize internet comparable prices (lowest/highest/average CAD) with comparable links for review.
- Internet price comparison runs are persisted in SQLite and can be reloaded in-app from recent run history.
- Stored internet comparison runs can be deleted from the UI, and report detail expanders show the captured comparable links for each analyzed item.

All listings are currently fictional sample data.

## Manual CSV source scaffold (Phase 3 foundation)
The new manual source adapter expects CSV columns:

- `source_record_id`
- `item_title`
- `category`
- `auction_house`
- `status`
- `price_cad`
- `buyer_premium_percent`
- `shipping_cad`

Optional columns include `description`, `location`, `listing_url`, `lot_number`, `sale_date_iso`, `other_fees_cad`, and `tax_percent`.

The in-app preview is intentionally **flagged as prototype** and does not auto-merge imported rows into persisted watchlist/search tables.
