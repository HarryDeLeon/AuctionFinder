import unittest

from models import AuctionListing
from pricing import calculate_estimated_cost


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


if __name__ == "__main__":
    unittest.main()