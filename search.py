from datetime import date
from typing import List, Mapping, Optional

from models import AuctionListing
from pricing import calculate_estimated_cost


def _relevance_score(listing: AuctionListing, keyword: str) -> int:
    normalized = keyword.strip().lower()
    if not normalized:
        return 0

    item = listing.item.lower()
    description = listing.description.lower()
    return item.count(normalized) * 2 + description.count(normalized)


def search_listings(
    listings: List[AuctionListing],
    keyword: str = "",
    category: str = "All",
    status: str = "All",
    min_price_cad: Optional[float] = None,
    max_price_cad: Optional[float] = None,
    sale_date_from: Optional[date] = None,
    sale_date_to: Optional[date] = None,
    sort_by: str = "Estimated total (CAD)",
    sort_desc: bool = False,
) -> List[AuctionListing]:
    filtered: List[AuctionListing] = []
    normalized_keyword = keyword.strip().lower()

    for listing in listings:
        haystack = f"{listing.item} {listing.description}".lower()
        if normalized_keyword and normalized_keyword not in haystack:
            continue

        if category != "All" and listing.category != category:
            continue

        if status != "All" and listing.status != status:
            continue

        if min_price_cad is not None and listing.price_cad < min_price_cad:
            continue

        if max_price_cad is not None and listing.price_cad > max_price_cad:
            continue

        if sale_date_from is not None:
            if listing.sale_date is None or listing.sale_date < sale_date_from:
                continue

        if sale_date_to is not None:
            if listing.sale_date is None or listing.sale_date > sale_date_to:
                continue

        filtered.append(listing)

    if sort_by == "Price (CAD)":
        key_fn = lambda listing: listing.price_cad
    elif sort_by == "Sale date":
        key_fn = lambda listing: (
            listing.sale_date is None,
            listing.sale_date or date.max,
        )
    elif sort_by == "Relevance":
        key_fn = lambda listing: _relevance_score(listing, keyword)
        sort_desc = True
    else:
        key_fn = calculate_estimated_cost

    return sorted(filtered, key=key_fn, reverse=sort_desc)


def select_top_listings_for_internet_report(
    listings: List[AuctionListing],
    keyword: str = "",
    image_match_distances: Optional[Mapping[str, int]] = None,
    limit: int = 10,
) -> List[AuctionListing]:
    normalized_limit = max(limit, 0)
    if normalized_limit == 0 or not listings:
        return []

    image_scores = image_match_distances or {}

    def _listing_key(listing: AuctionListing) -> str:
        return listing.source_record_id or f"{listing.item}|{listing.auction_house}"

    scored = []
    for index, listing in enumerate(listings):
        score = _relevance_score(listing, keyword) * 10
        listing_key = _listing_key(listing)
        distance = image_scores.get(listing_key)
        if distance is not None:
            score += max(0, 30 - distance) * 2
        if listing.description.strip():
            score += 4
        if listing.image_url:
            score += 3
        if listing.listing_url:
            score += 2
        scored.append((score, index, listing))

    scored.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in scored[:normalized_limit]]
