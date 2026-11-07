import hashlib
import json
import re
import time
from html import unescape
from typing import Dict, Iterable, List
from urllib.error import URLError
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from models import AuctionListing


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _safe_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return 0.0
    return float(match.group(0))


def _status_from_text(text: str) -> str:
    normalized = text.lower()
    if "sold" in normalized or "closed" in normalized:
        return "Sold"
    if "upcoming" in normalized or "starts" in normalized:
        return "Upcoming"
    if "live now" in normalized or "livenow" in normalized:
        return "Active"
    return "Active"


def _extract_bid_fields(text: str) -> tuple[float | None, float | None]:
    current_bid_match = re.search(
        r"(?:current|winning)\s*bid[^\d-]*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    opening_bid_match = re.search(
        r"(?:opening|start(?:ing)?)\s*bid[^\d-]*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    current_bid = float(current_bid_match.group(1)) if current_bid_match else None
    opening_bid = float(opening_bid_match.group(1)) if opening_bid_match else None
    return current_bid, opening_bid


def _record_id_from_url_or_title(url: str, title: str) -> str:
    key = (url.strip() or title.strip()).encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:16]


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    cleaned = parsed._replace(fragment="")
    normalized = cleaned.geturl()
    if normalized.endswith("/") and cleaned.path not in {"", "/"}:
        normalized = normalized.rstrip("/")
    return normalized


_BLOCKED_FILE_EXTENSIONS = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".pdf",
    ".zip",
    ".xml",
}

_DEFAULT_INCLUDE_TERMS = [
    "item",
    "lot",
    "auction",
    "catalog",
    "listing",
    "product",
    "sale",
    "bid",
]

_DEFAULT_EXCLUDE_TERMS = [
    "login",
    "logout",
    "register",
    "signup",
    "account",
    "privacy",
    "terms",
    "help",
    "contact",
    "about",
    "faq",
    "wishlist",
    "cart",
    "checkout",
    "shipping",
    "returns",
    "policy",
]

_SITE_PROFILES: Dict[str, Dict[str, List[str] | int]] = {
    "liveauctionworld.com": {
        "include_terms": ["_i", "_as", "auction", "lot", "item", "search"],
        "exclude_terms": _DEFAULT_EXCLUDE_TERMS,
        "title_min_length": 8,
    },
    "hibid.com": {
        "include_terms": ["lotdetails", "auction", "lot", "item"],
        "exclude_terms": _DEFAULT_EXCLUDE_TERMS + ["auctioncalendar", "auctionmap"],
        "title_min_length": 10,
    },
    "invaluable.com": {
        "include_terms": ["auction-lot", "lot", "item", "catalog"],
        "exclude_terms": _DEFAULT_EXCLUDE_TERMS,
        "title_min_length": 10,
    },
    "proxibid.com": {
        "include_terms": ["lotinformation", "lotdetails", "lot", "auction"],
        "exclude_terms": _DEFAULT_EXCLUDE_TERMS,
        "title_min_length": 10,
    },
    "urbanauctions.ca": {
        "include_terms": ["event/lotdetails", "lotdetails", "lot", "item"],
        "exclude_terms": _DEFAULT_EXCLUDE_TERMS + ["event/details"],
        "title_min_length": 8,
    },
}


def _site_profile_for_host(hostname: str) -> Dict[str, List[str] | int]:
    lowered = hostname.lower()
    for domain, profile in _SITE_PROFILES.items():
        if lowered == domain or lowered.endswith(f".{domain}"):
            return profile
    return {
        "include_terms": _DEFAULT_INCLUDE_TERMS,
        "exclude_terms": _DEFAULT_EXCLUDE_TERMS,
        "title_min_length": 10,
    }


def _path_has_blocked_extension(path: str) -> bool:
    lowered = path.lower().split("?", 1)[0].split("#", 1)[0]
    return any(lowered.endswith(ext) for ext in _BLOCKED_FILE_EXTENSIONS)


def _looks_like_item_candidate(
    path_and_query: str,
    include_terms: List[str],
) -> bool:
    if any(term in path_and_query for term in include_terms):
        return True
    if re.search(r"(?:^|[/?&=_-])(lot|item|product|listing)\d+", path_and_query):
        return True
    if re.search(r"(?:lotdetails|lot|item)[/-]\d{3,}", path_and_query):
        return True
    return bool(re.search(r"[_-](?:i|lot|item)\d+", path_and_query))


