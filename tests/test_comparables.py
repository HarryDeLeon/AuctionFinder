import unittest

from comparables import analyze_listing_against_comparables
from models import AuctionListing


class ComparablesTests(unittest.TestCase):

    def test_flags_potential_opportunity_with_sufficient_evidence(self):
        listings = [
            AuctionListing(
                item="Blue porcelain vase",
                description="Hand-painted floral porcelain",
                category="Porcelain",
                auction_house="A",
                status="Active",
                price_cad=200.0,
                buyer_premium_percent=20.0,
                shipping_cad=20.0,
            ),
            AuctionListing(
                item="Vintage porcelain vase",
                description="Porcelain floral motif",
                category="Porcelain",
                auction_house="B",
                status="Sold",
                price_cad=400.0,
                buyer_premium_percent=20.0,
                shipping_cad=30.0,
            ),
            AuctionListing(
                item="Decorative porcelain vase",
                description="Floral painted porcelain",
                category="Porcelain",
                auction_house="C",
                status="Sold",
                price_cad=380.0,
                buyer_premium_percent=18.0,
                shipping_cad=25.0,
            ),
        ]

        summary = analyze_listing_against_comparables(
            listings[0], listings
        )

        self.assertEqual(summary.comparable_count, 2)
        self.assertEqual(summary.opportunity_label, "Potential opportunity")
        self.assertEqual(summary.confidence_label, "Medium")

    def test_returns_not_enough_information_when_no_comparables(self):
        listings = [
            AuctionListing(
                item="Landscape painting",
                category="Art",
                auction_house="A",
                status="Active",
                price_cad=500.0,
                buyer_premium_percent=20.0,
                shipping_cad=30.0,
            ),
            AuctionListing(
                item="Silver bowl",
                category="Silver",
                auction_house="B",
                status="Sold",
                price_cad=300.0,
                buyer_premium_percent=15.0,
                shipping_cad=20.0,
            ),
        ]

        summary = analyze_listing_against_comparables(
            listings[0], listings
        )

        self.assertEqual(summary.comparable_count, 0)
        self.assertEqual(
            summary.opportunity_label, "Not enough information"
        )
        self.assertIsNone(summary.comparable_median_cad)

    def test_uses_limited_evidence_label_for_single_comparable(self):
        listings = [
            AuctionListing(
                item="Antique porcelain bowl",
                description="Blue porcelain with floral decoration",
                category="Porcelain",
                auction_house="A",
                status="Active",
                price_cad=220.0,
                buyer_premium_percent=20.0,
                shipping_cad=20.0,
            ),
            AuctionListing(
                item="Vintage porcelain bowl",
                description="Blue floral porcelain",
                category="Porcelain",
                auction_house="B",
                status="Sold",
                price_cad=260.0,
                buyer_premium_percent=20.0,
                shipping_cad=20.0,
            ),
        ]

        summary = analyze_listing_against_comparables(
            listings[0], listings
        )
        self.assertEqual(summary.comparable_count, 1)
        self.assertEqual(
            summary.opportunity_label,
            "Limited comparable evidence",
        )


if __name__ == "__main__":
    unittest.main()
