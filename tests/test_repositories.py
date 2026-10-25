import tempfile
import unittest
from pathlib import Path

from models import AuctionListing
from repositories import (
    complete_crawl_run,
    create_crawl_run,
    create_source_config,
    delete_source_config,
    delete_saved_search,
    delete_watchlist_entry,
    export_saved_searches_to_csv,
    export_watchlist_to_csv,
    get_source_config,
    import_saved_searches_from_csv,
    import_watchlist_from_csv,
    initialize_database,
    list_ingested_listings,
    list_recent_crawl_runs,
    list_saved_searches,
    list_source_configs,
    list_watchlist_entries,
    update_source_config,
    upsert_ingested_listing,
    upsert_saved_search,
    upsert_watchlist_entry,
)


class RepositoryTests(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_watchlist_entry_round_trip(self):
        listing = AuctionListing(
            item="Blue porcelain vase",
            category="Porcelain",
            auction_house="Demo House",
            status="Active",
            price_cad=200.0,
            buyer_premium_percent=20.0,
            shipping_cad=25.0,
        )

        upsert_watchlist_entry(
            listing=listing,
            estimated_total_cad=265.0,
            db_path=self.db_path,
        )

        entries = list_watchlist_entries(self.db_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["item_title"], "Blue porcelain vase")

        delete_watchlist_entry(entries[0]["item_key"], self.db_path)
        self.assertEqual(len(list_watchlist_entries(self.db_path)), 0)

    def test_saved_search_round_trip(self):
        upsert_saved_search(
            name="Porcelain under 500",
            keyword="porcelain",
            category="Porcelain",
            status="Active",
            min_price_cad=0.0,
            max_price_cad=500.0,
            sort_by="Estimated total (CAD)",
            sort_desc=False,
            db_path=self.db_path,
        )

        searches = list_saved_searches(self.db_path)
        self.assertEqual(len(searches), 1)
        self.assertEqual(searches[0]["name"], "Porcelain under 500")

        delete_saved_search("Porcelain under 500", self.db_path)
        self.assertEqual(len(list_saved_searches(self.db_path)), 0)

    def test_saved_search_requires_name(self):
        with self.assertRaises(ValueError):
            upsert_saved_search(
                name="   ",
                keyword="vase",
                category="All",
                status="All",
                min_price_cad=None,
                max_price_cad=None,
                sort_by="Estimated total (CAD)",
                sort_desc=False,
                db_path=self.db_path,
            )

    def test_watchlist_csv_export_and_import(self):
        listing = AuctionListing(
            item="Blue porcelain vase",
            category="Porcelain",
            auction_house="Demo House",
            status="Active",
            price_cad=200.0,
            buyer_premium_percent=20.0,
            shipping_cad=25.0,
            listing_url="https://example.com/lot/1",
        )
        upsert_watchlist_entry(
            listing=listing,
            estimated_total_cad=265.0,
            db_path=self.db_path,
        )

        csv_text = export_watchlist_to_csv(self.db_path)
        delete_watchlist_entry(
            list_watchlist_entries(self.db_path)[0]["item_key"],
            self.db_path,
        )
        imported = import_watchlist_from_csv(csv_text, self.db_path)
        self.assertEqual(imported, 1)
        self.assertEqual(len(list_watchlist_entries(self.db_path)), 1)

    def test_saved_search_csv_export_and_import(self):
        upsert_saved_search(
            name="Porcelain under 500",
            keyword="porcelain",
            category="Porcelain",
            status="Active",
            min_price_cad=0.0,
            max_price_cad=500.0,
            sort_by="Estimated total (CAD)",
            sort_desc=False,
            db_path=self.db_path,
        )

        csv_text = export_saved_searches_to_csv(self.db_path)
        delete_saved_search("Porcelain under 500", self.db_path)
        imported = import_saved_searches_from_csv(csv_text, self.db_path)
        self.assertEqual(imported, 1)
        self.assertEqual(len(list_saved_searches(self.db_path)), 1)

    def test_watchlist_csv_validation_rejects_missing_columns(self):
        bad_csv = "item_title,auction_house,status\nVase,Demo,Active\n"
        with self.assertRaises(ValueError):
            import_watchlist_from_csv(bad_csv, self.db_path)

    def test_saved_search_csv_validation_rejects_invalid_sort_desc(self):
        bad_csv = (
            "name,keyword,category,status,min_price_cad,max_price_cad,"
            "sort_by,sort_desc\n"
            "Test,vase,All,All,,,Estimated total (CAD),maybe\n"
        )
        with self.assertRaises(ValueError):
            import_saved_searches_from_csv(bad_csv, self.db_path)

    def test_source_config_crud_round_trip(self):
        source_id = create_source_config(
            name="LiveAuctionWorld",
            base_url="https://www.liveauctionworld.com/",
            source_type="dummy",
            enabled=True,
            rate_limit_seconds=1.5,
            crawl_max_pages=2,
            user_agent="AuctionFinderBot/0.1",
            notes="Seed source",
            db_path=self.db_path,
        )
        self.assertGreater(source_id, 0)

        sources = list_source_configs(self.db_path)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["name"], "LiveAuctionWorld")

        update_source_config(
            source_id=source_id,
            name="LAW",
            base_url="https://www.liveauctionworld.com/",
            source_type="html",
            enabled=False,
            rate_limit_seconds=3.0,
            crawl_max_pages=5,
            user_agent="CustomAgent/1.0",
            search_path_template="/search?q={query}",
            notes="Updated",
            db_path=self.db_path,
        )
        updated = get_source_config(source_id, self.db_path)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "LAW")
        self.assertEqual(updated["source_type"], "html")
        self.assertEqual(updated["enabled"], 0)
        self.assertEqual(updated["crawl_max_pages"], 5)

        delete_source_config(source_id, self.db_path)
        self.assertEqual(len(list_source_configs(self.db_path)), 0)

    def test_upsert_ingested_listing_insert_then_update(self):
        source_id = create_source_config(
            name="Dummy source",
            base_url="https://example.com",
            db_path=self.db_path,
        )
        listing = AuctionListing(
            item="Blue vase",
            category="Porcelain",
            auction_house="Demo House",
            status="Active",
            price_cad=200.0,
            buyer_premium_percent=20.0,
            shipping_cad=25.0,
            image_url="https://example.com/blue-vase.png",
            opening_bid_cad=100.0,
            current_bid_cad=200.0,
            source_name="Dummy source",
            source_record_id="abc-123",
        )
        first = upsert_ingested_listing(
            source_config_id=source_id,
            listing=listing,
            raw_url="https://example.com/lot/1",
            db_path=self.db_path,
        )
        self.assertEqual(first, "inserted")

        listing.status = "Sold"
        second = upsert_ingested_listing(
            source_config_id=source_id,
            listing=listing,
            raw_url="https://example.com/lot/1",
            db_path=self.db_path,
        )
        self.assertEqual(second, "updated")

        rows = list_ingested_listings(source_config_id=source_id, db_path=self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "Sold")
        self.assertEqual(rows[0]["image_url"], "https://example.com/blue-vase.png")
        self.assertEqual(rows[0]["opening_bid_cad"], 100.0)
        self.assertEqual(rows[0]["current_bid_cad"], 200.0)

    def test_crawl_run_tracking(self):
        source_id = create_source_config(
            name="Crawl source",
            base_url="https://example.com",
            db_path=self.db_path,
        )
        run_id = create_crawl_run(source_id, self.db_path)
        complete_crawl_run(
            run_id=run_id,
            status="success",
            discovered_count=2,
            inserted_count=1,
            updated_count=1,
            rejected_count=0,
            error_summary=None,
            db_path=self.db_path,
        )
        runs = list_recent_crawl_runs(source_id, db_path=self.db_path)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "success")
        self.assertEqual(runs[0]["discovered_count"], 2)


if __name__ == "__main__":
    unittest.main()
