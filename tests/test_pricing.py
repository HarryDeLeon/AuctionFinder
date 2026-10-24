import unittest

from models import AuctionListing
from pricing import calculate_estimated_cost, calculate_price_breakdown


class PricingTests(unittest.TestCase):

    def test_calculates_price_with_premium_and_shipping(self):
        listing = AuctionListing(
            item="Test vase",
            category="Porcelain",
            auction_house="Test auction",
            status="Sold",
            price_cad=100.00,
            buyer_premium_percent=20,
            shipping_cad=10.00,
        )

        result = calculate_estimated_cost(listing)

        self.assertEqual(result, 130.00)

    def test_calculates_price_without_premium(self):
        listing = AuctionListing(
            item="Test bowl",
            category="Silver",
            auction_house="Test auction",
            status="Sold",
            price_cad=100.00,
            buyer_premium_percent=0,
            shipping_cad=15.00,
        )

        result = calculate_estimated_cost(listing)

        self.assertEqual(result, 115.00)

    def test_includes_other_fees_in_total(self):
        listing = AuctionListing(
            item="Test desk",
            category="Furniture",
            auction_house="Test auction",
            status="Sold",
            price_cad=200.00,
            buyer_premium_percent=10,
            shipping_cad=20.00,
            other_fees_cad=15.00,
        )

        result = calculate_estimated_cost(listing)

        self.assertEqual(result, 255.00)

    def test_can_include_tax_when_rate_is_available(self):
        listing = AuctionListing(
            item="Test clock",
            category="Clocks",
            auction_house="Test auction",
            status="Sold",
            price_cad=100.00,
            buyer_premium_percent=20,
            shipping_cad=10.00,
            other_fees_cad=5.00,
            tax_percent=5.0,
        )

        result = calculate_estimated_cost(
            listing,
            include_taxes=True,
        )

        # subtotal 135.00 + tax 6.75
        self.assertEqual(result, 141.75)

    def test_breakdown_reports_excluded_taxes_when_rate_missing(self):
        listing = AuctionListing(
            item="Test lamp",
            category="Decorative antiques",
            auction_house="Test auction",
            status="Sold",
            price_cad=80.00,
            buyer_premium_percent=25,
            shipping_cad=10.00,
        )

        breakdown = calculate_price_breakdown(
            listing,
            include_taxes=True,
        )

        self.assertEqual(
            breakdown.excluded_charges,
            ["Taxes excluded: no tax rate available."],
        )
        self.assertEqual(breakdown.tax_cad, 0.0)

    def test_active_listing_is_marked_as_estimate(self):
        listing = AuctionListing(
            item="Test painting",
            category="Art",
            auction_house="Test auction",
            status="Active",
            price_cad=300.00,
            buyer_premium_percent=10,
            shipping_cad=20.00,
        )

        breakdown = calculate_price_breakdown(listing)

        self.assertTrue(breakdown.is_estimate)
        self.assertIn("Active auction", breakdown.estimate_notes)

    def test_rejects_negative_inputs(self):
        listing = AuctionListing(
            item="Invalid listing",
            category="Other",
            auction_house="Test auction",
            status="Sold",
            price_cad=-1.00,
            buyer_premium_percent=10,
            shipping_cad=5.00,
        )

        with self.assertRaises(ValueError):
            calculate_price_breakdown(listing)


if __name__ == "__main__":
    unittest.main()