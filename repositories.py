import sqlite3
import csv
from contextlib import closing
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import AuctionListing

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "auctionfinder.db"
WATCHLIST_CSV_HEADERS = [
    "item_title",
    "auction_house",
    "status",
    "estimated_total_cad",
    "listing_url",
]
SAVED_SEARCH_CSV_HEADERS = [
    "name",
    "keyword",
    "category",
    "status",
    "min_price_cad",
    "max_price_cad",
    "sort_by",
    "sort_desc",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_has_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    columns = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return any(column[1] == column_name for column in columns)


def initialize_database(db_path: Path = DEFAULT_DB_PATH) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_entries (
                item_key TEXT PRIMARY KEY,
                item_title TEXT NOT NULL,
                auction_house TEXT NOT NULL,
                status TEXT NOT NULL,
                estimated_total_cad REAL NOT NULL,
                listing_url TEXT,
                last_checked_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_searches (
                name TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                min_price_cad REAL,
                max_price_cad REAL,
                sort_by TEXT NOT NULL,
                sort_desc INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auction_sources_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                base_url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                rate_limit_seconds REAL NOT NULL,
                crawl_max_pages INTEGER NOT NULL DEFAULT 1,
                user_agent TEXT NOT NULL,
                search_path_template TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingested_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_config_id INTEGER NOT NULL,
                source_record_id TEXT NOT NULL,
                item TEXT NOT NULL,
                category TEXT NOT NULL,
                auction_house TEXT NOT NULL,
                status TEXT NOT NULL,
                price_cad REAL NOT NULL,
                buyer_premium_percent REAL NOT NULL,
                shipping_cad REAL NOT NULL,
                other_fees_cad REAL NOT NULL,
                tax_percent REAL,
                description TEXT NOT NULL,
                location TEXT,
                image_url TEXT,
                listing_url TEXT,
                lot_number TEXT,
                opening_bid_cad REAL,
                current_bid_cad REAL,
                sale_date TEXT,
                currency TEXT NOT NULL,
                source_name TEXT,
                raw_url TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(source_config_id, source_record_id),
                FOREIGN KEY(source_config_id)
                    REFERENCES auction_sources_config(id)
                    ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_config_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                discovered_count INTEGER NOT NULL DEFAULT 0,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT,
                FOREIGN KEY(source_config_id)
                    REFERENCES auction_sources_config(id)
                    ON DELETE CASCADE
            )
            """
        )
        if not _table_has_column(conn, "auction_sources_config", "crawl_max_pages"):
            conn.execute(
                """
                ALTER TABLE auction_sources_config
                ADD COLUMN crawl_max_pages INTEGER NOT NULL DEFAULT 1
                """
            )
        if not _table_has_column(conn, "ingested_listings", "image_url"):
            conn.execute(
                """
                ALTER TABLE ingested_listings
                ADD COLUMN image_url TEXT
                """
            )
        if not _table_has_column(conn, "ingested_listings", "opening_bid_cad"):
            conn.execute(
                """
                ALTER TABLE ingested_listings
                ADD COLUMN opening_bid_cad REAL
                """
            )
        if not _table_has_column(conn, "ingested_listings", "current_bid_cad"):
            conn.execute(
                """
                ALTER TABLE ingested_listings
                ADD COLUMN current_bid_cad REAL
                """
            )
        conn.commit()


def build_listing_key(listing: AuctionListing) -> str:
    return (
        f"{listing.item}|{listing.auction_house}|"
        f"{listing.price_cad:.2f}|{listing.status}"
    )


def upsert_watchlist_entry(
    listing: AuctionListing,
    estimated_total_cad: float,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    item_key = build_listing_key(listing)
    now = _utc_now_iso()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO watchlist_entries (
                item_key,
                item_title,
                auction_house,
                status,
                estimated_total_cad,
                listing_url,
                last_checked_at,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_key) DO UPDATE SET
                status = excluded.status,
                estimated_total_cad = excluded.estimated_total_cad,
                listing_url = excluded.listing_url,
                last_checked_at = excluded.last_checked_at
            """,
            (
                item_key,
                listing.item,
                listing.auction_house,
                listing.status,
                estimated_total_cad,
                listing.listing_url,
                now,
                now,
            ),
        )
        conn.commit()


def list_watchlist_entries(
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, object]]:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                item_key,
                item_title,
                auction_house,
                status,
                estimated_total_cad,
                listing_url,
                last_checked_at,
                created_at
            FROM watchlist_entries
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_watchlist_entry(
    item_key: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "DELETE FROM watchlist_entries WHERE item_key = ?",
            (item_key,),
        )
        conn.commit()


