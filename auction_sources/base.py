from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional


@dataclass(frozen=True)
class SourceRecord:
    source_name: str
    source_record_id: str
    item_title: str
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
    sale_date_iso: Optional[str] = None
    collected_at: Optional[datetime] = None


class AuctionSource(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def load_records(self) -> Iterable[SourceRecord]:
        raise NotImplementedError
