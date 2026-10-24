from datetime import date, datetime, timezone
from typing import Iterable, List

from auction_sources.base import SourceRecord
from models import AuctionListing


def _parse_sale_date(sale_date_iso: str | None) -> date | None:
    if not sale_date_iso:
        return None
    return date.fromisoformat(sale_date_iso)


def normalize_source_record(record: SourceRecord) -> AuctionListing:
    if not record.item_title.strip():
        raise ValueError("item_title is required")
    if not record.category.strip():
        raise ValueError("category is required")
    if not record.auction_house.strip():
        raise ValueError("auction_house is required")
    if not record.status.strip():
        raise ValueError("status is required")
    if record.price_cad < 0:
        raise ValueError("price_cad cannot be negative")
    if record.buyer_premium_percent < 0:
        raise ValueError("buyer_premium_percent cannot be negative")
    if record.shipping_cad < 0:
        raise ValueError("shipping_cad cannot be negative")
    if record.other_fees_cad < 0:
        raise ValueError("other_fees_cad cannot be negative")
    if record.tax_percent is not None and record.tax_percent < 0:
        raise ValueError("tax_percent cannot be negative")

    return AuctionListing(
        item=record.item_title.strip(),
        category=record.category.strip(),
        auction_house=record.auction_house.strip(),
        status=record.status.strip(),
        price_cad=record.price_cad,
        buyer_premium_percent=record.buyer_premium_percent,
        shipping_cad=record.shipping_cad,
        other_fees_cad=record.other_fees_cad,
        tax_percent=record.tax_percent,
        description=record.description.strip(),
        location=record.location,
        listing_url=record.listing_url,
        lot_number=record.lot_number,
        sale_date=_parse_sale_date(record.sale_date_iso),
        source_name=record.source_name,
        source_record_id=record.source_record_id,
        last_checked_at=record.collected_at
        or datetime.now(timezone.utc),
    )


def normalize_source_records(
    records: Iterable[SourceRecord],
) -> List[AuctionListing]:
    return [normalize_source_record(record) for record in records]
