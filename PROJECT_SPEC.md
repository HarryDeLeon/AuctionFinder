# Project Specification: Antique Auction Price Finder

## 1. Project Overview

Build a web application called **Antique Auction Price Finder** that helps users research antiques, compare auction prices across auction houses, identify potential bargains, and understand the actual cost of purchasing an item.

The initial geographic focus is British Columbia and the Lower Mainland, Canada, with the architecture designed to support additional Canadian and international auction houses later.

The application should help answer five questions:

1. What is this antique potentially worth?
2. What have comparable items sold for at other auctions?
3. Where can I find the best current opportunity?
4. What will the item actually cost after buyer premiums, shipping, and applicable taxes?
5. How reliable is the comparison?

This is a learning project and an evolving prototype. Prioritize correctness, maintainability, transparent calculations, and incremental development over adding many features quickly.

## 2. Current Technology and Development Environment

- Language: Python.
- IDE: Visual Studio Code.
- Web interface: Streamlit for the initial version.
- Data processing: pandas where useful.
- Automated testing: Python unittest.
- Version control: Git and GitHub.
- Initial data storage: local data files or SQLite if persistence becomes necessary.
- Future architecture: consider FastAPI and PostgreSQL if the application outgrows Streamlit.

The current project directory is:

`D:\Source\AuctionFinderHD`

The current project includes:

- `app.py`
- `models.py`
- `pricing.py`
- `sample_data.py`
- `requirements.txt`
- `.gitignore`
- `tests/test_pricing.py`

The application currently uses fictional sample auction listings. The existing pricing tests pass.

**Preserve the existing working application and its tests.** Inspect the current files before modifying anything. Do not replace working code with a completely new implementation unless there is a clear technical reason.

## 3. Main Functional Requirements

### Feature A — Search and Browse Auctions

Allow users to search for antiques across available auction listings.

Support:

- Keyword search by item name and description.
- Filtering by category, auction house, location, and auction status.
- Filtering by minimum and maximum price.
- Filtering by sale date or auction closing date when available.
- Sorting by price, estimated total cost, sale date, and relevance.
- Pagination or another sensible approach if the dataset becomes large.

Initial categories should include:

- Furniture
- Ceramics and porcelain
- Silver and metalware
- Paintings and fine art
- Jewellery and watches
- Coins and collectibles
- Books and manuscripts
- Glassware
- Clocks
- Decorative antiques
- Other

Allow categories to evolve without requiring major code changes.

### Feature B — Auction Listing Details

Each listing should have a detail view containing as much of the following information as is available:

- Item title and description.
- Auction house and original listing URL.
- Photographs, where permitted.
- Category and estimated period or date.
- Maker, artist, brand, or origin, when known.
- Materials, dimensions, condition, and provenance, when provided.
- Current bid or asking price.
- Final hammer price for completed auctions.
- Buyer premium and its calculation basis.
- Shipping and handling cost.
- Applicable taxes and other known charges.
- Auction closing date or sale date.
- Listing status: upcoming, active, sold, withdrawn, or unknown.
- Date the listing was last checked.
- Source of the information.

Clearly distinguish confirmed information from estimates, missing information, and AI-generated interpretations.

### Feature C — Compare Auction Prices

Allow users to compare multiple listings of the same or similar items.

Display:

- Auction house.
- Item description.
- Sale status.
- Hammer price or current bid.
- Buyer premium.
- Shipping.
- Estimated total cost.
- Sale date.
- Source link.
- Comparability or confidence rating.

Support side-by-side comparisons and sorting from lowest to highest estimated total cost.

Do not treat items as directly comparable merely because they share a broad category. Differences in maker, age, condition, rarity, size, provenance, and authenticity may significantly affect value.

### Feature D — Historical Sold Prices

Create a searchable record of completed auction sales.

Users should be able to:

- Search previously sold items.
- Filter by category, date, auction house, and price range.
- View sale-price ranges and averages for comparable items.
- View the number of sales supporting a comparison.
- See individual sale records and their original sources.

Distinguish hammer price from buyer's total purchase cost.

Use only reliable completed-sale data. Do not mix active bids, asking prices, estimates, unsold lots, and confirmed final sale prices into the same statistic without clearly identifying the differences.

If the sample size is small, tell the user rather than presenting the result as a reliable market valuation.

### Feature E — Potential Bargains

Develop a feature that identifies listings that may be attractively priced compared with relevant historical sales.

For each candidate, calculate:

- Estimated buyer cost.
- Comparable historical sale-price range.
- Median and average comparable price, when appropriate.
- Difference from the chosen benchmark.
- Percentage below or above the benchmark.
- Number of comparable sales.
- Confidence level and explanation.

Example:

A comparable item has a historical median hammer price of $400 CAD. A current listing has a $250 CAD bid.

The application should not automatically call it a bargain. It must account for buyer premiums, shipping, taxes where known, item condition, and comparability before presenting a conclusion.

Use transparent rules for the initial implementation. AI may help explain or rank comparisons, but it must not invent historical prices or present uncertain estimates as facts.

