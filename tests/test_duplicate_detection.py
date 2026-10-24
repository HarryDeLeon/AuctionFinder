import unittest

from duplicate_detection import summarize_potential_duplicates
from models import AuctionListing


class DuplicateDetectionTests(unittest.TestCase):

    def test_flags_same_listing_url_as_review_recommended(self):
        target = AuctionListing(
            item="Blue porcelain vase",
            description="Hand-painted floral motif",
            category="Porcelain",
            auction_house="House A",
            status="Active",
            price_cad=300.0,
            buyer_premium_percent=20.0,
            shipping_cad=20.0,
            listing_url="https://example.com/listing/123",
        )
        same_url = AuctionListing(
            item="Blue and white porcelain vase",
            description="Floral motif",
            category="Porcelain",
            auction_house="House B",
            status="Sold",
            price_cad=310.0,
            buyer_premium_percent=18.0,
            shipping_cad=25.0,
            listing_url="https://example.com/listing/123",
        )

        summary = summarize_potential_duplicates(target, [target, same_url])
        self.assertEqual(summary.candidate_count, 1)
        self.assertEqual(summary.review_label, "Review recommended")
        self.assertEqual(summary.candidates[0].confidence, "High")

    def test_returns_no_signal_for_distinct_records(self):
        target = AuctionListing(
            item="Landscape oil painting",
            category="Art",
            auction_house="House A",
            status="Active",
            price_cad=700.0,
            buyer_premium_percent=20.0,
            shipping_cad=40.0,
        )
        different = AuctionListing(
            item="Sterling silver bowl",
            category="Silver",
            auction_house="House B",
            status="Sold",
            price_cad=280.0,
            buyer_premium_percent=15.0,
            shipping_cad=25.0,
        )

        summary = summarize_potential_duplicates(target, [target, different])
        self.assertEqual(summary.candidate_count, 0)
        self.assertEqual(summary.review_label, "No duplicate signal")

    def test_detects_high_text_overlap_same_category(self):
        target = AuctionListing(
            item="Antique porcelain serving bowl",
            description="Blue floral porcelain bowl",
            category="Porcelain",
            auction_house="House A",
            status="Active",
            price_cad=250.0,
            buyer_premium_percent=20.0,
            shipping_cad=20.0,
        )
        similar = AuctionListing(
            item="Antique porcelain serving bowl",
            description="Blue floral porcelain serving bowl",
            category="Porcelain",
            auction_house="House C",
            status="Sold",
            price_cad=245.0,
            buyer_premium_percent=18.0,
            shipping_cad=20.0,
        )

        summary = summarize_potential_duplicates(target, [target, similar])
        self.assertEqual(summary.candidate_count, 1)
        self.assertIn(
            summary.candidates[0].confidence,
            {"Medium", "High"},
        )


if __name__ == "__main__":
    unittest.main()
