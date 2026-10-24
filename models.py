from dataclasses import dataclass


@dataclass
class AuctionListing:
    item: str
    category: str
    auction_house: str
    status: str
    price_cad: float
    buyer_premium_percent: float
    shipping_cad: float