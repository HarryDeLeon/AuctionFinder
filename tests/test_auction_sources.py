import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from auction_sources import (
    ManualCsvAuctionSource,
    load_manual_source_csv_preview,
    load_manual_source_csv_preview_with_report,
    normalize_source_record,
    normalize_source_records,
)


class AuctionSourcesTests(unittest.TestCase):
    def test_manual_csv_source_loads_records(self):
        csv_text = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad,description,"
            "sale_date_iso\n"
            "r1,Blue vase,Porcelain,House A,Active,250,20,25,"
            "Hand-painted,2026-10-25\n"
        )
        source = ManualCsvAuctionSource(csv_text, source_name="manual_test")
        records = list(source.load_records())

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_name, "manual_test")
        self.assertEqual(records[0].source_record_id, "r1")
        self.assertEqual(records[0].item_title, "Blue vase")

    def test_manual_csv_source_rejects_missing_required_columns(self):
        bad_csv = "source_record_id,item_title\nr1,Blue vase\n"
        source = ManualCsvAuctionSource(bad_csv)
        with self.assertRaises(ValueError):
            list(source.load_records())

    def test_manual_csv_source_can_load_from_file(self):
        csv_text = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad\n"
            "r1,Silver bowl,Silver,House B,Sold,300,18,20\n"
        )
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "import.csv"
            csv_path.write_text(csv_text, encoding="utf-8")
            source = ManualCsvAuctionSource.from_file(csv_path)
            records = list(source.load_records())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].item_title, "Silver bowl")

    def test_normalization_produces_auction_listing(self):
        csv_text = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad,sale_date_iso\n"
            "r1,Blue vase,Porcelain,House A,Active,250,20,25,2026-10-25\n"
        )
        source = ManualCsvAuctionSource(csv_text)
        records = list(source.load_records())
        listings = normalize_source_records(records)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].item, "Blue vase")
        self.assertEqual(listings[0].source_record_id, "r1")
        self.assertEqual(listings[0].sale_date.isoformat(), "2026-10-25")

    def test_normalization_rejects_negative_values(self):
        csv_text = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad\n"
            "r1,Blue vase,Porcelain,House A,Active,-1,20,25\n"
        )
        source = ManualCsvAuctionSource(csv_text)
        record = list(source.load_records())[0]
        with self.assertRaises(ValueError):
            normalize_source_record(record)

    def test_error_message_includes_row_number(self):
        bad_csv = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad\n"
            "r1,Blue vase,Porcelain,House A,Active,not-a-number,20,25\n"
        )
        source = ManualCsvAuctionSource(bad_csv)
        with self.assertRaises(ValueError) as exc:
            list(source.load_records())
        self.assertIn("Row 2", str(exc.exception))

    def test_import_preview_loader_returns_normalized_listings(self):
        csv_text = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad\n"
            "r1,Blue vase,Porcelain,House A,Active,250,20,25\n"
        )
        listings = load_manual_source_csv_preview(csv_text)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].item, "Blue vase")

    def test_load_records_with_report_keeps_valid_rows(self):
        csv_text = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad\n"
            "r1,Blue vase,Porcelain,House A,Active,250,20,25\n"
            "r2,Invalid vase,Porcelain,House A,Active,not-a-number,20,25\n"
        )
        source = ManualCsvAuctionSource(csv_text)
        report = source.load_records_with_report()

        self.assertEqual(report.total_rows, 2)
        self.assertEqual(report.valid_rows, 1)
        self.assertEqual(report.rejected_rows, 1)
        rejected_csv = report.rejected_rows_to_csv()
        self.assertIn("row_number,error_message", rejected_csv)
        self.assertIn("3", rejected_csv)

    def test_preview_report_returns_reject_csv_and_valid_rows(self):
        csv_text = (
            "source_record_id,item_title,category,auction_house,status,"
            "price_cad,buyer_premium_percent,shipping_cad\n"
            "r1,Blue vase,Porcelain,House A,Active,250,20,25\n"
            "r2,Bad row,Porcelain,House A,Active,-5,20,25\n"
        )
        preview_result = load_manual_source_csv_preview_with_report(csv_text)
        self.assertEqual(preview_result.total_rows, 2)
        self.assertEqual(preview_result.valid_rows, 1)
        self.assertEqual(len(preview_result.rejected_rows), 1)
        self.assertIn("row_number,error_message", preview_result.rejected_rows_csv)
        self.assertIn("price_cad cannot be negative", preview_result.rejected_rows_csv)


if __name__ == "__main__":
    unittest.main()
