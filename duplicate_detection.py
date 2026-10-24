import re
from dataclasses import dataclass
from typing import List, Set

from models import AuctionListing


@dataclass
class DuplicateCandidate:
    item: str
    auction_house: str
    score: float
    confidence: str
    reason: str


@dataclass
class DuplicateSummary:
    candidate_count: int
    review_label: str
    explanation: str
    candidates: List[DuplicateCandidate]


def _tokenize(text: str) -> Set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 4
    }


def _safe_jaccard(left: Set[str], right: Set[str]) -> float:
    if not left and not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


def _confidence_from_score(score: float) -> str:
    if score >= 0.9:
        return "High"
    if score >= 0.8:
        return "Medium"
    return "Low"


def summarize_potential_duplicates(
    listing: AuctionListing,
    all_listings: List[AuctionListing],
    min_score: float = 0.75,
) -> DuplicateSummary:
    listing_tokens = _tokenize(f"{listing.item} {listing.description}")
    candidates: List[DuplicateCandidate] = []

    for candidate in all_listings:
        if candidate is listing:
            continue

        score = 0.0
        reasons: List[str] = []

        if (
            listing.listing_url
            and candidate.listing_url
            and listing.listing_url == candidate.listing_url
        ):
            score = max(score, 1.0)
            reasons.append("Same listing URL")

        if (
            listing.lot_number
            and candidate.lot_number
            and listing.auction_house == candidate.auction_house
            and listing.lot_number == candidate.lot_number
        ):
            score = max(score, 0.95)
            reasons.append("Same auction house lot number")

        token_overlap = _safe_jaccard(
            listing_tokens,
            _tokenize(f"{candidate.item} {candidate.description}"),
        )
        if listing.category == candidate.category and token_overlap >= 0.75:
            score = max(score, 0.85)
            reasons.append("High title/description overlap in same category")

        if (
            listing.category == candidate.category
            and token_overlap >= 0.5
            and max(listing.price_cad, candidate.price_cad) > 0
        ):
            relative_price_gap = abs(listing.price_cad - candidate.price_cad) / max(
                listing.price_cad, candidate.price_cad
            )
            if relative_price_gap <= 0.1:
                score = max(score, 0.78)
                reasons.append(
                    "Moderate text overlap with very similar listed price"
                )

        if score >= min_score:
            candidates.append(
                DuplicateCandidate(
                    item=candidate.item,
                    auction_house=candidate.auction_house,
                    score=round(score, 2),
                    confidence=_confidence_from_score(score),
                    reason="; ".join(reasons),
                )
            )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)

    if not candidates:
        return DuplicateSummary(
            candidate_count=0,
            review_label="No duplicate signal",
            explanation="No strong duplicate candidates were detected.",
            candidates=[],
        )

    top_confidence = candidates[0].confidence
    if top_confidence in {"High", "Medium"}:
        label = "Review recommended"
    else:
        label = "Limited duplicate evidence"

    return DuplicateSummary(
        candidate_count=len(candidates),
        review_label=label,
        explanation=(
            f"{len(candidates)} potential duplicate(s) found. "
            "Review manually before merging or de-duplicating records."
        ),
        candidates=candidates,
    )
