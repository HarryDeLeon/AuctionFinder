import tempfile
import unittest
from pathlib import Path

from models import AuctionListing
from repositories import (
    delete_saved_search,
    delete_watchlist_entry,
    export_saved_searches_to_csv,
    export_watchlist_to_csv,
    import_saved_searches_from_csv,
    import_watchlist_from_csv,
    initialize_database,
    list_saved_searches,
    list_watchlist_entries,
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


if __name__ == "__main__":
    unittest.main()
