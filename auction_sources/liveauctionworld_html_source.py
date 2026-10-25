import hashlib
import json
import re
import time
from html import unescape
from typing import Dict, Iterable, List
from urllib.error import URLError
from urllib.parse import urljoin
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


def _record_id_from_url_or_title(url: str, title: str) -> str:
    key = (url.strip() or title.strip()).encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:16]


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
                price_cad = _safe_float(
                    offers.get("price")
                    if isinstance(offers, dict)
                    else None
                )
                seller_name = source_name
                if isinstance(item_data.get("seller"), dict):
                    seller_name = str(
                        item_data.get("seller", {}).get("name") or source_name
                    ).strip()
                category = str(item_data.get("category") or "Other").strip() or "Other"
                description = str(item_data.get("description") or "").strip()
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
                        listing_url=listing_url,
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
        price_cad = _safe_float(bid_text)

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
                listing_url=listing_url,
                lot_number=lot_number,
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


class LiveAuctionWorldHtmlAdapter:
    def __init__(self, fetcher=fetch_html_document, sleeper=time.sleep):
        self._fetcher = fetcher
        self._sleeper = sleeper

    def _resolve_crawl_url(self, source_config: Dict[str, object]) -> str:
        base_url = str(source_config["base_url"]).strip()
        template = str(source_config.get("search_path_template") or "").strip()
        if not template:
            return base_url
        if "{query}" in template:
            template = template.replace("{query}", "antique")
        if "{page}" in template:
            template = template.replace("{page}", "1")
        return urljoin(base_url, template)

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

    def crawl_latest(self, source_config: Dict[str, object]) -> List[AuctionListing]:
        base_url = str(source_config["base_url"]).strip()
        if "liveauctionworld.com" not in base_url.lower():
            raise ValueError(
                "LiveAuctionWorld HTML adapter only supports liveauctionworld.com URLs."
            )

        crawl_url = self._resolve_crawl_url(source_config)
        user_agent = (
            str(source_config.get("user_agent") or "").strip()
            or "AuctionFinderBot/0.1"
        )
        rate_limit_seconds = max(float(source_config.get("rate_limit_seconds") or 2.0), 0.0)
        timeout_seconds = max(rate_limit_seconds * 5, 10.0)
        max_pages = max(int(source_config.get("crawl_max_pages") or 1), 1)
        source_name = str(source_config["name"])

        first_html = self._fetch_page(
            page_url=crawl_url,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            rate_limit_seconds=rate_limit_seconds,
        )

        results: List[AuctionListing] = []
        seen_ids = set()

        initial_listings = parse_liveauctionworld_html(
            html_text=first_html,
            source_name=source_name,
            base_url=base_url,
        )
        for listing in initial_listings:
            if listing.source_record_id in seen_ids:
                continue
            seen_ids.add(listing.source_record_id)
            results.append(listing)

        pagination_links = extract_liveauctionworld_pagination_links(first_html, base_url)
        pages_crawled = 1
        for page_url in pagination_links:
            if pages_crawled >= max_pages:
                break
            if page_url == crawl_url:
                continue
            page_html = self._fetch_page(
                page_url=page_url,
                user_agent=user_agent,
                timeout_seconds=timeout_seconds,
                rate_limit_seconds=rate_limit_seconds,
            )
            page_listings = parse_liveauctionworld_html(
                html_text=page_html,
                source_name=source_name,
                base_url=base_url,
            )
            for listing in page_listings:
                if listing.source_record_id in seen_ids:
                    continue
                seen_ids.add(listing.source_record_id)
                results.append(listing)
            pages_crawled += 1

        auction_links = extract_liveauctionworld_auction_links(first_html, base_url)
        for auction_url in auction_links[:max_pages]:
            if pages_crawled >= max_pages:
                break
            if auction_url == crawl_url:
                continue
            auction_html = self._fetch_page(
                page_url=auction_url,
                user_agent=user_agent,
                timeout_seconds=timeout_seconds,
                rate_limit_seconds=rate_limit_seconds,
            )
            auction_listings = parse_liveauctionworld_html(
                html_text=auction_html,
                source_name=source_name,
                base_url=base_url,
            )
            for listing in auction_listings:
                if listing.source_record_id in seen_ids:
                    continue
                seen_ids.add(listing.source_record_id)
                results.append(listing)
            pages_crawled += 1

        if not results:
            raise ValueError(
                "No listing records could be parsed from the fetched HTML."
            )
        return results
