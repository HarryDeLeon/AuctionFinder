from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class AuctionListing:
    item: str
    category: str
    auction_house: str
    status: str
    price_cad: float
    buyer_premium_percent: float
    shipping_cad: float
    other_fees_cad: float = 0.0
    tax_percent: Optional[float] = None
    description: str = ""
    location: Optional[str] = None
    listing_url: Optional[str] = None
    lot_number: Optional[str] = None
    sale_date: Optional[date] = None
    currency: str = "CAD"
    source_name: Optional[str] = None
    source_record_id: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    comparability_confidence: Optional[float] = None
    confidence_notes: Optional[str] = None