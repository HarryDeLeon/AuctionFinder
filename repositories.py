import sqlite3
import csv
from contextlib import closing
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional

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


def initialize_database(db_path: Path = DEFAULT_DB_PATH) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
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
