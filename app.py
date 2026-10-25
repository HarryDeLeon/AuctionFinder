
import pandas as pd
import streamlit as st
from datetime import date, datetime
from io import StringIO

from auction_sources import load_manual_source_csv_preview_with_report
from comparables import analyze_listing_against_comparables
from duplicate_detection import summarize_potential_duplicates
from ingestion import run_source_crawl
from ingestion import run_source_keyword_crawl
from models import AuctionListing
from pricing import calculate_price_breakdown
from repositories import (
    create_source_config,
    delete_source_config,
    delete_saved_search,
    delete_watchlist_entry,
    export_saved_searches_to_csv,
    export_watchlist_to_csv,
    import_saved_searches_from_csv,
    import_watchlist_from_csv,
    initialize_database,
    list_ingested_listings,
    list_recent_crawl_runs,
    list_saved_searches,
    list_source_configs,
    list_watchlist_entries,
    update_source_config,
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
HTML_RECOMMENDED_BASE_URL = "https://www.liveauctionworld.com/auctionlist.aspx"
HTML_RECOMMENDED_SEARCH_TEMPLATE = "/search.aspx"
HTML_RECOMMENDED_MAX_PAGES = 2


def _listing_from_ingested_row(row: dict) -> AuctionListing:
    sale_date_value = (
        date.fromisoformat(str(row["sale_date"]))
        if row.get("sale_date")
        else None
    )
    last_checked = (
        datetime.fromisoformat(str(row["last_seen_at"]))
        if row.get("last_seen_at")
        else None
    )
    return AuctionListing(
        item=str(row["item"]),
        category=str(row["category"]),
        auction_house=str(row["auction_house"]),
        status=str(row["status"]),
        price_cad=float(row["price_cad"]),
        buyer_premium_percent=float(row["buyer_premium_percent"]),
        shipping_cad=float(row["shipping_cad"]),
        other_fees_cad=float(row["other_fees_cad"]),
        tax_percent=(
            float(row["tax_percent"])
            if row.get("tax_percent") is not None
            else None
        ),
        description=str(row.get("description") or ""),
        location=row.get("location"),
        listing_url=row.get("listing_url"),
        lot_number=row.get("lot_number"),
        sale_date=sale_date_value,
        currency=str(row.get("currency") or "CAD"),
        source_name=row.get("source_name"),
        source_record_id=row.get("source_record_id"),
        last_checked_at=last_checked,
    )


def _load_selected_saved_search(saved_searches: list[dict]) -> None:
    selected_saved_search = st.session_state.get(
        "selected_saved_search",
        "(none)",
    )
    if selected_saved_search == "(none)":
        st.session_state["_saved_search_load_message"] = (
            "Select a saved search first."
        )
        st.session_state["_saved_search_load_message_type"] = "info"
        return

    selected = next(
        (
            row
            for row in saved_searches
            if row["name"] == selected_saved_search
        ),
        None,
    )
    if selected is None:
        st.session_state["_saved_search_load_message"] = (
            "Saved search was not found. Please refresh and try again."
        )
        st.session_state["_saved_search_load_message_type"] = "error"
        return

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
    st.session_state["_saved_search_load_message"] = (
        f"Loaded '{selected_saved_search}'."
    )
    st.session_state["_saved_search_load_message_type"] = "success"


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
    "Prototype mode: sample and ingestion listings are currently "
    "demonstration data. Live scraping adapters are not connected yet."
)

initialize_database()
saved_searches = list_saved_searches()
watchlist_entries = list_watchlist_entries()
ingested_listing_rows = list_ingested_listings()
ingested_listings = [
    _listing_from_ingested_row(row) for row in ingested_listing_rows
]
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

all_categories = {
    listing.category
    for listing in (AUCTIONS + ingested_listings)
}
categories = ["All"] + sorted(all_categories)
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