def _looks_like_event_index_url(path_and_query: str) -> bool:
    lowered = path_and_query.lower()
    if "event/lotdetails" in lowered:
        return False
    return "event/details" in lowered


def _anchor_context_window(html_text: str, start_index: int, end_index: int) -> str:
    context_start = max(start_index - 180, 0)
    context_end = min(end_index + 180, len(html_text))
    return _clean_text(html_text[context_start:context_end])


def _extract_internal_links(
    html_text: str,
    current_url: str,
    root_host: str,
    max_links: int,
) -> List[str]:
    href_pattern = re.compile(
        r"<a[^>]+href=[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    )
    profile = _site_profile_for_host(root_host)
    include_terms = list(profile.get("include_terms") or _DEFAULT_INCLUDE_TERMS)
    exclude_terms = list(profile.get("exclude_terms") or _DEFAULT_EXCLUDE_TERMS)

    links_with_score: List[tuple[int, str]] = []
    seen = set()
    for href in href_pattern.findall(html_text):
        href_value = href.strip()
        if not href_value:
            continue
        if href_value.startswith("#"):
            continue
        lowered = href_value.lower()
        if lowered.startswith("javascript:") or lowered.startswith("mailto:"):
            continue

        absolute = _normalize_url(urljoin(current_url, href_value))
        if not absolute:
            continue
        parsed = urlparse(absolute)
        if (parsed.hostname or "").lower() != root_host:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)

        path_and_query = f"{parsed.path} {parsed.query}".lower()
        if _path_has_blocked_extension(parsed.path):
            continue
        if any(term in path_and_query for term in exclude_terms):
            continue

        has_page_marker = bool(re.search(r"[_?&]p\d+|page=\d+", path_and_query))
        is_item_candidate = _looks_like_item_candidate(path_and_query, include_terms)
        if not has_page_marker and not is_item_candidate:
            continue
        if is_item_candidate and _looks_like_event_index_url(path_and_query):
            continue

        score = 0
        if has_page_marker:
            score += 6
        if is_item_candidate:
            score += 3
        if "lotdetails" in path_and_query:
            score += 6
        if _looks_like_event_index_url(path_and_query):
            score -= 4
        if parsed.query:
            score += 1
        if re.search(r"\d{4,}", path_and_query):
            score += 2

        links_with_score.append((score, absolute))

    links_with_score.sort(key=lambda pair: (-pair[0], pair[1]))
    ranked_links = [url for _, url in links_with_score]
    return ranked_links[: max(max_links, 1)]