def upsert_saved_search(
    name: str,
    keyword: str,
    category: str,
    status: str,
    min_price_cad: Optional[float],
    max_price_cad: Optional[float],
    sort_by: str,
    sort_desc: bool,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    if not name.strip():
        raise ValueError("Saved search name is required")

    now = _utc_now_iso()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO saved_searches (
                name,
                keyword,
                category,
                status,
                min_price_cad,
                max_price_cad,
                sort_by,
                sort_desc,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                keyword = excluded.keyword,
                category = excluded.category,
                status = excluded.status,
                min_price_cad = excluded.min_price_cad,
                max_price_cad = excluded.max_price_cad,
                sort_by = excluded.sort_by,
                sort_desc = excluded.sort_desc
            """,
            (
                name.strip(),
                keyword,
                category,
                status,
                min_price_cad,
                max_price_cad,
                sort_by,
                1 if sort_desc else 0,
                now,
            ),
        )
        conn.commit()


def list_saved_searches(
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, object]]:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                name,
                keyword,
                category,
                status,
                min_price_cad,
                max_price_cad,
                sort_by,
                sort_desc,
                created_at
            FROM saved_searches
            ORDER BY created_at DESC, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_saved_search(
    name: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "DELETE FROM saved_searches WHERE name = ?",
            (name,),
        )
        conn.commit()


def _require_csv_headers(
    actual_headers: Optional[List[str]],
    required_headers: List[str],
) -> None:
    if actual_headers is None:
        raise ValueError("CSV file must include a header row")
    missing = [
        header for header in required_headers if header not in actual_headers
    ]
    if missing:
        raise ValueError(
            "CSV missing required columns: " + ", ".join(missing)
        )


def export_watchlist_to_csv(
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    entries = list_watchlist_entries(db_path)
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=WATCHLIST_CSV_HEADERS)
    writer.writeheader()
    for entry in entries:
        writer.writerow(
            {
                "item_title": entry["item_title"],
                "auction_house": entry["auction_house"],
                "status": entry["status"],
                "estimated_total_cad": entry["estimated_total_cad"],
                "listing_url": entry["listing_url"] or "",
            }
        )
    return output.getvalue()


def import_watchlist_from_csv(
    csv_text: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    reader = csv.DictReader(StringIO(csv_text))
    _require_csv_headers(reader.fieldnames, WATCHLIST_CSV_HEADERS)

    imported = 0
    for row in reader:
        item_title = (row.get("item_title") or "").strip()
        auction_house = (row.get("auction_house") or "").strip()
        status = (row.get("status") or "").strip()
        estimated_total_raw = (row.get("estimated_total_cad") or "").strip()
        if not item_title or not auction_house or not status:
            raise ValueError(
                "Watchlist CSV rows must include item_title, "
                "auction_house, and status."
            )
        try:
            estimated_total = float(estimated_total_raw)
        except ValueError as exc:
            raise ValueError(
                "estimated_total_cad must be a valid number"
            ) from exc
        if estimated_total < 0:
            raise ValueError("estimated_total_cad cannot be negative")

        listing = AuctionListing(
            item=item_title,
            category="Imported",
            auction_house=auction_house,
            status=status,
            price_cad=estimated_total,
            buyer_premium_percent=0.0,
            shipping_cad=0.0,
            listing_url=(row.get("listing_url") or "").strip() or None,
        )
        upsert_watchlist_entry(
            listing=listing,
            estimated_total_cad=estimated_total,
            db_path=db_path,
        )
        imported += 1

    return imported


def export_saved_searches_to_csv(
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    entries = list_saved_searches(db_path)
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=SAVED_SEARCH_CSV_HEADERS)
    writer.writeheader()
    for entry in entries:
        writer.writerow(
            {
                "name": entry["name"],
                "keyword": entry["keyword"],
                "category": entry["category"],
                "status": entry["status"],
                "min_price_cad": (
                    "" if entry["min_price_cad"] is None else entry["min_price_cad"]
                ),
                "max_price_cad": (
                    "" if entry["max_price_cad"] is None else entry["max_price_cad"]
                ),
                "sort_by": entry["sort_by"],
                "sort_desc": int(entry["sort_desc"]),
            }
        )
    return output.getvalue()


def import_saved_searches_from_csv(
    csv_text: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    reader = csv.DictReader(StringIO(csv_text))
    _require_csv_headers(reader.fieldnames, SAVED_SEARCH_CSV_HEADERS)

    imported = 0
    for row in reader:
        name = (row.get("name") or "").strip()
        keyword = row.get("keyword") or ""
        category = (row.get("category") or "All").strip() or "All"
        status = (row.get("status") or "All").strip() or "All"
        sort_by = (
            row.get("sort_by") or "Estimated total (CAD)"
        ).strip() or "Estimated total (CAD)"
        sort_desc_raw = (row.get("sort_desc") or "0").strip().lower()

        if not name:
            raise ValueError("Saved search rows must include a name.")

        min_price_raw = (row.get("min_price_cad") or "").strip()
        max_price_raw = (row.get("max_price_cad") or "").strip()

        min_price = None
        max_price = None
        if min_price_raw:
            try:
                min_price = float(min_price_raw)
            except ValueError as exc:
                raise ValueError(
                    "min_price_cad must be a valid number"
                ) from exc
        if max_price_raw:
            try:
                max_price = float(max_price_raw)
            except ValueError as exc:
                raise ValueError(
                    "max_price_cad must be a valid number"
                ) from exc

        if sort_desc_raw in {"1", "true", "yes"}:
            sort_desc = True
        elif sort_desc_raw in {"0", "false", "no"}:
            sort_desc = False
        else:
            raise ValueError(
                "sort_desc must be one of: 1, 0, true, false, yes, no"
            )

        upsert_saved_search(
            name=name,
            keyword=keyword,
            category=category,
            status=status,
            min_price_cad=min_price,
            max_price_cad=max_price,
            sort_by=sort_by,
            sort_desc=sort_desc,
            db_path=db_path,
        )
        imported += 1

    return imported


def create_source_config(
    name: str,
    base_url: str,
    source_type: str = "dummy",
    enabled: bool = True,
    rate_limit_seconds: float = 2.0,
    crawl_max_pages: int = 1,
    user_agent: str = "AuctionFinderBot/0.1",
    search_path_template: Optional[str] = None,
    notes: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    name_clean = name.strip()
    base_url_clean = base_url.strip()
    if not name_clean:
        raise ValueError("Source name is required")
    if not base_url_clean:
        raise ValueError("Source base URL is required")
    if rate_limit_seconds < 0:
        raise ValueError("rate_limit_seconds cannot be negative")
    if crawl_max_pages < 1:
        raise ValueError("crawl_max_pages must be at least 1")

    now = _utc_now_iso()
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO auction_sources_config (
                name,
                base_url,
                source_type,
                enabled,
                rate_limit_seconds,
                crawl_max_pages,
                user_agent,
                search_path_template,
                notes,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name_clean,
                base_url_clean,
                source_type.strip() or "dummy",
                1 if enabled else 0,
                rate_limit_seconds,
                crawl_max_pages,
                user_agent.strip() or "AuctionFinderBot/0.1",
                search_path_template.strip() if search_path_template else None,
                notes.strip(),
                now,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_source_configs(
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                id,
                name,
                base_url,
                source_type,
                enabled,
                rate_limit_seconds,
                crawl_max_pages,
                user_agent,
                search_path_template,
                notes,
                created_at,
                updated_at
            FROM auction_sources_config
            ORDER BY created_at DESC, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_source_config(
    source_id: int,
    db_path: Path = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                id,
                name,
                base_url,
                source_type,
                enabled,
                rate_limit_seconds,
                crawl_max_pages,
                user_agent,
                search_path_template,
                notes,
                created_at,
                updated_at
            FROM auction_sources_config
            WHERE id = ?
            """,
            (source_id,),
        ).fetchone()
    return dict(row) if row else None


def update_source_config(
    source_id: int,
    name: str,
    base_url: str,
    source_type: str,
    enabled: bool,
    rate_limit_seconds: float,
    crawl_max_pages: int,
    user_agent: str,
    search_path_template: Optional[str],
    notes: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    if not name.strip():
        raise ValueError("Source name is required")
    if not base_url.strip():
        raise ValueError("Source base URL is required")
    if rate_limit_seconds < 0:
        raise ValueError("rate_limit_seconds cannot be negative")
    if crawl_max_pages < 1:
        raise ValueError("crawl_max_pages must be at least 1")

    now = _utc_now_iso()
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            UPDATE auction_sources_config
            SET
                name = ?,
                base_url = ?,
                source_type = ?,
                enabled = ?,
                rate_limit_seconds = ?,
                crawl_max_pages = ?,
                user_agent = ?,
                search_path_template = ?,
                notes = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                base_url.strip(),
                source_type.strip() or "dummy",
                1 if enabled else 0,
                rate_limit_seconds,
                crawl_max_pages,
                user_agent.strip() or "AuctionFinderBot/0.1",
                search_path_template.strip() if search_path_template else None,
                notes.strip(),
                now,
                source_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Source config id {source_id} was not found")
        conn.commit()


def delete_source_config(
    source_id: int,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            "DELETE FROM auction_sources_config WHERE id = ?",
            (source_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Source config id {source_id} was not found")
        conn.commit()


def create_crawl_run(
    source_config_id: int,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    now = _utc_now_iso()
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO crawl_runs (
                source_config_id,
                started_at,
                status
            )
            VALUES (?, ?, ?)
            """,
            (source_config_id, now, "running"),
        )
        conn.commit()
        return int(cursor.lastrowid)


def complete_crawl_run(
    run_id: int,
    status: str,
    discovered_count: int,
    inserted_count: int,
    updated_count: int,
    rejected_count: int,
    error_summary: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    if status not in {"success", "partial", "failed"}:
        raise ValueError("status must be one of: success, partial, failed")

    now = _utc_now_iso()
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            UPDATE crawl_runs
            SET
                finished_at = ?,
                status = ?,
                discovered_count = ?,
                inserted_count = ?,
                updated_count = ?,
                rejected_count = ?,
                error_summary = ?
            WHERE id = ?
            """,
            (
                now,
                status,
                discovered_count,
                inserted_count,
                updated_count,
                rejected_count,
                error_summary,
                run_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Crawl run id {run_id} was not found")
        conn.commit()


def list_recent_crawl_runs(
    source_config_id: Optional[int] = None,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    query = """
        SELECT
            id,
            source_config_id,
            started_at,
            finished_at,
            status,
            discovered_count,
            inserted_count,
            updated_count,
            rejected_count,
            error_summary
        FROM crawl_runs
    """
    params: List[Any] = []
    if source_config_id is not None:
        query += " WHERE source_config_id = ?"
        params.append(source_config_id)
    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def upsert_ingested_listing(
    source_config_id: int,
    listing: AuctionListing,
    raw_url: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    source_record_id = (
        listing.source_record_id
        or build_listing_key(listing)
    )
    now = _utc_now_iso()
    sale_date_iso = (
        listing.sale_date.isoformat()
        if listing.sale_date is not None
        else None
    )
    existing = None

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            """
            SELECT id
            FROM ingested_listings
            WHERE source_config_id = ? AND source_record_id = ?
            """,
            (source_config_id, source_record_id),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO ingested_listings (
                    source_config_id,
                    source_record_id,
                    item,
                    category,
                    auction_house,
                    status,
                    price_cad,
                    buyer_premium_percent,
                    shipping_cad,
                    other_fees_cad,
                    tax_percent,
                    description,
                    location,
                    image_url,
                    listing_url,
                    lot_number,
                    opening_bid_cad,
                    current_bid_cad,
                    sale_date,
                    currency,
                    source_name,
                    raw_url,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    source_config_id,
                    source_record_id,
                    listing.item,
                    listing.category,
                    listing.auction_house,
                    listing.status,
                    listing.price_cad,
                    listing.buyer_premium_percent,
                    listing.shipping_cad,
                    listing.other_fees_cad,
                    listing.tax_percent,
                    listing.description,
                    listing.location,
                    listing.image_url,
                    listing.listing_url,
                    listing.lot_number,
                    listing.opening_bid_cad,
                    listing.current_bid_cad,
                    sale_date_iso,
                    listing.currency,
                    listing.source_name,
                    raw_url,
                    now,
                    now,
                ),
            )
            conn.commit()
            return "inserted"

        conn.execute(
            """
            UPDATE ingested_listings
            SET
                item = ?,
                category = ?,
                auction_house = ?,
                status = ?,
                price_cad = ?,
                buyer_premium_percent = ?,
                shipping_cad = ?,
                other_fees_cad = ?,
                tax_percent = ?,
                description = ?,
                location = ?,
                image_url = ?,
                listing_url = ?,
                lot_number = ?,
                opening_bid_cad = ?,
                current_bid_cad = ?,
                sale_date = ?,
                currency = ?,
                source_name = ?,
                raw_url = ?,
                last_seen_at = ?
            WHERE source_config_id = ? AND source_record_id = ?
            """,
            (
                listing.item,
                listing.category,
                listing.auction_house,
                listing.status,
                listing.price_cad,
                listing.buyer_premium_percent,
                listing.shipping_cad,
                listing.other_fees_cad,
                listing.tax_percent,
                listing.description,
                listing.location,
                listing.image_url,
                listing.listing_url,
                listing.lot_number,
                listing.opening_bid_cad,
                listing.current_bid_cad,
                sale_date_iso,
                listing.currency,
                listing.source_name,
                raw_url,
                now,
                source_config_id,
                source_record_id,
            ),
        )
        conn.commit()
    return "updated"


def list_ingested_listings(
    source_config_id: Optional[int] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    query = """
        SELECT
            id,
            source_config_id,
            source_record_id,
            item,
            category,
            auction_house,
            status,
            price_cad,
            buyer_premium_percent,
            shipping_cad,
            other_fees_cad,
            tax_percent,
            description,
            location,
            image_url,
            listing_url,
            lot_number,
            opening_bid_cad,
            current_bid_cad,
            sale_date,
            currency,
            source_name,
            raw_url,
            first_seen_at,
            last_seen_at
        FROM ingested_listings
    """
    params: List[Any] = []
    if source_config_id is not None:
        query += " WHERE source_config_id = ?"
        params.append(source_config_id)
    query += " ORDER BY last_seen_at DESC"

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]
