from dataclasses import dataclass
from typing import List, Optional

from models import AuctionListing


@dataclass
class PriceBreakdown:
    listed_or_hammer_price_cad: float
    buyer_premium_cad: float
    shipping_cad: float
    other_fees_cad: float
    tax_percent: Optional[float]
    tax_cad: float
    estimated_total_cad: float
    excluded_charges: List[str]
    is_estimate: bool
    estimate_notes: Optional[str]


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def calculate_price_breakdown(
    listing: AuctionListing,
    include_taxes: bool = False,
) -> PriceBreakdown:
    """Calculate a transparent CAD cost breakdown for a listing."""

    _validate_non_negative("price_cad", listing.price_cad)
    _validate_non_negative(
        "buyer_premium_percent", listing.buyer_premium_percent
    )
    _validate_non_negative("shipping_cad", listing.shipping_cad)
    _validate_non_negative("other_fees_cad", listing.other_fees_cad)

    if listing.tax_percent is not None:
        _validate_non_negative("tax_percent", listing.tax_percent)

    premium = (
        listing.price_cad
        * listing.buyer_premium_percent
        / 100
    )
    subtotal = (
        listing.price_cad
        + premium
        + listing.shipping_cad
        + listing.other_fees_cad
    )

    excluded_charges: List[str] = []
    tax_cad = 0.0
    if include_taxes:
        if listing.tax_percent is None:
            excluded_charges.append(
                "Taxes excluded: no tax rate available."
            )
        else:
            tax_cad = subtotal * listing.tax_percent / 100
    else:
        excluded_charges.append(
            "Taxes excluded by current estimate settings."
        )

    estimate_notes: Optional[str] = None
    is_estimate = listing.status.lower() == "active"
    if is_estimate:
        estimate_notes = (
            "Active auction: estimate uses current bid, "
            "not final hammer price."
        )

    total = subtotal + tax_cad
    return PriceBreakdown(
        listed_or_hammer_price_cad=round(listing.price_cad, 2),
        buyer_premium_cad=round(premium, 2),
        shipping_cad=round(listing.shipping_cad, 2),
        other_fees_cad=round(listing.other_fees_cad, 2),
        tax_percent=listing.tax_percent if include_taxes else None,
        tax_cad=round(tax_cad, 2),
        estimated_total_cad=round(total, 2),
        excluded_charges=excluded_charges,
        is_estimate=is_estimate,
        estimate_notes=estimate_notes,
    )


def calculate_estimated_cost(
    listing: AuctionListing,
    include_taxes: bool = False,
) -> float:
    breakdown = calculate_price_breakdown(
        listing,
        include_taxes=include_taxes,
    )
    return breakdown.estimated_total_cad