import tempfile
import unittest
from pathlib import Path

from auction_sources.liveauctionworld_html_source import LiveAuctionWorldHtmlAdapter
from ingestion import run_source_crawl
from ingestion import ADAPTER_REGISTRY
from ingestion import run_source_keyword_crawl
from ingestion import run_source_url_crawl
from models import AuctionListing
from repositories import (
    create_source_config,
    initialize_database,
    list_ingested_listings,
    list_recent_crawl_runs,
)


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_dummy_source_crawl_inserts_listing(self):
        source_id = create_source_config(
            name="LiveAuctionWorld",
            base_url="https://www.liveauctionworld.com/",
            source_type="dummy",
            db_path=self.db_path,
        )

        summary = run_source_crawl(source_id, db_path=self.db_path)

        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.discovered_count, 1)
        rows = list_ingested_listings(source_id, db_path=self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_record_id"].startswith("dummy-"), True)

    def test_unknown_source_type_marks_run_failed(self):
        source_id = create_source_config(
            name="Unsupported Source",
            base_url="https://example.com",
            source_type="rss",
            db_path=self.db_path,
        )

        summary = run_source_crawl(source_id, db_path=self.db_path)

        self.assertEqual(summary.status, "failed")
        self.assertIn("No adapter is registered", summary.error_summary or "")
        runs = list_recent_crawl_runs(source_id, db_path=self.db_path)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "failed")

    def test_html_source_crawl_uses_liveauctionworld_adapter(self):
        fixture_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "liveauctionworld_auction_detail_page1.html"
        )
        html_text = fixture_path.read_text(encoding="utf-8")

        original_adapter = ADAPTER_REGISTRY["html"]
        ADAPTER_REGISTRY["html"] = LiveAuctionWorldHtmlAdapter(
            fetcher=lambda url, user_agent, timeout_seconds: html_text
        )
        try:
            source_id = create_source_config(
                name="LiveAuctionWorld",
                base_url="https://www.liveauctionworld.com/",
                source_type="html",
                db_path=self.db_path,
            )
            summary = run_source_crawl(source_id, db_path=self.db_path)
        finally:
            ADAPTER_REGISTRY["html"] = original_adapter

        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.discovered_count, 2)
        rows = list_ingested_listings(source_id, db_path=self.db_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["item"] in {"Blue Vase", "Silver Bowl"}, True)

    def test_keyword_crawl_uses_adapter_keyword_method(self):
        class KeywordAdapter:
            def crawl_latest(self, source_config):
                return []

            def crawl_keyword(self, source_config, keyword):
                return [
                    AuctionListing(
                        item=f"{keyword} example listing",
                        category="Auction lot",
                        auction_house="LiveAuctionWorld",
                        status="Active",
                        price_cad=0.0,
                        buyer_premium_percent=0.0,
                        shipping_cad=0.0,
                        description="keyword match",
                        listing_url="https://www.liveauctionworld.com/example_i1",
                        source_name="LiveAuctionWorld",
                        source_record_id="1",
                    )
                ]

        original_adapter = ADAPTER_REGISTRY["html"]
        ADAPTER_REGISTRY["html"] = KeywordAdapter()
        try:
            source_id = create_source_config(
                name="LiveAuctionWorld",
                base_url="https://www.liveauctionworld.com/",
                source_type="html",
                db_path=self.db_path,
            )
            summary = run_source_keyword_crawl(
                source_id,
                keyword="rifle",
                db_path=self.db_path,
            )
        finally:
            ADAPTER_REGISTRY["html"] = original_adapter

        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.discovered_count, 1)

    def test_url_crawl_uses_adapter_url_method(self):
        class UrlAdapter:
            def crawl_latest(self, source_config):
                return []

            def crawl_url(self, source_config, auction_url):
                return [
                    AuctionListing(
                        item=f"Lot from {auction_url}",
                        category="Auction lot",
                        auction_house="LiveAuctionWorld",
                        status="Active",
                        price_cad=0.0,
                        buyer_premium_percent=0.0,
                        shipping_cad=0.0,
                        description="url crawl match",
                        listing_url=auction_url,
                        source_name="LiveAuctionWorld",
                        source_record_id="url-1",
                    )
                ]

        original_adapter = ADAPTER_REGISTRY["html"]
        ADAPTER_REGISTRY["html"] = UrlAdapter()
        try:
            source_id = create_source_config(
                name="LiveAuctionWorld",
                base_url="https://www.liveauctionworld.com/",
                source_type="html",
                db_path=self.db_path,
            )
            summary = run_source_url_crawl(
                source_id,
                auction_url="https://www.liveauctionworld.com/Fall-Antique-Sale_as555",
                db_path=self.db_path,
            )
        finally:
            ADAPTER_REGISTRY["html"] = original_adapter

        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.discovered_count, 1)

    def test_url_crawl_passes_keyword_when_supported(self):
        class UrlKeywordAdapter:
            def crawl_latest(self, source_config):
                return []

            def crawl_url(self, source_config, auction_url, keyword=None):
                item_name = keyword or "no keyword"
                return [
                    AuctionListing(
                        item=f"{item_name} result",
                        category="Auction lot",
                        auction_house="Generic",
                        status="Active",
                        price_cad=0.0,
                        buyer_premium_percent=0.0,
                        shipping_cad=0.0,
                        description="url crawl match",
                        listing_url=auction_url,
                        source_name="Generic",
                        source_record_id="url-keyword-1",
                    )
                ]

        original_adapter = ADAPTER_REGISTRY["html"]
        ADAPTER_REGISTRY["html"] = UrlKeywordAdapter()
        try:
            source_id = create_source_config(
                name="Generic",
                base_url="https://example.com",
                source_type="html",
                db_path=self.db_path,
            )
            summary = run_source_url_crawl(
                source_id,
                auction_url="https://example.com/auctions",
                keyword="vase",
                db_path=self.db_path,
            )
        finally:
            ADAPTER_REGISTRY["html"] = original_adapter

        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.discovered_count, 1)


if __name__ == "__main__":
    unittest.main()