search_action_col1, search_action_col2 = st.columns(2)
if search_action_col1.button("Search web source now"):
    normalized_search = search.strip()
    if not normalized_search:
        st.info("Enter a keyword first (for example: rifle).")
    else:
        available_html_sources = [
            source
            for source in list_source_configs()
            if bool(source["enabled"]) and source["source_type"] == "html"
        ]
        if not available_html_sources:
            try:
                created_source_id = create_source_config(
                    name="LiveAuctionWorld",
                    base_url=HTML_RECOMMENDED_BASE_URL,
                    source_type="html",
                    enabled=True,
                    rate_limit_seconds=2.0,
                    crawl_max_pages=HTML_RECOMMENDED_MAX_PAGES,
                    user_agent="AuctionFinderBot/0.1",
                    search_path_template=HTML_RECOMMENDED_SEARCH_TEMPLATE,
                    notes="Auto-created from web keyword search action.",
                )
                available_html_sources = [
                    source
                    for source in list_source_configs()
                    if int(source["id"]) == created_source_id
                ]
                st.info(
                    "No enabled HTML source existed. "
                    "Created a default LiveAuctionWorld source and running it now."
                )
            except ValueError as exc:
                st.error(
                    "No enabled HTML sources are configured and automatic "
                    f"source creation failed: {exc}"
                )
                available_html_sources = []
        if available_html_sources:
            total_discovered = 0
            total_inserted = 0
            total_updated = 0
            source_errors = []
            for source in available_html_sources:
                summary = run_source_keyword_crawl(
                    source_config_id=int(source["id"]),
                    keyword=normalized_search,
                )
                total_discovered += summary.discovered_count
                total_inserted += summary.inserted_count
                total_updated += summary.updated_count
                if summary.status != "success" and summary.error_summary:
                    source_errors.append(
                        f"{source['name']}: {summary.error_summary}"
                    )

            if total_discovered > 0:
                st.success(
                    "Web keyword crawl complete. "
                    f"Matched {total_discovered} item(s); "
                    f"inserted {total_inserted}, updated {total_updated}."
                )
            else:
                st.warning(
                    "Web crawl completed but found no keyword matches. "
                    "Try increasing max pages in source settings."
                )

            if source_errors:
                st.warning("Some sources reported issues:")
                for source_error in source_errors:
                    st.caption(f"- {source_error}")
            st.rerun()

