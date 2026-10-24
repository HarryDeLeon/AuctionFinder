
import pandas as pd
import streamlit as st
from io import StringIO

from auction_sources import load_manual_source_csv_preview_with_report
from comparables import analyze_listing_against_comparables
from duplicate_detection import summarize_potential_duplicates
from pricing import calculate_price_breakdown
from repositories import (
    delete_saved_search,
    delete_watchlist_entry,
    export_saved_searches_to_csv,
    export_watchlist_to_csv,
    import_saved_searches_from_csv,
    import_watchlist_from_csv,
    initialize_database,
    list_saved_searches,
    list_watchlist_entries,
    upsert_saved_search,
    upsert_watchlist_entry,
)
from sample_data import AUCTIONS
from search import search_listings

MANUAL_SOURCE_REQUIRED_COLUMNS = [
    "source_record_id",
    "item_title",
    "category",
    "auction_house",
    "status",
    "price_cad",
    "buyer_premium_percent",
    "shipping_cad",
]
MANUAL_SOURCE_OPTIONAL_COLUMNS = [
    "description",
    "location",
    "listing_url",
    "lot_number",
    "sale_date_iso",
    "other_fees_cad",
    "tax_percent",
]
MANUAL_SOURCE_TEMPLATE_CSV = (
    "source_record_id,item_title,category,auction_house,status,price_cad,"
    "buyer_premium_percent,shipping_cad,description,location,listing_url,"
    "lot_number,sale_date_iso,other_fees_cad,tax_percent\n"
    "demo-1,Blue and white porcelain vase,Porcelain,Demo Auction House A,"
    "Active,275,22,40,Hand-painted floral vase,Vancouver BC,"
    "https://example.com/listings/demo-1,12,2026-10-25,0,5\n"
)


st.set_page_config(
    page_title="Antique Auction Finder",
    page_icon="🏺",
    layout="wide",
)

st.title("🏺 Antique Auction Price Finder")
st.write(
    "Compare antique listings and investigate "
    "potential bargains across auction houses."
)

st.info(
    "Prototype mode: all listings are fictional. "
    "No live auction data is connected."
)

initialize_database()
saved_searches = list_saved_searches()
watchlist_entries = list_watchlist_entries()
if "imported_source_listings" not in st.session_state:
    st.session_state["imported_source_listings"] = []
if "show_import_preview" not in st.session_state:
    st.session_state["show_import_preview"] = False
if "manual_preview_reject_csv" not in st.session_state:
    st.session_state["manual_preview_reject_csv"] = ""
if "manual_preview_summary" not in st.session_state:
    st.session_state["manual_preview_summary"] = {
        "total": 0,
        "valid": 0,
        "rejected": 0,
    }

# Search controls
search = st.text_input(
    "Search antiques",
    placeholder="Try vase, silver, painting...",
    key="search_keyword",
)

categories = ["All"] + sorted(
    {listing.category for listing in AUCTIONS}
)
category = st.selectbox(
    "Category",
    categories,
    key="category_filter",
)

status = st.selectbox(
    "Auction status",
    ["All", "Active", "Sold"],
    key="status_filter",
)

price_col1, price_col2 = st.columns(2)

min_price_cad = price_col1.number_input(
    "Minimum price (CAD)",
    min_value=0.0,
    value=st.session_state.get("min_price_cad", 0.0),
    step=25.0,
    key="min_price_cad",
)
max_price_cad_raw = price_col2.number_input(
    "Maximum price (CAD, 0 = no cap)",
    min_value=0.0,
    value=st.session_state.get("max_price_cad", 0.0),
    step=25.0,
    key="max_price_cad",
)

sort_col1, sort_col2 = st.columns(2)
sort_by = sort_col1.selectbox(
    "Sort by",
    [
        "Estimated total (CAD)",
        "Price (CAD)",
        "Relevance",
    ],
    key="sort_by",
)
sort_desc = sort_col2.checkbox(
    "Descending",
    value=st.session_state.get("sort_desc", False),
    key="sort_desc",
)

