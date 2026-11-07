import unittest
from pathlib import Path
from urllib.error import URLError

from auction_sources.liveauctionworld_html_source import (
    LiveAuctionWorldHtmlAdapter,
    extract_liveauctionworld_pagination_links,
    parse_liveauctionworld_html,
)


class LiveAuctionWorldParserTests(unittest.TestCase):
    def _load_fixture(self, file_name: str) -> str:
        fixture_path = (
            Path(__file__).resolve().parent / "fixtures" / file_name
        )
        return fixture_path.read_text(encoding="utf-8")

    def test_parse_uses_json_ld_when_available(self):
        html_text = self._load_fixture("liveauctionworld_snapshot_jsonld.html")
        listings = parse_liveauctionworld_html(
            html_text=html_text,
            source_name="LiveAuctionWorld",
            base_url="https://www.liveauctionworld.com/",
        )

        self.assertEqual(len(listings), 2)
        listing = listings[0]
        self.assertEqual(listing.item, "Antique silver bowl")
        self.assertEqual(listing.category, "Silver")
        self.assertEqual(listing.price_cad, 340.0)
        self.assertEqual(listing.auction_house, "House A")
        self.assertIn("/item/777-silver-bowl", listing.listing_url or "")
        self.assertEqual(listings[1].status, "Sold")

    def test_parse_falls_back_to_anchor_links(self):
        html_text = self._load_fixture("liveauctionworld_snapshot_links.html")
        listings = parse_liveauctionworld_html(
            html_text=html_text,
            source_name="LiveAuctionWorld",
            base_url="https://www.liveauctionworld.com/",
        )

        self.assertEqual(len(listings), 2)
        listing = listings[0]
        self.assertEqual(listing.item, "Fall Antique Sale (Session 1)")
        self.assertEqual(listing.price_cad, 0.0)
        self.assertEqual(listing.status, "Active")
        self.assertEqual(listings[1].status, "Upcoming")

    def test_adapter_supports_non_liveauctionworld_domain(self):
        html_text = self._load_fixture("liveauctionworld_snapshot_jsonld.html")
        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: html_text,
            sleeper=lambda _: None,
        )
        listings = adapter.crawl_latest(
            {
                "id": 1,
                "name": "Other",
                "base_url": "https://example.com",
                "source_type": "html",
                "rate_limit_seconds": 0.1,
                "user_agent": "AuctionFinderBot/0.1",
            }
        )
        self.assertGreaterEqual(len(listings), 1)

    def test_adapter_retries_transient_fetch_errors(self):
        attempts = {"count": 0}

        def flaky_fetcher(url: str, user_agent: str, timeout_seconds: float) -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise URLError("temporary connectivity issue")
            return self._load_fixture("liveauctionworld_auction_detail_page1.html")

        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=flaky_fetcher,
            sleeper=lambda _: None,
        )
        listings = adapter.crawl_latest(
            {
                "id": 1,
                "name": "LiveAuctionWorld",
                "base_url": "https://www.liveauctionworld.com/",
                "source_type": "html",
                "rate_limit_seconds": 0.1,
                "user_agent": "AuctionFinderBot/0.1",
            }
        )
        self.assertEqual(attempts["count"], 3)
        self.assertGreaterEqual(len(listings), 1)

    def test_adapter_returns_partial_error_for_empty_parse(self):
        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: "<html></html>",
            sleeper=lambda _: None,
        )
        with self.assertRaises(ValueError):
            adapter.crawl_latest(
                {
                    "id": 1,
                    "name": "LiveAuctionWorld",
                    "base_url": "https://www.liveauctionworld.com/",
                    "source_type": "html",
                    "rate_limit_seconds": 0.1,
                    "user_agent": "AuctionFinderBot/0.1",
                }
            )

    def test_pagination_links_are_extracted(self):
        html_text = self._load_fixture("liveauctionworld_auction_detail_page1.html")
        page_links = extract_liveauctionworld_pagination_links(
            html_text,
            "https://www.liveauctionworld.com/",
        )
        self.assertEqual(len(page_links), 2)
        self.assertIn("_p2", page_links[1])

    def test_adapter_crawls_multiple_pages_with_limit(self):
        page_one_url = "https://www.liveauctionworld.com/Fall-Antique-Sale_as555"
        page_two_url = "https://www.liveauctionworld.com/Fall-Antique-Sale_as555_p2"
        page_one_html = self._load_fixture("liveauctionworld_auction_detail_page1.html")
        page_two_html = self._load_fixture("liveauctionworld_auction_detail_page2.html")
        calls: list[str] = []

        def page_fetcher(url: str, user_agent: str, timeout_seconds: float) -> str:
            calls.append(url)
            if url == page_one_url:
                return page_one_html
            if url == page_two_url:
                return page_two_html
            return "<html></html>"

        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=page_fetcher,
            sleeper=lambda _: None,
        )
        listings = adapter.crawl_latest(
            {
                "id": 1,
                "name": "LiveAuctionWorld",
                "base_url": "https://www.liveauctionworld.com/",
                "source_type": "html",
                "rate_limit_seconds": 0.1,
                "crawl_max_pages": 2,
                "search_path_template": "https://www.liveauctionworld.com/Fall-Antique-Sale_as555",
                "user_agent": "AuctionFinderBot/0.1",
            }
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(listings), 3)
        self.assertEqual(listings[0].item, "Blue Vase")
        self.assertEqual(listings[-1].item, "Antique Clock")

    def test_parse_item_detail_page(self):
        html_text = self._load_fixture("liveauctionworld_item_detail.html")
        listings = parse_liveauctionworld_html(
            html_text=html_text,
            source_name="LiveAuctionWorld",
            base_url="https://www.liveauctionworld.com/",
        )
        self.assertEqual(len(listings), 1)
        listing = listings[0]
        self.assertEqual(
            listing.item,
            "Josef Hambrusch Rifle Ferlach RARE 6.5 x 57R c/w Zeiss 8 x 56 Scope",
        )
        self.assertEqual(listing.auction_house, "KOS Auctions")
        self.assertEqual(listing.category, "Firearms & Military")
        self.assertIn("_i61264155", listing.listing_url or "")

    def test_keyword_crawl_filters_results(self):
        payload = {
            "ItemResults": [
                {
                    "ItemID": 1001,
                    "ItemTitle": "Blue Vase",
                    "ItemDescription": "Hand-painted porcelain",
                    "ItemCategoryName": ["Auction lot"],
                    "AuctioneerName": "House Alpha",
                    "AuctionCity": "Vancouver",
                    "AuctionProvince": "BC",
                    "AuctionCountry": "Canada",
                    "ItemLot": "1",
                    "ItemCurrentBidAmount": 120.0,
                    "ItemOpeningBidAmount": 80.0,
                    "ItemImageURL": "/images/blue-vase.png",
                    "ItemSold": 0,
                },
                {
                    "ItemID": 1002,
                    "ItemTitle": "Silver Bowl",
                    "ItemDescription": "Sterling bowl",
                    "ItemCategoryName": ["Auction lot"],
                    "AuctioneerName": "House Alpha",
                    "AuctionCity": "Vancouver",
                    "AuctionProvince": "BC",
                    "AuctionCountry": "Canada",
                    "ItemLot": "2",
                    "ItemCurrentBidAmount": 200.0,
                    "ItemSold": 0,
                },
            ]
        }
        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: "",
            json_fetcher=lambda url, user_agent, timeout_seconds: payload,
            sleeper=lambda _: None,
        )
        listings = adapter.crawl_keyword(
            {
                "id": 1,
                "name": "LiveAuctionWorld",
                "base_url": "https://www.liveauctionworld.com/",
                "source_type": "html",
                "rate_limit_seconds": 0.1,
                "crawl_max_pages": 1,
                "search_path_template": "/search.aspx",
                "user_agent": "AuctionFinderBot/0.1",
            },
            keyword="vase",
        )
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].item, "Blue Vase")
        self.assertEqual(listings[0].current_bid_cad, 120.0)
        self.assertEqual(listings[0].opening_bid_cad, 80.0)
        self.assertIn("/images/blue-vase.png", listings[0].image_url or "")

    def test_keyword_crawl_does_not_force_site_id_by_default(self):
        captured_urls: list[str] = []

        def capture_json_fetcher(url: str, user_agent: str, timeout_seconds: float):
            captured_urls.append(url)
            return {"ItemResults": []}

        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: "",
            json_fetcher=capture_json_fetcher,
            sleeper=lambda _: None,
        )

        with self.assertRaises(ValueError):
            adapter.crawl_keyword(
                {
                    "id": 1,
                    "name": "LiveAuctionWorld",
                    "base_url": "https://www.liveauctionworld.com/",
                    "source_type": "html",
                    "rate_limit_seconds": 0.1,
                    "crawl_max_pages": 1,
                    "search_path_template": "/search.aspx",
                    "user_agent": "AuctionFinderBot/0.1",
                },
                keyword="tools",
            )

        self.assertEqual(len(captured_urls), 1)
        self.assertNotIn("siteID=6", captured_urls[0])

    def test_keyword_crawl_uses_configured_site_id_when_present(self):
        captured_urls: list[str] = []

        def capture_json_fetcher(url: str, user_agent: str, timeout_seconds: float):
            captured_urls.append(url)
            return {"ItemResults": []}

        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: "",
            json_fetcher=capture_json_fetcher,
            sleeper=lambda _: None,
        )

        with self.assertRaises(ValueError):
            adapter.crawl_keyword(
                {
                    "id": 1,
                    "name": "LiveAuctionWorld",
                    "base_url": "https://www.liveauctionworld.com/",
                    "source_type": "html",
                    "rate_limit_seconds": 0.1,
                    "crawl_max_pages": 1,
                    "site_id": "12",
                    "search_path_template": "/search.aspx",
                    "user_agent": "AuctionFinderBot/0.1",
                },
                keyword="tools",
            )

        self.assertEqual(len(captured_urls), 1)
        self.assertIn("siteID=12", captured_urls[0])

        def test_keyword_crawl_falls_back_to_generic_url_crawl_for_other_domains(self):
                html_text = """
                <html>
                    <body>
                        <a href='/auctions/tools/lot-991-ridgid-pipe-wrench'>RIDGID Pipe Wrench Lot 991</a>
                        <div>Current bid CAD 180</div>
                    </body>
                </html>
                """
                adapter = LiveAuctionWorldHtmlAdapter(
                        fetcher=lambda url, user_agent, timeout_seconds: html_text,
                        sleeper=lambda _: None,
                )
                listings = adapter.crawl_keyword(
                        {
                                "id": 1,
                                "name": "Urban Auctions",
                                "base_url": "https://urbanauctions.ca",
                                "source_type": "html",
                                "rate_limit_seconds": 0.0,
                                "crawl_max_pages": 1,
                                "user_agent": "AuctionFinderBot/0.1",
                        },
                        keyword="wrench",
                )

                self.assertEqual(len(listings), 1)
                self.assertIn("wrench", listings[0].item.lower())

    def test_crawl_url_uses_explicit_url(self):
        page_url = "https://www.liveauctionworld.com/Fall-Antique-Sale_as555"
        html_text = self._load_fixture("liveauctionworld_auction_detail_page1.html")
        calls: list[str] = []

        def page_fetcher(url: str, user_agent: str, timeout_seconds: float) -> str:
            calls.append(url)
            return html_text

        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=page_fetcher,
            sleeper=lambda _: None,
        )
        listings = adapter.crawl_url(
            {
                "id": 1,
                "name": "LiveAuctionWorld",
                "base_url": "https://www.liveauctionworld.com/",
                "source_type": "html",
                "rate_limit_seconds": 0.1,
                "crawl_max_pages": 1,
                "user_agent": "AuctionFinderBot/0.1",
            },
            auction_url=page_url,
        )
        self.assertEqual(calls[0], page_url)
        self.assertGreaterEqual(len(listings), 1)

    def test_crawl_url_supports_non_liveauctionworld_domain(self):
        html_text = self._load_fixture("liveauctionworld_snapshot_jsonld.html")
        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: html_text,
            sleeper=lambda _: None,
        )
        listings = adapter.crawl_url(
            {
                "id": 1,
                "name": "LiveAuctionWorld",
                "base_url": "https://www.liveauctionworld.com/",
                "source_type": "html",
                "rate_limit_seconds": 0.1,
                "user_agent": "AuctionFinderBot/0.1",
            },
            auction_url="https://example.com/auction",
        )
        self.assertGreaterEqual(len(listings), 1)

    def test_crawl_url_prefers_urban_lotdetails_links_over_event_details(self):
        html_text = """
        <html>
            <body>
                <a href='/Event/Details/172162755/GENERAL-AUCTION-OCT-30TH-TO-NOV-1ST/C165507/Tools-'>
                    General Auction Event Page
                </a>
                <a href='/Event/LotDetails/172201544/NEW-MILWAUKEE-M12-RED-LITHIUM-CP15-BATTERY'>
                    NEW MILWAUKEE M12 RED LITHIUM CP1.5 BATTERY
                </a>
                <div>Current bid CAD 65</div>
            </body>
        </html>
        """
        adapter = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: html_text,
            sleeper=lambda _: None,
        )

        listings = adapter.crawl_url(
            {
                "id": 1,
                "name": "Urban Auctions",
                "base_url": "https://urbanauctions.ca",
                "source_type": "html",
                "rate_limit_seconds": 0.0,
                "crawl_max_pages": 1,
                "user_agent": "AuctionFinderBot/0.1",
            },
            auction_url=(
                "https://urbanauctions.ca/Event/Details/172162755/"
                "GENERAL-AUCTION-OCT-30TH-TO-NOV-1ST/C165507/Tools-"
            ),
        )

        self.assertEqual(len(listings), 1)
        self.assertIn("/event/lotdetails/", (listings[0].listing_url or "").lower())
        self.assertNotIn("/event/details/", (listings[0].listing_url or "").lower())

        def test_generic_crawl_filters_navigation_links(self):
                html_text = """
                <html>
                    <body>
                        <a href='/login'>Login</a>
                        <a href='/privacy'>Privacy Policy</a>
                        <a href='/auction/lot-10342-blue-vase'>Blue porcelain vase lot 10342</a>
                        <div>Current bid CAD 420</div>
                        <a href='/item/884211-antique-clock'>Antique wall clock lot 884211</a>
                    </body>
                </html>
                """
                adapter = LiveAuctionWorldHtmlAdapter(
                        fetcher=lambda url, user_agent, timeout_seconds: html_text,
                        sleeper=lambda _: None,
                )

                listings = adapter.crawl_url(
                        {
                                "id": 1,
                                "name": "Generic Auctions",
                                "base_url": "https://example-auctions.test",
                                "source_type": "html",
                                "rate_limit_seconds": 0.0,
                                "crawl_max_pages": 1,
                                "user_agent": "AuctionFinderBot/0.1",
                        },
                        auction_url="https://example-auctions.test/start",
                )

                self.assertEqual(len(listings), 2)
                joined_titles = " ".join(listing.item.lower() for listing in listings)
                self.assertIn("blue porcelain vase", joined_titles)
                self.assertIn("antique wall clock", joined_titles)


if __name__ == "__main__":
    unittest.main()
