from models import AuctionListing


def calculate_estimated_cost(
    listing: AuctionListing,
) -> float:
    """Calculate price plus buyer premium and shipping."""

    premium = (
        listing.price_cad
        * listing.buyer_premium_percent
        / 100
    )

    total = (
        listing.price_cad
        + premium
        + listing.shipping_cad
    )

    return round(total, 2)