Use labels such as:

- Potential opportunity
- Worth investigating
- Limited comparable evidence
- Not enough information

Clearly explain why a listing was flagged.

### Feature F — True Cost Calculator

Provide a reusable pricing calculator.

Calculate:

Hammer price or current bid  
+ Buyer premium  
+ Shipping and handling  
+ Other known fees  
+ Applicable taxes  
= Estimated total cost

Requirements:

- Support different buyer-premium percentages.
- Support fixed fees where applicable.
- Avoid double-counting taxes or fees.
- Distinguish confirmed charges from estimates.
- Support CAD initially.
- Design for additional currencies later.
- Show which charges are excluded when information is unavailable.

Taxes must be calculated according to the applicable transaction and jurisdiction when sufficient information is available. Do not assume that all auction purchases have the same tax treatment.

For active auctions, label the result as an estimate based on the current bid. It is not a prediction of the final winning price.

### Feature G — Watchlist and Saved Searches

Allow users to save interesting listings.

The watchlist should display:

- Item title.
- Auction house.
- Current price.
- Estimated total cost.
- Closing date.
- Listing status.
- Last checked date.
- Link to the original listing.

Allow users to save search criteria, such as:

"Antique porcelain vases under $500 CAD."

Design the feature so that price-change notifications and auction-ending reminders can be added later.

For the initial version, local persistence is acceptable. Explain any limitations if the data is stored only on the current computer.

### Feature H — Auction House Directory

Maintain a directory of auction houses.

For each auction house, store:

- Name.
- Website.
- Location.
- Supported categories, when known.
- Currency.
- Buyer-premium information and source.
- Shipping information and source.
- Data collection method.
- Last verification date.
- Integration status.

Start with a small, verified set of relevant Lower Mainland auction houses.

Do not assume that every auction house publishes its results in the same format or permits automated collection.

### Feature I — Data Collection and Source Management

Design a modular data-ingestion system that can eventually collect information from multiple auction houses.

Each auction-house integration should be independent of the user interface and should convert its source data into a common internal format.

Possible data sources, in order of preference:

1. Official APIs or feeds.
2. Licensed third-party data providers.
3. Auction-house exports or other explicitly authorized data.
4. Public pages only where automated access and intended use are permitted.

Respect terms of service, copyright, robots directives, rate limits, authentication requirements, and applicable privacy rules. Do not bypass access controls or anti-bot protections.

Do not assume that publicly viewable information can automatically be scraped, stored, or republished.

If an integration is not permitted or reliable, provide a manual import option instead.

Each record should retain source attribution and a timestamp.

Build error handling for unavailable websites, malformed data, duplicate records, and changed page structures.

### Feature J — Duplicate Detection and Item Matching

The same item or similar items may appear in different formats or across different sources.

Implement a cautious matching system using available attributes, including:

- Title and description.
- Maker or artist.
- Category.
- Materials.
- Dimensions.
- Photographs, if permitted.
- Sale date.
- Auction house and lot number.

Initially, use transparent matching rules and allow the user to review uncertain matches.

Do not merge records automatically when the evidence is weak. Distinguish the same physical item appearing more than once from different items that are merely similar.

AI-assisted matching can be introduced later, with explanations and a way to correct mistakes.

### Feature K — AI Research Assistant

In a later phase, add an AI assistant that can help users research an item.

Potential capabilities:

- Summarize a listing.
- Extract attributes from descriptions.
- Suggest search terms and relevant categories.
- Identify potentially relevant comparable sales.
- Explain why two items may or may not be comparable.
- Summarize maker, period, or historical context using verifiable sources.
- Highlight missing information that could affect value.

The AI must not fabricate citations, sale results, provenance, authenticity, or valuations.

Every factual claim about a listing or historical sale should link back to its source when possible.

Clearly distinguish sourced facts, user-provided information, model-generated suggestions, and uncertain conclusions.

AI should assist research, not replace evidence or make unsupported claims of authenticity.

### Feature L — Dashboard and Reporting

Provide a clear dashboard with:

- Recently added listings.
- Upcoming auction closings.
- Saved items.
- Potential opportunities.
- Recently sold comparable items.
- Search and filter controls.

Allow users to export selected records to CSV.

Design the interface for desktop first, while keeping it usable on smaller screens.

## 4. Data Model

Use a common internal data model rather than writing auction-specific logic throughout the application.

The existing `AuctionListing` model may be extended as needed. Consider separating these entities as the application grows:

- `AuctionHouse`
- `AuctionListing`
- `SaleRecord`
- `Item`
- `ComparableMatch`
- `PriceEstimate`
- `WatchlistEntry`
- `SavedSearch`
- `SourceRecord`

Keep the distinction between an item, a listing, and a completed sale.

An item is the object being researched. A listing is a particular auction-house offering. A sale record represents the outcome of a completed auction.

Store prices with explicit currencies. Use appropriate decimal arithmetic for financial calculations when precision is important.

