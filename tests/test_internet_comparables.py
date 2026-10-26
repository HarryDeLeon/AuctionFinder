import unittest

from internet_comparables import analyze_listing_internet_prices
from internet_comparables import _extract_price_candidates
from models import AuctionListing


class InternetComparablesTests(unittest.TestCase):
    def test_extract_price_candidates_parses_multiple_currencies(self):
        candidates = _extract_price_candidates(
            "Offered at US$120.00 or C$150.00"
        )
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0][2], "USD")
        self.assertEqual(candidates[1][2], "CAD")

    def test_analyze_listing_internet_prices_computes_low_high_average(self):
        html_text = """
        <html><body>
            <a class="result__a" href="https://shop.example.com/one">Blue Vase - C$100.00</a>
            <a class="result__snippet" href="#">Vintage condition</a>
            <a class="result__a" href="https://shop.example.com/two">Blue Vase - US$120.00</a>
            <a class="result__snippet" href="#">Rare collectible</a>
        </body></html>
        """

        listing = AuctionListing(
            item="Blue Vase",
            category="Porcelain",
            auction_house="Test",
            status="Active",
            price_cad=50.0,
            buyer_premium_percent=0.0,
            shipping_cad=0.0,
            description="Vintage porcelain blue vase",
        )

        summary = analyze_listing_internet_prices(
            listing=listing,
            max_results=10,
            fetcher=lambda _: html_text,
        )
        self.assertEqual(summary.comparable_count, 2)
        self.assertEqual(summary.lowest_price_cad, 100.0)
        self.assertEqual(summary.highest_price_cad, 163.2)
        self.assertEqual(summary.average_price_cad, 131.6)
        self.assertIsNone(summary.error_message)

    def test_analyze_listing_internet_prices_reports_missing_prices(self):
        listing = AuctionListing(
            item="Clock",
            category="Clocks",
            auction_house="Test",
            status="Active",
            price_cad=80.0,
            buyer_premium_percent=0.0,
            shipping_cad=0.0,
            description="Antique clock",
        )
        summary = analyze_listing_internet_prices(
            listing=listing,
            fetcher=lambda _: "<html><body>No prices here</body></html>",
        )
        self.assertEqual(summary.comparable_count, 0)
        self.assertIsNotNone(summary.error_message)


if __name__ == "__main__":
    unittest.main()
