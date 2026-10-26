import re
from dataclasses import dataclass
from statistics import mean
from typing import Callable, Dict, List, Optional
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from models import AuctionListing


@dataclass(frozen=True)
class InternetComparableHit:
    title: str
    url: str
    source: str
    raw_price_text: str
    detected_currency: str
    detected_amount: float
    price_cad: float
    snippet: str
    query: str


@dataclass(frozen=True)
class InternetPriceSummary:
    comparable_count: int
    lowest_price_cad: Optional[float]
    highest_price_cad: Optional[float]
    average_price_cad: Optional[float]
    error_message: Optional[str]
    hits: List[InternetComparableHit]


_CURRENCY_TO_CAD: Dict[str, float] = {
    "CAD": 1.0,
    "USD": 1.36,
    "EUR": 1.49,
    "GBP": 1.73,
}

_PRICE_PATTERN = re.compile(
    r"(?P<prefix>C\$|CAD\s*\$|US\$|USD\s*\$|\$|€|£)\s*(?P<amount>\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def _fetch_html(
    url: str,
    user_agent: str = "AuctionFinderBot/0.1",
    timeout_seconds: float = 20.0,
) -> str:
    request = Request(
        url=url,
        headers={"User-Agent": user_agent},
        method="GET",
    )
    with urlopen(request, timeout=max(timeout_seconds, 1.0)) as response:
        content = response.read()
    return content.decode("utf-8", errors="replace")


def _normalize_currency(prefix: str) -> str:
    normalized = prefix.strip().upper().replace(" ", "")
    if normalized in {"C$", "CAD$"}:
        return "CAD"
    if normalized in {"US$", "USD$"}:
        return "USD"
    if normalized == "€":
        return "EUR"
    if normalized == "£":
        return "GBP"
    return "CAD"


def _extract_price_candidates(text: str) -> List[tuple[str, float, str]]:
    candidates: List[tuple[str, float, str]] = []
    for match in _PRICE_PATTERN.finditer(text):
        amount_text = match.group("amount").replace(",", "")
        try:
            amount = float(amount_text)
        except ValueError:
            continue
        currency = _normalize_currency(match.group("prefix"))
        candidates.append((match.group(0).strip(), amount, currency))
    return candidates


def _to_cad(amount: float, currency: str) -> Optional[float]:
    rate = _CURRENCY_TO_CAD.get(currency.upper())
    if rate is None:
        return None
    return round(amount * rate, 2)


def _build_queries(listing: AuctionListing) -> List[str]:
    queries = [listing.item.strip()]
    description_words = re.findall(r"[a-zA-Z0-9]+", listing.description or "")
    if description_words:
        detail = " ".join(description_words[:8]).strip()
        if detail:
            queries.append(f"{listing.item} {detail}")
    if listing.lot_number:
        queries.append(f"{listing.item} lot {listing.lot_number}")
    return [query for query in queries if query]


def _extract_results_from_ddg_html(html_text: str) -> List[tuple[str, str, str]]:
    anchor_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*>.*?</a>.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    snippets = [re.sub(r"<[^>]+>", " ", snippet).strip() for snippet in snippet_pattern.findall(html_text)]
    results: List[tuple[str, str, str]] = []
    for index, match in enumerate(anchor_pattern.finditer(html_text)):
        title = re.sub(r"<[^>]+>", " ", match.group("title")).strip()
        url = match.group("url").strip()
        snippet = snippets[index] if index < len(snippets) else ""
        if not title or not url:
            continue
        results.append((title, url, snippet))
    return results


def analyze_listing_internet_prices(
    listing: AuctionListing,
    max_results: int = 10,
    fetcher: Callable[[str], str] = _fetch_html,
) -> InternetPriceSummary:
    normalized_max = max(max_results, 1)
    hits: List[InternetComparableHit] = []
    errors: List[str] = []
    seen = set()

    for query in _build_queries(listing):
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            html_text = fetcher(search_url)
        except Exception as exc:
            errors.append(f"{query}: {exc}")
            continue

        for title, url, snippet in _extract_results_from_ddg_html(html_text):
            if len(hits) >= normalized_max:
                break

            combined_text = f"{title} {snippet}"
            price_candidates = _extract_price_candidates(combined_text)
            if not price_candidates:
                continue

            raw_price_text, amount, currency = price_candidates[0]
            price_cad = _to_cad(amount, currency)
            if price_cad is None:
                continue

            dedupe_key = f"{url}|{raw_price_text}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            source_match = re.search(r"https?://([^/]+)", url, re.IGNORECASE)
            source = source_match.group(1).lower() if source_match else "unknown"
            hits.append(
                InternetComparableHit(
                    title=title,
                    url=url,
                    source=source,
                    raw_price_text=raw_price_text,
                    detected_currency=currency,
                    detected_amount=round(amount, 2),
                    price_cad=price_cad,
                    snippet=snippet,
                    query=query,
                )
            )

        if len(hits) >= normalized_max:
            break

    if not hits:
        error_message = (
            "No internet comparable prices were extracted from search results."
        )
        if errors:
            error_message = (
                f"{error_message} Search errors: {'; '.join(errors[:3])}"
            )
        return InternetPriceSummary(
            comparable_count=0,
            lowest_price_cad=None,
            highest_price_cad=None,
            average_price_cad=None,
            error_message=error_message,
            hits=[],
        )

    cad_prices = [hit.price_cad for hit in hits]
    return InternetPriceSummary(
        comparable_count=len(hits),
        lowest_price_cad=round(min(cad_prices), 2),
        highest_price_cad=round(max(cad_prices), 2),
        average_price_cad=round(float(mean(cad_prices)), 2),
        error_message=None,
        hits=hits,
    )
