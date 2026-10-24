# AuctionFinder
Application to find and compare auction items.

#Requires:
streamlit
pandas

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