Add stable identifiers and timestamps. Avoid unnecessary complexity until the requirements justify it.

## 5. Architecture and Code Quality

Use a modular structure with clear responsibilities.

Suggested direction:

- `app.py`: Streamlit interface and application flow.
- `models.py`: data structures and domain models.
- `pricing.py`: purchase-cost calculations.
- `comparables.py`: matching and price-comparison logic.
- `search.py`: filtering and search logic.
- `repositories.py`: loading and saving data.
- `auction_sources/`: independent integrations for permitted sources.
- `tests/`: automated tests.
- `requirements.txt`: application dependencies.

This is a proposed structure, not a requirement to create every file immediately. Introduce modules when there is real functionality to put in them.

Keep business rules out of the UI where practical.

Use type hints, meaningful names, short functions, and useful error messages.

Avoid unnecessary frameworks, dependencies, abstractions, and premature microservices.

## 6. Testing and Reliability

Automated tests are required for important business logic.

Add tests covering:

- Buyer-premium calculations.
- Shipping and other fees.
- Tax handling and excluded taxes.
- Zero or missing charges.
- Invalid or negative inputs.
- Currency handling as it is introduced.
- Search and filtering.
- Comparable matching.
- Bargain calculations.
- Missing or incomplete source data.
- Duplicate detection.
- Persistence and data-import errors.

Use fictional test fixtures where appropriate. Never present test fixtures as real auction results.

Run the existing tests after every relevant change. Add new tests before or alongside implementing new business rules.

Do not claim tests passed unless they were actually executed and passed.

## 7. Security and Data Integrity

- Never commit API keys, passwords, tokens, or other secrets to GitHub.
- Use environment variables or appropriate local secret storage.
- Validate imported data.
- Handle untrusted source text safely.
- Avoid executing code contained in imported data.
- Preserve source URLs and collection timestamps.
- Make it possible to identify stale, missing, or contradictory data.
- Do not overwrite a verified sale price with an unverified estimate.
- Keep a clear audit trail for important corrections where practical.

## 8. Development Workflow for AI-Assisted Coding

Work incrementally. Do not attempt to implement the entire specification in one large code-generation step.

For each feature:

1. Inspect the existing project and understand the current implementation.
2. State the proposed changes and explain the reasoning.
3. Identify which files will be added or modified.
4. Define the expected behavior and acceptance criteria.
5. Add or update automated tests.
6. Implement the smallest useful change.
7. Run the tests and report the actual results.
8. Explain how a human can verify the behavior manually.
9. Update the README when the workflow or setup changes.
10. Wait for approval before moving into a major new phase.

Keep changes focused and reviewable. Do not silently change existing behavior or remove working functionality.

When something is ambiguous, ask a question or state a reasonable assumption explicitly.

Do not install new dependencies without explaining why they are needed.

Do not commit, push, deploy, or publish changes unless explicitly instructed.

## 9. Implementation Roadmap

### Phase 1 — Stable MVP

- Preserve the current Streamlit application.
- Improve the existing listing model.
- Implement search, filters, sorting, and detailed pricing.
- Add comparable-sale statistics using fictional data.
- Implement a transparent potential-bargain indicator.
- Add automated tests for the new business rules.
- Clearly label all sample data as fictional.

### Phase 2 — Persistence and User Features

- Introduce SQLite or another appropriate store.
- Add a watchlist and saved searches.
- Add CSV import and export.
- Improve listing detail pages and source attribution.
- Add duplicate detection.

### Phase 3 — Real Auction Data

- Verify the permitted data-access method for each auction house.
- Implement one source at a time.
- Validate collected records against the original source.
- Add monitoring for collection failures and stale listings.
- Keep manual import available when automated collection is unsuitable.

### Phase 4 — Research and Valuation

- Improve comparable matching.
- Add historical sale-price analysis.
- Add AI-assisted item research and description extraction.
- Add transparent confidence indicators.
- Require human review for uncertain matches and consequential conclusions.

### Phase 5 — Production Readiness

Only if justified by actual use:

- Evaluate a move to FastAPI and PostgreSQL.
- Add user accounts and secure cloud hosting.
- Introduce scheduled data collection and notifications.
- Add backup, logging, monitoring, and recovery procedures.
- Review data licensing, security, privacy, and operating costs.

## 10. Definition of Done

A feature is complete only when:

- It meets its stated acceptance criteria.
- Automated tests cover its important business rules.
- Existing tests continue to pass.
- The application runs without errors.
- Errors and missing information are handled clearly.
- The README explains any relevant setup or usage changes.
- No fictional or AI-generated data is misrepresented as verified real-world information.
- The developer provides a concise summary of changed files, tests executed, known limitations, and suggested next steps.

## Initial Instruction

Begin by inspecting the current repository and reporting:

1. What is already implemented.
2. Which tests exist and whether they pass.
3. Any obvious architectural or correctness issues.
4. The smallest sensible next feature to implement.

Do not start by rewriting the application. Propose the next feature and its acceptance criteria first, then wait for approval.