with st.sidebar:
    st.header("Saved searches")
    save_search_name = st.text_input(
        "Saved search name",
        placeholder="e.g. Porcelain under $500",
        key="saved_search_name",
    )
    if st.button("Save current filters"):
        try:
            upsert_saved_search(
                name=save_search_name,
                keyword=search,
                category=category,
                status=status,
                min_price_cad=min_price_cad if min_price_cad > 0 else None,
                max_price_cad=(
                    max_price_cad_raw if max_price_cad_raw > 0 else None
                ),
                sort_by=sort_by,
                sort_desc=sort_desc,
            )
            st.success("Saved search stored.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    saved_search_names = [row["name"] for row in saved_searches]
    selected_saved_search = st.selectbox(
        "Saved search list",
        options=["(none)"] + saved_search_names,
        key="selected_saved_search",
    )

    if st.button("Load selected search"):
        if selected_saved_search == "(none)":
            st.info("Select a saved search first.")
        else:
            selected = next(
                row
                for row in saved_searches
                if row["name"] == selected_saved_search
            )
            st.session_state["search_keyword"] = selected["keyword"]
            st.session_state["category_filter"] = selected["category"]
            st.session_state["status_filter"] = selected["status"]
            st.session_state["min_price_cad"] = (
                float(selected["min_price_cad"])
                if selected["min_price_cad"] is not None
                else 0.0
            )
            st.session_state["max_price_cad"] = (
                float(selected["max_price_cad"])
                if selected["max_price_cad"] is not None
                else 0.0
            )
            st.session_state["sort_by"] = selected["sort_by"]
            st.session_state["sort_desc"] = bool(selected["sort_desc"])
            st.success(f"Loaded '{selected_saved_search}'.")
            st.rerun()

    if st.button("Delete selected search"):
        if selected_saved_search == "(none)":
            st.info("Select a saved search first.")
        else:
            delete_saved_search(selected_saved_search)
            st.success(f"Deleted '{selected_saved_search}'.")
            st.rerun()

    st.divider()
    st.subheader("CSV import/export")
    st.download_button(
        label="Export saved searches CSV",
        data=export_saved_searches_to_csv(),
        file_name="saved_searches.csv",
        mime="text/csv",
    )
    saved_search_upload = st.file_uploader(
        "Import saved searches CSV",
        type=["csv"],
        key="saved_search_upload",
    )
    if st.button("Import saved searches"):
        if saved_search_upload is None:
            st.info("Choose a CSV file first.")
        else:
            try:
                imported_count = import_saved_searches_from_csv(
                    saved_search_upload.getvalue().decode("utf-8")
                )
                st.success(
                    f"Imported {imported_count} saved search row(s)."
                )
                st.rerun()
            except UnicodeDecodeError:
                st.error("CSV must be UTF-8 encoded.")
            except ValueError as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Manual source import preview")
    st.checkbox(
        "Enable prototype manual source CSV preview",
        key="show_import_preview",
    )
    with st.expander("CSV requirements", expanded=False):
        st.write("**Required columns**")
        st.code(", ".join(MANUAL_SOURCE_REQUIRED_COLUMNS))
        st.write("**Optional columns**")
        st.code(", ".join(MANUAL_SOURCE_OPTIONAL_COLUMNS))
        st.download_button(
            "Download manual source CSV template",
            data=MANUAL_SOURCE_TEMPLATE_CSV,
            file_name="manual_source_template.csv",
            mime="text/csv",
        )

    if st.session_state["show_import_preview"]:
        import_upload = st.file_uploader(
            "Manual source CSV",
            type=["csv"],
            key="manual_source_import_upload",
            help=(
                "Prototype only: validates and previews rows in-session. "
                "No records are auto-merged into persisted watchlists."
            ),
        )
        if st.button("Load manual source preview"):
            if import_upload is None:
                st.info("Choose a CSV file first.")
            else:
                try:
                    preview_result = load_manual_source_csv_preview_with_report(
                        import_upload.getvalue().decode("utf-8")
                    )
                    imported_listings = preview_result.listings
                    st.session_state["imported_source_listings"] = (
                        imported_listings
                    )
                    st.session_state["manual_preview_reject_csv"] = (
                        preview_result.rejected_rows_csv
                    )
                    st.session_state["manual_preview_summary"] = {
                        "total": preview_result.total_rows,
                        "valid": preview_result.valid_rows,
                        "rejected": len(preview_result.rejected_rows),
                    }
                    if preview_result.rejected_rows:
                        st.warning(
                            "Preview loaded with validation issues. "
                            f"{preview_result.valid_rows} valid row(s), "
                            f"{len(preview_result.rejected_rows)} rejected row(s)."
                        )
                    else:
                        st.success(
                            f"Loaded {len(imported_listings)} listing(s) "
                            "into preview mode."
                        )
                    st.rerun()
                except UnicodeDecodeError:
                    st.error("CSV must be UTF-8 encoded.")
                except ValueError as exc:
                    st.session_state["manual_preview_reject_csv"] = ""
                    st.session_state["manual_preview_summary"] = {
                        "total": 0,
                        "valid": 0,
                        "rejected": 0,
                    }
                    st.error(str(exc))

        preview_summary = st.session_state["manual_preview_summary"]
        if preview_summary["total"] > 0:
            st.caption(
                "Last preview result: "
                f"{preview_summary['valid']} valid / "
                f"{preview_summary['rejected']} rejected "
                f"(total {preview_summary['total']})."
            )
            if (
                preview_summary["rejected"] > 0
                and st.session_state["manual_preview_reject_csv"]
            ):
                st.write("**Correction workflow**")
                st.caption(
                    "1) Download the clean template. "
                    "2) Download rejected rows. "
                    "3) Copy corrected values into the template format. "
                    "4) Re-upload the corrected CSV."
                )
                correction_col1, correction_col2 = st.columns(2)
                correction_col1.download_button(
                    "Download clean template CSV",
                    data=MANUAL_SOURCE_TEMPLATE_CSV,
                    file_name="manual_source_template.csv",
                    mime="text/csv",
                )
                correction_col2.download_button(
                    "Download rejected rows CSV",
                    data=st.session_state["manual_preview_reject_csv"],
                    file_name="manual_source_rejected_rows.csv",
                    mime="text/csv",
                )
                rejected_preview_df = pd.read_csv(
                    StringIO(st.session_state["manual_preview_reject_csv"])
                )
                st.write("**Rejected rows preview (up to 10)**")
                st.dataframe(
                    rejected_preview_df.head(10),
                    use_container_width=True,
                    hide_index=True,
                )
                error_messages = (
                    rejected_preview_df["error_message"]
                    .dropna()
                    .astype(str)
                    .str.lower()
                    .tolist()
                    if "error_message" in rejected_preview_df.columns
                    else []
                )
                fix_tips = []
                if any("required" in message for message in error_messages):
                    fix_tips.append(
                        "Fill all required fields for each row "
                        "(for example: source_record_id, item_title, "
                        "category, auction_house, status)."
                    )
                if any("must be numeric" in message for message in error_messages):
                    fix_tips.append(
                        "Use numeric values only in numeric columns "
                        "(price_cad, buyer_premium_percent, shipping_cad, "
                        "other_fees_cad, tax_percent)."
                    )
                if any("cannot be negative" in message for message in error_messages):
                    fix_tips.append(
                        "Use zero or positive values for price/fees/tax fields."
                    )
                if fix_tips:
                    st.write("**Common fix tips**")
                    for tip in fix_tips:
                        st.caption(f"- {tip}")

        if st.button("Clear manual source preview"):
            st.session_state["imported_source_listings"] = []
            st.session_state["manual_preview_reject_csv"] = ""
            st.session_state["manual_preview_summary"] = {
                "total": 0,
                "valid": 0,
                "rejected": 0,
            }
            st.success("Manual source preview cleared.")
            st.rerun()
    else:
        st.caption(
            "Preview mode is off. Enable it to validate and temporarily add "
            "manual source rows to the current session view."
        )

# Filter and sort the listings
min_price = min_price_cad if min_price_cad > 0 else None
max_price = max_price_cad_raw if max_price_cad_raw > 0 else None
all_listings = AUCTIONS + st.session_state["imported_source_listings"]

filtered = search_listings(
    listings=all_listings,
    keyword=search,
    category=category,
    status=status,
    min_price_cad=min_price,
    max_price_cad=max_price,
    sort_by=sort_by,
    sort_desc=sort_desc,
)

# Prepare the comparison table and detail records
rows = []
detail_records = []

for listing in filtered:
    breakdown = calculate_price_breakdown(listing)
    comparables = analyze_listing_against_comparables(
        listing, all_listings
    )
    duplicate_summary = summarize_potential_duplicates(
        listing, all_listings
    )
    cost_basis = (
        "Estimate (active bid)"
        if breakdown.is_estimate
        else "Final/recorded price"
    )
    rows.append(
        {
            "Item": listing.item,
            "Category": listing.category,
            "Auction house": listing.auction_house,
            "Status": listing.status,
            "Cost basis": cost_basis,
            "Listed / hammer price (CAD)": listing.price_cad,
            "Premium (%)": listing.buyer_premium_percent,
            "Shipping (CAD)": listing.shipping_cad,
            "Estimated total (CAD)": breakdown.estimated_total_cad,
            "Comparable count": comparables.comparable_count,
            "Comparable median (CAD)": comparables.comparable_median_cad,
            "Diff vs median (%)": comparables.difference_from_median_percent,
            "Opportunity signal": comparables.opportunity_label,
            "Confidence": comparables.confidence_label,
            "Potential duplicates": duplicate_summary.candidate_count,
            "Duplicate review": duplicate_summary.review_label,
        }
    )
    detail_records.append(
        {
            "listing": listing,
            "breakdown": breakdown,
            "comparables": comparables,
            "duplicate_summary": duplicate_summary,
            "cost_basis": cost_basis,
        }
    )

st.subheader("Auction listings")
if st.session_state["imported_source_listings"]:
    st.caption(
        "Manual source preview is active. "
        f"{len(st.session_state['imported_source_listings'])} imported "
        "listing(s) are included in this session view."
    )

col1, col2 = st.columns(2)

col1.metric("Matching listings", len(rows))

if rows:
    df = pd.DataFrame(rows)

    lowest = df["Estimated total (CAD)"].min()
    opportunity_count = len(
        df[
            df["Opportunity signal"].isin(
                ["Potential opportunity", "Worth investigating"]
            )
        ]
    )
    duplicate_review_count = len(
        df[df["Duplicate review"] == "Review recommended"]
    )

    col2.metric("Lowest estimated total", f"${lowest:,.2f}")

    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric(
        "Potential / investigate signals", opportunity_count
    )
    summary_col2.metric(
        "Average comparable count",
        f"{df['Comparable count'].mean():.1f}",
    )
    summary_col3.metric(
        "Average confidence",
        df["Confidence"].mode().iloc[0],
    )
    summary_col4.metric(
        "Listings needing duplicate review",
        duplicate_review_count,
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Listing details and rationale")
    for record in detail_records:
        listing = record["listing"]
        breakdown = record["breakdown"]
        comparables = record["comparables"]
        duplicate_summary = record["duplicate_summary"]
        expander_title = (
            f"{listing.item} — {record['cost_basis']} — "
            f"{comparables.opportunity_label}"
        )
        with st.expander(expander_title):
            detail_col1, detail_col2 = st.columns(2)
            detail_col1.write(
                f"**Auction house:** {listing.auction_house}"
            )
            detail_col1.write(f"**Status:** {listing.status}")
            detail_col1.write(f"**Category:** {listing.category}")
            detail_col1.write(
                f"**Estimated total:** ${breakdown.estimated_total_cad:,.2f}"
            )

            detail_col2.write("**Price breakdown (CAD)**")
            detail_col2.write(
                f"- Listed/hammer: ${breakdown.listed_or_hammer_price_cad:,.2f}"
            )
            detail_col2.write(
                f"- Buyer premium: ${breakdown.buyer_premium_cad:,.2f}"
            )
            detail_col2.write(
                f"- Shipping: ${breakdown.shipping_cad:,.2f}"
            )
            detail_col2.write(
                f"- Other fees: ${breakdown.other_fees_cad:,.2f}"
            )
            detail_col2.write(f"- Taxes: ${breakdown.tax_cad:,.2f}")

            st.write("**Why this listing was flagged**")
            st.write(comparables.explanation)
            st.write(
                f"Comparable median: "
                f"{'$' + format(comparables.comparable_median_cad, ',.2f') if comparables.comparable_median_cad is not None else 'N/A'}"
            )
            st.write(
                "Difference vs median: "
                + (
                    f"{comparables.difference_from_median_percent}%"
                    if comparables.difference_from_median_percent is not None
                    else "N/A"
                )
            )
            st.write("**Duplicate review signal**")
            st.write(duplicate_summary.explanation)
            if duplicate_summary.candidates:
                for candidate in duplicate_summary.candidates[:3]:
                    st.write(
                        "- "
                        f"{candidate.item} ({candidate.auction_house}) "
                        f"[{candidate.confidence} confidence, score {candidate.score}] "
                        f"— {candidate.reason}"
                    )

            if breakdown.estimate_notes:
                st.info(breakdown.estimate_notes)

            if breakdown.excluded_charges:
                for excluded_charge in breakdown.excluded_charges:
                    st.caption(excluded_charge)

            save_button_key = (
                f"watchlist-save-{listing.item}-{listing.auction_house}"
            )
            if st.button("Save to watchlist", key=save_button_key):
                upsert_watchlist_entry(
                    listing=listing,
                    estimated_total_cad=breakdown.estimated_total_cad,
                )
                st.success("Saved to watchlist.")
                st.rerun()
else:
    st.warning(
        "No matching listings. Try changing your search."
    )

st.subheader("Watchlist")
watchlist_entries = list_watchlist_entries()
if watchlist_entries:
    st.download_button(
        label="Export watchlist CSV",
        data=export_watchlist_to_csv(),
        file_name="watchlist.csv",
        mime="text/csv",
    )

    watchlist_df = pd.DataFrame(watchlist_entries).rename(
        columns={
            "item_title": "Item",
            "auction_house": "Auction house",
            "status": "Status",
            "estimated_total_cad": "Estimated total (CAD)",
            "listing_url": "Listing URL",
            "last_checked_at": "Last checked (UTC)",
        }
    )
    st.dataframe(
        watchlist_df[
            [
                "Item",
                "Auction house",
                "Status",
                "Estimated total (CAD)",
                "Listing URL",
                "Last checked (UTC)",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    watchlist_options = {
        f"{row['item_title']} ({row['auction_house']})": row["item_key"]
        for row in watchlist_entries
    }
    selected_watchlist_label = st.selectbox(
        "Remove watchlist entry",
        options=list(watchlist_options.keys()),
        key="watchlist_remove_label",
    )
    if st.button("Remove selected watchlist entry"):
        delete_watchlist_entry(watchlist_options[selected_watchlist_label])
        st.success("Watchlist entry removed.")
        st.rerun()
else:
    st.caption("No watchlist entries saved yet.")

watchlist_upload = st.file_uploader(
    "Import watchlist CSV",
    type=["csv"],
    key="watchlist_upload",
)
if st.button("Import watchlist"):
    if watchlist_upload is None:
        st.info("Choose a CSV file first.")
    else:
        try:
            imported_count = import_watchlist_from_csv(
                watchlist_upload.getvalue().decode("utf-8")
            )
            st.success(f"Imported {imported_count} watchlist row(s).")
            st.rerun()
        except UnicodeDecodeError:
            st.error("CSV must be UTF-8 encoded.")
        except ValueError as exc:
            st.error(str(exc))

st.caption(
    "Estimated totals include the displayed price, buyer premium, "
    "and shipping. Taxes are excluded. For active listings, "
    "the displayed price is the current bid, not a final sale price. "
    "Comparable and opportunity signals use fictional sold records "
    "with transparent rule-based matching. Duplicate detection is "
    "conservative and flag-only; no records are merged automatically."
)
