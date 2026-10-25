from io import BytesIO
from typing import Dict, Iterable, List
from urllib.request import Request, urlopen

from models import AuctionListing

try:
    from PIL import Image
except ImportError:  # pragma: no cover - guarded at runtime
    Image = None


def _average_hash(image_bytes: bytes, hash_size: int = 8) -> int:
    if Image is None:
        raise RuntimeError("Pillow is required for image-based search.")

    with Image.open(BytesIO(image_bytes)) as image:
        grayscale = image.convert("L").resize((hash_size, hash_size))
        if hasattr(grayscale, "get_flattened_data"):
            pixels = list(grayscale.get_flattened_data())
        else:
            pixels = list(grayscale.getdata())

    average_value = sum(pixels) / len(pixels)
    bits = [1 if pixel >= average_value else 0 for pixel in pixels]

    hash_value = 0
    for bit in bits:
        hash_value = (hash_value << 1) | bit
    return hash_value


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _fetch_image_bytes(
    url: str,
    user_agent: str = "AuctionFinderBot/0.1",
    timeout_seconds: float = 10.0,
) -> bytes:
    request = Request(
        url=url,
        headers={"User-Agent": user_agent},
        method="GET",
    )
    with urlopen(request, timeout=max(timeout_seconds, 1.0)) as response:
        return response.read()


def find_image_matches(
    listings: Iterable[AuctionListing],
    query_image_bytes: bytes,
    max_hamming_distance: int = 12,
) -> Dict[str, int]:
    query_hash = _average_hash(query_image_bytes)
    matches: Dict[str, int] = {}

    for listing in listings:
        if not listing.image_url:
            continue

        try:
            listing_hash = _average_hash(_fetch_image_bytes(listing.image_url))
        except Exception:
            continue

        distance = _hamming_distance(query_hash, listing_hash)
        if distance <= max_hamming_distance:
            listing_key = listing.source_record_id or f"{listing.item}|{listing.auction_house}"
            matches[listing_key] = distance

    return matches


def filter_listings_by_image(
    listings: List[AuctionListing],
    query_image_bytes: bytes,
    max_hamming_distance: int = 12,
) -> tuple[List[AuctionListing], Dict[str, int]]:
    matches = find_image_matches(
        listings=listings,
        query_image_bytes=query_image_bytes,
        max_hamming_distance=max_hamming_distance,
    )

    filtered: List[AuctionListing] = []
    for listing in listings:
        listing_key = listing.source_record_id or f"{listing.item}|{listing.auction_house}"
        if listing_key in matches:
            filtered.append(listing)

    return filtered, matches