def _extract_generic_anchor_items(
    html_text: str,
    source_name: str,
    base_url: str,
    root_host: str,
) -> List[AuctionListing]:
    anchor_pattern = re.compile(
        r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    profile = _site_profile_for_host(root_host)
    include_terms = list(profile.get("include_terms") or _DEFAULT_INCLUDE_TERMS)
    exclude_terms = list(profile.get("exclude_terms") or _DEFAULT_EXCLUDE_TERMS)
    title_min_length = int(profile.get("title_min_length") or 10)

    skip_titles = {
        "home",
        "about",
        "contact",
        "login",
        "register",
        "next",
        "previous",
        "privacy",
        "terms",
        "help",
    }
    results: List[AuctionListing] = []
    seen_record_ids = set()
    for match in anchor_pattern.finditer(html_text):
        href = match.group(1).strip()
        title = _clean_text(match.group(2))
        if not href or len(title) < title_min_length:
            continue
        if title.lower() in skip_titles:
            continue

        listing_url = _normalize_url(urljoin(base_url, href))
        if not listing_url:
            continue
        listing_parsed = urlparse(listing_url)
        if (listing_parsed.hostname or "").lower() != root_host:
            continue

        path_and_query = f"{listing_parsed.path} {listing_parsed.query}".lower()
        if _path_has_blocked_extension(listing_parsed.path):
            continue
        if any(term in path_and_query for term in exclude_terms):
            continue

        context_text = _anchor_context_window(html_text, match.start(), match.end())
        has_item_path = _looks_like_item_candidate(path_and_query, include_terms)
        if has_item_path and _looks_like_event_index_url(path_and_query):
            continue
        has_item_context = bool(
            re.search(r"\b(lot|item|bid|estimate|auction|sold|current bid|opening bid)\b", context_text.lower())
        )
        has_price = bool(re.search(r"(?:\$|cad|usd|eur|gbp)\s*\d", context_text.lower()))
        if not has_item_path and not has_item_context and not has_price:
            continue

        source_record_id = _record_id_from_url_or_title(listing_url, title)
        if source_record_id in seen_record_ids:
            continue
        seen_record_ids.add(source_record_id)

        price_cad = _safe_float(context_text)
        status = _status_from_text(context_text)

        results.append(
            AuctionListing(
                item=title,
                category="Web listing",
                auction_house=source_name,
                status=status,
                price_cad=max(price_cad, 0.0),
                buyer_premium_percent=0.0,
                shipping_cad=0.0,
                description=context_text,
                listing_url=listing_url,
                source_name=source_name,
                source_record_id=source_record_id,
            )
        )
    return results


def _filter_listings_by_keyword(
    listings: List[AuctionListing],
    keyword: str,
) -> List[AuctionListing]:
    normalized = keyword.strip().lower()
    if not normalized:
        return listings
    return [
        listing
        for listing in listings
        if normalized in f"{listing.item} {listing.description}".lower()
    ]


def _iter_json_blocks(data: object) -> Iterable[Dict[str, object]]:
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _iter_json_blocks(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_json_blocks(item)


def _extract_from_json_ld(
    html_text: str,
    source_name: str,
    base_url: str,
) -> List[AuctionListing]:
    pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    results: List[AuctionListing] = []
    seen_record_ids = set()
    for match in pattern.finditer(html_text):
        payload = _clean_text(match.group(1))
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue

        for block in _iter_json_blocks(parsed):
            if "itemListElement" not in block:
                continue
            elements = block.get("itemListElement")
            if not isinstance(elements, list):
                continue
            for element in elements:
                if not isinstance(element, dict):
                    continue
                item_data = element.get("item", element)
                if not isinstance(item_data, dict):
                    continue
                title = str(item_data.get("name") or "").strip()
                raw_url = str(item_data.get("url") or "").strip()
                if not title or not raw_url:
                    continue
                listing_url = urljoin(base_url, raw_url)
                offers = item_data.get("offers", {})
                current_bid_cad = 0.0
                opening_bid_cad = 0.0
                if isinstance(offers, dict):
                    current_bid_cad = _safe_float(offers.get("price"))
                    opening_bid_cad = _safe_float(
                        offers.get("lowPrice") or offers.get("priceSpecification")
                    )
                price_cad = current_bid_cad or opening_bid_cad
                seller_name = source_name
                if isinstance(item_data.get("seller"), dict):
                    seller_name = str(
                        item_data.get("seller", {}).get("name") or source_name
                    ).strip()
                category = str(item_data.get("category") or "Other").strip() or "Other"
                description = str(item_data.get("description") or "").strip()
                image_value = item_data.get("image")
                image_url = None
                if isinstance(image_value, list) and image_value:
                    image_url = urljoin(base_url, str(image_value[0]))
                elif isinstance(image_value, str) and image_value.strip():
                    image_url = urljoin(base_url, image_value.strip())
                status = _status_from_text(
                    f"{item_data.get('availability', '')} {description}"
                )
                source_record_id = _record_id_from_url_or_title(listing_url, title)
                if source_record_id in seen_record_ids:
                    continue
                seen_record_ids.add(source_record_id)
                results.append(
                    AuctionListing(
                        item=title,
                        category=category,
                        auction_house=seller_name or source_name,
                        status=status,
                        price_cad=max(price_cad, 0.0),
                        buyer_premium_percent=0.0,
                        shipping_cad=0.0,
                        description=description,
                        image_url=image_url,
                        listing_url=listing_url,
                        opening_bid_cad=(opening_bid_cad if opening_bid_cad > 0 else None),
                        current_bid_cad=(current_bid_cad if current_bid_cad > 0 else None),
                        source_name=source_name,
                        source_record_id=source_record_id,
                    )
                )
    return results


def _extract_auction_cards(
    html_text: str,
    source_name: str,
    base_url: str,
) -> List[AuctionListing]:
    pattern = re.compile(
        r"<div class='auction'>(.*?)(?=<div class='auction'>|$)",
        re.IGNORECASE | re.DOTALL,
    )
    results: List[AuctionListing] = []
    seen_record_ids = set()
    for block in pattern.findall(html_text):
        url_match = re.search(
            r"<a class='row_thumbnail' href='([^']+)'[^>]*>",
            block,
            re.IGNORECASE,
        )
        title_match = re.search(
            r"<span class='title'>(.*?)</span>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if not url_match or not title_match:
            continue
        listing_url = urljoin(base_url, url_match.group(1).strip())
        title = _clean_text(title_match.group(1))
        if not title:
            continue
        auctioneer = source_name
        auctioneer_match = re.search(
            r"<div class='auctioneer'>(.*?)</div>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if auctioneer_match:
            auctioneer = _clean_text(auctioneer_match.group(1)) or source_name

        location_text = ""
        location_match = re.search(
            r"<div class='location'>(.*?)</div>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if location_match:
            location_text = _clean_text(location_match.group(1))

        links_text_match = re.search(
            r"<ul class='links'>(.*?)</ul>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        status = "Active"
        if links_text_match:
            status = _status_from_text(_clean_text(links_text_match.group(1)))

        source_record_id = _record_id_from_url_or_title(listing_url, title)
        if source_record_id in seen_record_ids:
            continue
        seen_record_ids.add(source_record_id)
        results.append(
            AuctionListing(
                item=title,
                category="Auction event",
                auction_house=auctioneer,
                status=status,
                price_cad=0.0,
                buyer_premium_percent=0.0,
                shipping_cad=0.0,
                description="Auction event listing",
                location=location_text or None,
                listing_url=listing_url,
                source_name=source_name,
                source_record_id=source_record_id,
            )
        )
    return results


def _extract_grid_lots(
    html_text: str,
    source_name: str,
    base_url: str,
) -> List[AuctionListing]:
    pattern = re.compile(
        r"<div class='gridItem' id='([^']+)'>(.*?)(?=<div class='gridItem' id='|</div>\s*</div>\s*</span>|$)",
        re.IGNORECASE | re.DOTALL,
    )
    results: List[AuctionListing] = []
    seen_record_ids = set()
    for item_id, block in pattern.findall(html_text):
        title_link_match = re.search(
            r"<span class='gridView_heading'>.*?<a href='([^']+)'[^>]*>.*?<span class='gridView_title'>(.*?)</span>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if not title_link_match:
            continue
        listing_url = urljoin(base_url, title_link_match.group(1).strip())
        raw_title = _clean_text(title_link_match.group(2))
        title = re.sub(r"^\d+\s*-\s*", "", raw_title).strip()
        if not title:
            continue

        auctioneer = source_name
        auctioneer_match = re.search(
            r"<div class='auctioneer'>(.*?)</div>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if auctioneer_match:
            auctioneer = _clean_text(auctioneer_match.group(1)) or source_name

        description = ""
        description_match = re.search(
            r"<div class='description[^']*'>(.*?)</div>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if description_match:
            description = _clean_text(description_match.group(1))

        bid_match = re.search(
            r"<div class='gridView_winningbid'>(.*?)</div>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        bid_text = _clean_text(bid_match.group(1)) if bid_match else ""
        current_bid_cad = _safe_float(bid_text)

        opening_bid_match = re.search(
            r"<div class='gridView_openingbid'>(.*?)</div>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        opening_bid_text = (
            _clean_text(opening_bid_match.group(1))
            if opening_bid_match
            else ""
        )
        opening_bid_cad = _safe_float(opening_bid_text)

        if not opening_bid_text and not bid_text:
            text_current_bid, text_opening_bid = _extract_bid_fields(
                _clean_text(block)
            )
            if text_current_bid is not None:
                current_bid_cad = max(text_current_bid, 0.0)
            if text_opening_bid is not None:
                opening_bid_cad = max(text_opening_bid, 0.0)

        price_cad = current_bid_cad or opening_bid_cad

        image_url = None
        image_match = re.search(
            r"<img[^>]+src='([^']+)'",
            block,
            re.IGNORECASE,
        )
        if image_match:
            image_url = urljoin(base_url, image_match.group(1).strip())

        status_text = f"{bid_text} {description}"
        status = _status_from_text(status_text)
        if "sold" not in status_text.lower() and price_cad > 0:
            status = "Active"

        lot_number = None
        lot_match = re.search(
            r"<i class='gridView_lotnum'>(.*?)</i>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if lot_match:
            lot_number = _clean_text(lot_match.group(1)).replace("-", "").strip() or None

        source_record_id = item_id.replace("i", "").strip() or _record_id_from_url_or_title(
            listing_url, title
        )
        if source_record_id in seen_record_ids:
            continue
        seen_record_ids.add(source_record_id)
        results.append(
            AuctionListing(
                item=title,
                category="Auction lot",
                auction_house=auctioneer,
                status=status,
                price_cad=max(price_cad, 0.0),
                buyer_premium_percent=0.0,
                shipping_cad=0.0,
                description=description,
                image_url=image_url,
                listing_url=listing_url,
                lot_number=lot_number,
                opening_bid_cad=(opening_bid_cad if opening_bid_cad > 0 else None),
                current_bid_cad=(current_bid_cad if current_bid_cad > 0 else None),
                source_name=source_name,
                source_record_id=source_record_id,
            )
        )
    return results


def _extract_item_detail_page(
    html_text: str,
    source_name: str,
    base_url: str,
) -> List[AuctionListing]:
    canonical_match = re.search(
        r"<link rel=[\"']canonical[\"'] href=[\"']([^\"']+_i\d+)[\"']",
        html_text,
        re.IGNORECASE,
    )
    if not canonical_match:
        canonical_match = re.search(
            r"Contents of\s+(https?://[^\s]+_i\d+)",
            html_text,
            re.IGNORECASE,
        )
    if not canonical_match:
        return []

    listing_url = canonical_match.group(1).strip()
    title = ""
    auction_house = source_name
    meta_description_match = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )
    if meta_description_match:
        description_content = _clean_text(meta_description_match.group(1))
        if " - " in description_content:
            title_part, auction_part = description_content.rsplit(" - ", 1)
            title = title_part.strip()
            if auction_part.strip():
                auction_house = auction_part.strip()
        else:
            title = description_content

    if not title:
        title_match = re.search(
            r"<title>\s*(.*?)\s*</title>",
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if title_match:
            title = _clean_text(title_match.group(1))

    if not title:
        return []

    category = "Auction lot"
    category_match = re.search(
        r'\$\("#lblCategory"\)\.text\("([^"]+)"\)',
        html_text,
        re.IGNORECASE,
    )
    if category_match:
        category = _clean_text(category_match.group(1)) or category

    keywords_match = re.search(
        r'<meta[^>]*name=["\']keywords["\'][^>]*content=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )
    location = None
    if keywords_match:
        keyword_parts = [
            _clean_text(part)
            for part in keywords_match.group(1).split(",")
        ]
        if len(keyword_parts) >= 4:
            location = ", ".join(
                part for part in keyword_parts[2:5] if part
            ) or None

    source_record_id_match = re.search(r"_i(\d+)", listing_url, re.IGNORECASE)
    source_record_id = (
        source_record_id_match.group(1)
        if source_record_id_match
        else _record_id_from_url_or_title(listing_url, title)
    )
    return [
        AuctionListing(
            item=title,
            category=category,
            auction_house=auction_house,
            status="Active",
            price_cad=0.0,
            buyer_premium_percent=0.0,
            shipping_cad=0.0,
            description=title,
            location=location,
            image_url=(
                urljoin(base_url, _clean_text(image_match.group(1)).strip())
                if (
                    image_match := re.search(
                        r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
                        html_text,
                        re.IGNORECASE,
                    )
                )
                else None
            ),
            listing_url=urljoin(base_url, listing_url),
            source_name=source_name,
            source_record_id=source_record_id,
        )
    ]


def parse_liveauctionworld_html(
    html_text: str,
    source_name: str,
    base_url: str,
) -> List[AuctionListing]:
    from_json_ld = _extract_from_json_ld(html_text, source_name, base_url)
    if from_json_ld:
        return from_json_ld

    from_grid = _extract_grid_lots(html_text, source_name, base_url)
    if from_grid:
        return from_grid

    from_item_detail = _extract_item_detail_page(html_text, source_name, base_url)
    if from_item_detail:
        return from_item_detail

    return _extract_auction_cards(html_text, source_name, base_url)


def extract_liveauctionworld_pagination_links(
    html_text: str,
    base_url: str,
) -> List[str]:
    pages_match = re.search(
        r"<span class='pagingbar_pages'>(.*?)</span>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not pages_match:
        return []
    page_links = re.findall(
        r"<a href='([^']+)'[^>]*>",
        pages_match.group(1),
        re.IGNORECASE,
    )
    absolute_links: List[str] = []
    for link in page_links:
        absolute = urljoin(base_url, link.strip())
        if absolute not in absolute_links:
            absolute_links.append(absolute)
    return absolute_links


def extract_liveauctionworld_auction_links(
    html_text: str,
    base_url: str,
) -> List[str]:
    card_links = re.findall(
        r"<a class='row_thumbnail' href='([^']+_as\d+[^']*)'",
        html_text,
        re.IGNORECASE,
    )
    links: List[str] = []
    for link in card_links:
        absolute = urljoin(base_url, link.strip())
        if absolute not in links:
            links.append(absolute)
    return links


def fetch_html_document(
    url: str,
    user_agent: str,
    timeout_seconds: float = 20.0,
) -> str:
    timeout = max(timeout_seconds, 1.0)
    request = Request(
        url=url,
        headers={"User-Agent": user_agent},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        content = response.read()
    return content.decode("utf-8", errors="replace")


def fetch_json_document(
    url: str,
    user_agent: str,
    timeout_seconds: float = 20.0,
) -> Dict[str, object]:
    timeout = max(timeout_seconds, 1.0)
    request = Request(
        url=url,
        headers={"User-Agent": user_agent},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        content = response.read()
    decoded = content.decode("utf-8", errors="replace")
    return json.loads(decoded)


class LiveAuctionWorldHtmlAdapter:
    def __init__(
        self,
        fetcher=fetch_html_document,
        json_fetcher=fetch_json_document,
        sleeper=time.sleep,
    ):
        self._fetcher = fetcher
        self._json_fetcher = json_fetcher
        self._sleeper = sleeper

    def _resolve_crawl_url(
        self,
        source_config: Dict[str, object],
        keyword: str | None = None,
    ) -> str:
        base_url = str(source_config["base_url"]).strip()
        template = str(source_config.get("search_path_template") or "").strip()
        if not template:
            if keyword:
                query = quote_plus(keyword)
                connector = "&" if "?" in base_url else "?"
                return f"{base_url}{connector}txtSearch={query}"
            return base_url
        if "{query}" in template:
            template = template.replace("{query}", quote_plus(keyword or "antique"))
        if "{page}" in template:
            template = template.replace("{page}", "1")
        if keyword and "{query}" not in str(source_config.get("search_path_template") or ""):
            connector = "&" if "?" in template else "?"
            template = f"{template}{connector}txtSearch={quote_plus(keyword)}"
        return urljoin(base_url, template)

    def _crawl_from_url(
        self,
        source_config: Dict[str, object],
        crawl_url: str,
        keyword: str | None = None,
    ) -> List[AuctionListing]:
        base_url = str(source_config["base_url"]).strip()
        normalized_start_url = _normalize_url(crawl_url)
        if not normalized_start_url:
            raise ValueError("A valid http/https URL is required for crawl.")

        start_parsed = urlparse(normalized_start_url)
        root_host = (start_parsed.hostname or "").lower()
        if not root_host:
            raise ValueError("Crawl URL must include a valid hostname.")

        user_agent = (
            str(source_config.get("user_agent") or "").strip()
            or "AuctionFinderBot/0.1"
        )
        rate_limit_seconds = max(float(source_config.get("rate_limit_seconds") or 2.0), 0.0)
        timeout_seconds = max(rate_limit_seconds * 5, 10.0)
        max_pages = max(int(source_config.get("crawl_max_pages") or 1), 1)
        source_name = str(source_config["name"])

        results: List[AuctionListing] = []
        seen_ids = set()

        queue: List[str] = [normalized_start_url]
        queued_urls = {normalized_start_url}
        crawled_urls = set()

        pages_crawled = 0
        while queue and pages_crawled < max_pages:
            page_url = queue.pop(0)
            if page_url in crawled_urls:
                continue

            page_html = self._fetch_page(
                page_url=page_url,
                user_agent=user_agent,
                timeout_seconds=timeout_seconds,
                rate_limit_seconds=rate_limit_seconds,
            )
            crawled_urls.add(page_url)
            pages_crawled += 1

            page_listings = parse_liveauctionworld_html(
                html_text=page_html,
                source_name=source_name,
                base_url=page_url,
            )
            if not page_listings:
                page_listings = _extract_generic_anchor_items(
                    html_text=page_html,
                    source_name=source_name,
                    base_url=page_url,
                    root_host=root_host,
                )

            for listing in page_listings:
                if listing.source_record_id in seen_ids:
                    continue
                seen_ids.add(listing.source_record_id)
                results.append(listing)

            candidate_links: List[str] = []
            candidate_links.extend(
                extract_liveauctionworld_pagination_links(page_html, page_url)
            )
            candidate_links.extend(
                extract_liveauctionworld_auction_links(page_html, page_url)
            )
            candidate_links.extend(
                _extract_internal_links(
                    html_text=page_html,
                    current_url=page_url,
                    root_host=root_host,
                    max_links=max_pages * 8,
                )
            )

            for candidate in candidate_links:
                normalized_candidate = _normalize_url(candidate)
                if not normalized_candidate:
                    continue
                if normalized_candidate in queued_urls:
                    continue
                if normalized_candidate in crawled_urls:
                    continue
                candidate_host = (urlparse(normalized_candidate).hostname or "").lower()
                if candidate_host != root_host:
                    continue
                queued_urls.add(normalized_candidate)
                queue.append(normalized_candidate)

        if keyword:
            results = _filter_listings_by_keyword(results, keyword)
            if not results:
                raise ValueError(
                    "URL crawl completed but found no items matching the keyword filter."
                )

        if not results:
            raise ValueError(
                "No listing records could be parsed from the fetched HTML pages."
            )
        return results

    def _fetch_with_retry(
        self,
        crawl_url: str,
        user_agent: str,
        timeout_seconds: float,
        retries: int,
        rate_limit_seconds: float,
    ) -> str:
        attempts = max(retries, 1)
        backoff_seconds = max(rate_limit_seconds, 0.5)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._fetcher(
                    url=crawl_url,
                    user_agent=user_agent,
                    timeout_seconds=timeout_seconds,
                )
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                self._sleeper(backoff_seconds * attempt)

        if last_error is None:
            raise ValueError("HTML fetch failed without a captured exception.")
        raise ValueError(
            f"Failed to fetch LiveAuctionWorld HTML after {attempts} attempt(s): {last_error}"
        ) from last_error

    def _fetch_page(
        self,
        page_url: str,
        user_agent: str,
        timeout_seconds: float,
        rate_limit_seconds: float,
    ) -> str:
        html_text = self._fetch_with_retry(
            crawl_url=page_url,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            retries=3,
            rate_limit_seconds=rate_limit_seconds,
        )
        if rate_limit_seconds > 0:
            self._sleeper(rate_limit_seconds)
        return html_text

    def crawl_latest(
        self,
        source_config: Dict[str, object],
        keyword: str | None = None,
    ) -> List[AuctionListing]:
        crawl_url = self._resolve_crawl_url(source_config, keyword=keyword)
        return self._crawl_from_url(
            source_config=source_config,
            crawl_url=crawl_url,
            keyword=keyword,
        )

    def crawl_url(
        self,
        source_config: Dict[str, object],
        auction_url: str,
        keyword: str | None = None,
    ) -> List[AuctionListing]:
        normalized_url = auction_url.strip()
        if not normalized_url:
            raise ValueError("Auction URL is required for URL crawl.")
        return self._crawl_from_url(
            source_config=source_config,
            crawl_url=normalized_url,
            keyword=keyword,
        )

    def crawl_keyword(
        self,
        source_config: Dict[str, object],
        keyword: str,
    ) -> List[AuctionListing]:
        normalized_keyword = keyword.strip().lower()
        if not normalized_keyword:
            raise ValueError("Keyword is required for keyword crawl.")
        base_url = str(source_config["base_url"]).strip()
        base_host = (urlparse(base_url).hostname or "").lower()
        if "liveauctionworld.com" not in base_host:
            # Generic sites use URL crawl plus keyword filtering instead of
            # the LiveAuctionWorld-specific JSON endpoint.
            return self._crawl_from_url(
                source_config=source_config,
                crawl_url=base_url,
                keyword=keyword,
            )

        user_agent = (
            str(source_config.get("user_agent") or "").strip()
            or "AuctionFinderBot/0.1"
        )
        rate_limit_seconds = max(float(source_config.get("rate_limit_seconds") or 2.0), 0.0)
        timeout_seconds = max(rate_limit_seconds * 5, 10.0)
        max_pages = max(int(source_config.get("crawl_max_pages") or 1), 1)
        source_name = str(source_config["name"])
        base_query = parse_qs(urlparse(base_url).query)
        configured_site_id = str(source_config.get("site_id") or "").strip()
        query_site_id = configured_site_id or (
            (base_query.get("siteID") or base_query.get("siteId") or [""])[0].strip()
        )

        all_results: List[AuctionListing] = []
        seen_ids = set()
        for page_number in range(1, max_pages + 1):
            query_params = {
                "command": "searchitems",
                "unitsPerPage": 100,
                "page": page_number,
                "isCurrent": 1,
                "keywords": keyword,
                "categoryID": "",
                "auctionSessionTypeID": "",
                "countryLocationID": "",
                "auctioneerID": "",
                "yearID": "",
                "registrantID": "",
                "exactKeywords": 0,
                "sortBy": 4,
                "searchFields": 0,
                "hasImage": 0,
            }
            if query_site_id:
                query_params["siteID"] = query_site_id
            query_string = urlencode(query_params)
            endpoint = urljoin(
                base_url,
                f"handlers/controls/CloudsearchItemSearch.ashx?{query_string}",
            )
            payload = self._json_fetcher(endpoint, user_agent, timeout_seconds)
            item_results = payload.get("ItemResults")
            if not isinstance(item_results, list):
                raise ValueError("Keyword search endpoint returned an invalid payload.")
            if not item_results:
                if page_number == 1:
                    break
                continue

            for row in item_results:
                if not isinstance(row, dict):
                    continue
                item_id = row.get("ItemID")
                item_title = str(row.get("ItemTitle") or "").strip()
                if not item_id or not item_title:
                    continue
                source_record_id = str(item_id)
                if source_record_id in seen_ids:
                    continue
                seen_ids.add(source_record_id)

                category = "Auction lot"
                category_values = row.get("ItemCategoryName")
                if isinstance(category_values, list) and category_values:
                    category = str(category_values[0] or "").strip() or category
                elif row.get("ItemCategoryName"):
                    category = str(row.get("ItemCategoryName")).strip() or category

                location_parts = [
                    str(row.get("AuctionCity") or "").strip(),
                    str(row.get("AuctionProvince") or "").strip(),
                    str(row.get("AuctionCountry") or "").strip(),
                ]
                location = ", ".join([part for part in location_parts if part]) or None

                lot_number = str(row.get("ItemLot") or "").strip() or None
                listing_url = urljoin(base_url, f"item.aspx?i={item_id}")
                current_bid_cad = _safe_float(row.get("ItemCurrentBidAmount"))
                opening_bid_cad = _safe_float(
                    row.get("ItemOpeningBidAmount")
                    or row.get("ItemOpeningBid")
                    or row.get("ItemStartingBid")
                )
                price_cad = current_bid_cad or opening_bid_cad
                status = "Sold" if int(row.get("ItemSold") or 0) == 1 else "Active"
                image_raw = (
                    row.get("ItemImage")
                    or row.get("ItemImageURL")
                    or row.get("ImageURL")
                )
                image_url = (
                    urljoin(base_url, str(image_raw).strip())
                    if image_raw
                    else None
                )

                listing = AuctionListing(
                    item=item_title,
                    category=category,
                    auction_house=str(row.get("AuctioneerName") or source_name).strip() or source_name,
                    status=status,
                    price_cad=max(price_cad, 0.0),
                    buyer_premium_percent=0.0,
                    shipping_cad=0.0,
                    description=str(row.get("ItemDescription") or "").strip(),
                    location=location,
                    image_url=image_url,
                    listing_url=listing_url,
                    lot_number=lot_number,
                    opening_bid_cad=(opening_bid_cad if opening_bid_cad > 0 else None),
                    current_bid_cad=(current_bid_cad if current_bid_cad > 0 else None),
                    source_name=source_name,
                    source_record_id=source_record_id,
                )
                all_results.append(listing)

            if rate_limit_seconds > 0:
                self._sleeper(rate_limit_seconds)

        matches = [
            listing
            for listing in all_results
            if normalized_keyword in f"{listing.item} {listing.description}".lower()
        ]
        if matches:
            return matches

        raise ValueError(
            "Search crawl produced no keyword matches. "
            "Try increasing max pages or using a broader term."
        )
