import tempfile
import unittest
from pathlib import Path

from auction_sources.liveauctionworld_html_source import LiveAuctionWorldHtmlAdapter
from ingestion import run_source_crawl
from ingestion import ADAPTER_REGISTRY
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


if __name__ == "__main__":
    unittest.main()