search_action_col2.caption(
    "Runs a live keyword crawl against enabled HTML sources and stores matches."
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

    st.button(
        "Load selected search",
        on_click=_load_selected_saved_search,
        args=(saved_searches,),
    )

    if st.session_state.get("_saved_search_load_message"):
        message = str(st.session_state["_saved_search_load_message"])
        message_type = st.session_state.get(
            "_saved_search_load_message_type",
            "info",
        )
        if message_type == "success":
            st.success(message)
        elif message_type == "error":
            st.error(message)
        else:
            st.info(message)
        st.session_state.pop("_saved_search_load_message", None)
        st.session_state.pop("_saved_search_load_message_type", None)

    if st.button("Delete selected search"):
        if selected_saved_search == "(none)":
            st.info("Select a saved search first.")
        else:
            delete_saved_search(selected_saved_search)
            st.success(f"Deleted '{selected_saved_search}'.")
            st.rerun()

    st.divider()
    st.subheader("Auction source registry (prototype)")
    st.caption(
        "Configure source records and run a dummy crawl to validate the "
        "new ingestion pipeline foundation."
    )

    with st.form("source_add_form"):
        st.write("**Add source**")
        add_source_type = st.selectbox(
            "Source type",
            options=["dummy", "html", "api", "rss"],
            index=0,
        )
        default_base_url = (
            HTML_RECOMMENDED_BASE_URL
            if add_source_type == "html"
            else "https://www.liveauctionworld.com/"
        )
        default_search_template = (
            HTML_RECOMMENDED_SEARCH_TEMPLATE
            if add_source_type == "html"
            else ""
        )
        default_max_pages = (
            HTML_RECOMMENDED_MAX_PAGES
            if add_source_type == "html"
            else 1
        )
        add_name = st.text_input(
            "Source name",
            value="LiveAuctionWorld",
        )
        add_base_url = st.text_input(
            "Base URL",
            value=default_base_url,
        )
        add_enabled = st.checkbox("Enabled", value=True)
        add_rate_limit = st.number_input(
            "Rate limit seconds",
            min_value=0.0,
            value=2.0,
            step=0.5,
        )
        add_crawl_max_pages = st.number_input(
            "Max pages per crawl",
            min_value=1,
            value=default_max_pages,
            step=1,
        )
        add_user_agent = st.text_input(
            "User agent",
            value="AuctionFinderBot/0.1",
        )
        add_search_template = st.text_input(
            "Search path template (optional)",
            value=default_search_template,
            placeholder="/search?q={query}",
        )
        if add_source_type == "html":
            st.caption(
                "Recommended HTML source defaults applied: "
                "auction list base URL, /search.aspx template, and max pages = 2."
            )
        add_notes = st.text_area("Notes", value="")
        add_submit = st.form_submit_button("Add source")
        if add_submit:
            try:
                create_source_config(
                    name=add_name,
                    base_url=add_base_url,
                    source_type=add_source_type,
                    enabled=add_enabled,
                    rate_limit_seconds=add_rate_limit,
                    crawl_max_pages=int(add_crawl_max_pages),
                    user_agent=add_user_agent,
                    search_path_template=add_search_template or None,
                    notes=add_notes,
                )
                st.success("Source added.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    source_configs = list_source_configs()
    recent_runs = list_recent_crawl_runs(limit=200)
    latest_run_by_source = {}
    for run in recent_runs:
        source_id = int(run["source_config_id"])
        if source_id not in latest_run_by_source:
            latest_run_by_source[source_id] = run

    if source_configs:
        display_rows = [
            {
                "ID": row["id"],
                "Name": row["name"],
                "Base URL": row["base_url"],
                "Type": row["source_type"],
                "Enabled": bool(row["enabled"]),
                "Rate limit (s)": row["rate_limit_seconds"],
                "Max pages": row["crawl_max_pages"],
                "Last status": (
                    latest_run_by_source.get(int(row["id"]), {}).get("status")
                    or "Never run"
                ),
                "Last finished": latest_run_by_source.get(
                    int(row["id"]), {}
                ).get("finished_at"),
                "Last error": latest_run_by_source.get(
                    int(row["id"]), {}
                ).get("error_summary"),
            }
            for row in source_configs
        ]
        st.dataframe(
            pd.DataFrame(display_rows),
            use_container_width=True,
            hide_index=True,
        )

        source_options = {
            f"{row['name']} (#{row['id']})": int(row["id"])
            for row in source_configs
        }
        selected_source_label = st.selectbox(
            "Select source to edit",
            options=list(source_options.keys()),
            key="selected_source_config",
        )
        selected_source_id = source_options[selected_source_label]
        selected_source = next(
            row
            for row in source_configs
            if int(row["id"]) == selected_source_id
        )

        with st.form("source_edit_form"):
            st.write("**Edit source**")
            edit_name = st.text_input(
                "Source name",
                value=selected_source["name"],
            )
            edit_base_url = st.text_input(
                "Base URL",
                value=selected_source["base_url"],
            )
            type_options = ["dummy", "html", "api", "rss"]
            selected_type = selected_source["source_type"]
            edit_type_index = (
                type_options.index(selected_type)
                if selected_type in type_options
                else 0
            )
            edit_source_type = st.selectbox(
                "Source type",
                options=type_options,
                index=edit_type_index,
            )
            edit_enabled = st.checkbox(
                "Enabled",
                value=bool(selected_source["enabled"]),
            )
            edit_rate_limit = st.number_input(
                "Rate limit seconds",
                min_value=0.0,
                value=float(selected_source["rate_limit_seconds"]),
                step=0.5,
            )
            edit_crawl_max_pages = st.number_input(
                "Max pages per crawl",
                min_value=1,
                value=int(selected_source.get("crawl_max_pages") or 1),
                step=1,
            )
            edit_user_agent = st.text_input(
                "User agent",
                value=selected_source["user_agent"],
            )
            edit_search_template = st.text_input(
                "Search path template (optional)",
                value=selected_source["search_path_template"] or "",
            )
            edit_notes = st.text_area(
                "Notes",
                value=selected_source["notes"] or "",
            )
            if edit_source_type == "html":
                st.caption(
                    "Tip: for LiveAuctionWorld HTML sources, use "
                    "https://www.liveauctionworld.com/auctionlist.aspx, "
                    "search template /search.aspx, and max pages around 2-3."
                )
            edit_save_col, edit_defaults_col = st.columns(2)
            edit_submit = edit_save_col.form_submit_button("Save source changes")
            apply_html_defaults_submit = edit_defaults_col.form_submit_button(
                "Apply recommended HTML defaults"
            )
            if edit_submit:
                try:
                    update_source_config(
                        source_id=selected_source_id,
                        name=edit_name,
                        base_url=edit_base_url,
                        source_type=edit_source_type,
                        enabled=edit_enabled,
                        rate_limit_seconds=edit_rate_limit,
                        crawl_max_pages=int(edit_crawl_max_pages),
                        user_agent=edit_user_agent,
                        search_path_template=edit_search_template or None,
                        notes=edit_notes,
                    )
                    st.success("Source updated.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if apply_html_defaults_submit:
                if edit_source_type != "html":
                    st.info(
                        "Recommended defaults apply to HTML sources only. "
                        "Set source type to html first."
                    )
                else:
                    try:
                        update_source_config(
                            source_id=selected_source_id,
                            name=edit_name,
                            base_url=HTML_RECOMMENDED_BASE_URL,
                            source_type="html",
                            enabled=edit_enabled,
                            rate_limit_seconds=edit_rate_limit,
                            crawl_max_pages=HTML_RECOMMENDED_MAX_PAGES,
                            user_agent=edit_user_agent,
                            search_path_template=HTML_RECOMMENDED_SEARCH_TEMPLATE,
                            notes=edit_notes,
                        )
                        st.success(
                            "Applied recommended HTML defaults "
                            "(base URL, search template, and max pages)."
                        )
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

        source_action_col1, source_action_col2 = st.columns(2)
        if source_action_col1.button("Run selected source crawl"):
            crawl_summary = run_source_crawl(selected_source_id)
            if crawl_summary.status == "success":
                st.success(
                    "Crawl completed. "
                    f"Discovered {crawl_summary.discovered_count}, "
                    f"inserted {crawl_summary.inserted_count}, "
                    f"updated {crawl_summary.updated_count}."
                )
            elif crawl_summary.status == "partial":
                st.warning(
                    "Crawl completed with partial failures. "
                    f"Rejected {crawl_summary.rejected_count}. "
                    f"Error: {crawl_summary.error_summary}"
                )
            else:
                st.error(f"Crawl failed: {crawl_summary.error_summary}")
            st.rerun()

        if source_action_col2.button("Delete selected source"):
            try:
                delete_source_config(selected_source_id)
                st.success("Source deleted.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.caption("No sources configured yet.")

    recent_runs = list_recent_crawl_runs(limit=10)
    if recent_runs:
        runs_df = pd.DataFrame(recent_runs).rename(
            columns={
                "id": "Run ID",
                "source_config_id": "Source ID",
                "started_at": "Started",
                "finished_at": "Finished",
                "status": "Status",
                "discovered_count": "Discovered",
                "inserted_count": "Inserted",
                "updated_count": "Updated",
                "rejected_count": "Rejected",
                "error_summary": "Error summary",
            }
        )
        st.write("**Recent crawl runs**")
        st.dataframe(
            runs_df,
            use_container_width=True,
            hide_index=True,
        )

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
all_listings = (
    AUCTIONS
    + st.session_state["imported_source_listings"]
    + ingested_listings
)

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
