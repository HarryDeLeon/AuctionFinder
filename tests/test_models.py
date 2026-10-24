import unittest
from datetime import date

from models import AuctionListing


class AuctionListingModelTests(unittest.TestCase):

    def test_existing_constructor_shape_still_works(self):
        listing = AuctionListing(
            item="Test vase",
            category="Porcelain",
            auction_house="Test auction",
            status="Sold",
            price_cad=100.0,
            buyer_premium_percent=20.0,
            shipping_cad=10.0,
        )

        self.assertEqual(listing.item, "Test vase")
        self.assertEqual(listing.currency, "CAD")
        self.assertIsNone(listing.listing_url)
        self.assertEqual(listing.description, "")

    def test_supports_extended_metadata_fields(self):
        listing = AuctionListing(
            item="Antique clock",
            category="Clocks",
            auction_house="Demo House",
            status="Active",
            price_cad=500.0,
            buyer_premium_percent=18.0,
            shipping_cad=45.0,
            description="Late 19th century mantle clock.",
            location="Vancouver, BC",
            listing_url="https://example.com/listing/123",
            lot_number="123",
            sale_date=date(2026, 10, 24),
            source_name="Manual import",
            source_record_id="demo-123",
            comparability_confidence=0.8,
            confidence_notes="Maker and dimensions align with known comps.",
        )

        self.assertEqual(listing.location, "Vancouver, BC")
        self.assertEqual(listing.sale_date, date(2026, 10, 24))
        self.assertEqual(listing.comparability_confidence, 0.8)


if __name__ == "__main__":
    unittest.main()
