import re
from dataclasses import dataclass
from statistics import mean, median
from typing import List, Optional, Set

from models import AuctionListing
from pricing import calculate_price_breakdown

_STOP_WORDS = {
    "antique",
    "vintage",
    "with",
    "from",
    "and",
    "the",
    "for",
    "details",
}


@dataclass
class ComparableSummary:
    comparable_count: int
    comparable_min_cad: Optional[float]
    comparable_max_cad: Optional[float]
    comparable_median_cad: Optional[float]
    comparable_average_cad: Optional[float]
    difference_from_median_cad: Optional[float]
    difference_from_median_percent: Optional[float]
    confidence_label: str
    opportunity_label: str
    explanation: str


def _tokenize(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {
        word
        for word in words
        if len(word) >= 4 and word not in _STOP_WORDS
    }


def _confidence_label(
    comparable_count: int,
    avg_token_overlap: float,
) -> str:
    if comparable_count >= 5 and avg_token_overlap >= 2:
        return "High"
    if comparable_count >= 2:
        return "Medium"
    return "Low"


def analyze_listing_against_comparables(
    listing: AuctionListing,
    all_listings: List[AuctionListing],
) -> ComparableSummary:
    listing_tokens = _tokenize(
        f"{listing.item} {listing.description}"
    )

    comparable_totals: List[float] = []
    overlap_scores: List[int] = []

    for candidate in all_listings:
        if candidate.status != "Sold":
            continue
        if candidate.category != listing.category:
            continue
        if (
            candidate.item == listing.item
            and candidate.auction_house == listing.auction_house
            and candidate.price_cad == listing.price_cad
        ):
            continue

        candidate_tokens = _tokenize(
            f"{candidate.item} {candidate.description}"
        )
        overlap = len(listing_tokens.intersection(candidate_tokens))

        # Transparent rule: require at least one shared token when available.
        if listing_tokens and candidate_tokens and overlap == 0:
            continue

        comparable_totals.append(
            calculate_price_breakdown(candidate).estimated_total_cad
        )
        overlap_scores.append(overlap)

    comparable_count = len(comparable_totals)
    if comparable_count == 0:
        return ComparableSummary(
            comparable_count=0,
            comparable_min_cad=None,
            comparable_max_cad=None,
            comparable_median_cad=None,
            comparable_average_cad=None,
            difference_from_median_cad=None,
            difference_from_median_percent=None,
            confidence_label="Low",
            opportunity_label="Not enough information",
            explanation=(
                "No suitable sold comparables were found "
                "for this listing."
            ),
        )

    candidate_total = calculate_price_breakdown(
        listing
    ).estimated_total_cad
    median_total = float(median(comparable_totals))
    difference_cad = candidate_total - median_total
    difference_percent = (
        difference_cad / median_total * 100 if median_total else 0.0
    )

    avg_overlap = mean(overlap_scores) if overlap_scores else 0.0
    confidence = _confidence_label(comparable_count, avg_overlap)

    if comparable_count < 2:
        opportunity_label = "Limited comparable evidence"
    elif listing.status == "Active":
        if difference_percent <= -15:
            opportunity_label = "Potential opportunity"
        elif difference_percent <= -5:
            opportunity_label = "Worth investigating"
        else:
            opportunity_label = "No clear bargain signal"
    else:
        opportunity_label = "Comparable baseline available"

    explanation = (
        f"{comparable_count} sold comparable(s), median estimated total "
        f"${median_total:,.2f}, listing differs by {difference_percent:.1f}%."
    )

    return ComparableSummary(
        comparable_count=comparable_count,
        comparable_min_cad=round(min(comparable_totals), 2),
        comparable_max_cad=round(max(comparable_totals), 2),
        comparable_median_cad=round(median_total, 2),
        comparable_average_cad=round(float(mean(comparable_totals)), 2),
        difference_from_median_cad=round(difference_cad, 2),
        difference_from_median_percent=round(difference_percent, 2),
        confidence_label=confidence,
        opportunity_label=opportunity_label,
        explanation=explanation,
    )
