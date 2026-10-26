import unittest
from datetime import date

from models import AuctionListing
from search import search_listings
from search import select_top_listings_for_internet_report


class SearchListingsTests(unittest.TestCase):

    def setUp(self):
        self.listings = [
            AuctionListing(
                item="Blue porcelain vase",
                description="Hand-painted floral details.",
                category="Porcelain",
                auction_house="A",
                status="Active",
                price_cad=200.0,
                buyer_premium_percent=20.0,
                shipping_cad=25.0,
                sale_date=date(2026, 10, 20),
            ),
            AuctionListing(
                item="Silver serving bowl",
                description="Sterling silver, Victorian era.",
                category="Silver",
                auction_house="B",
                status="Sold",
                price_cad=320.0,
                buyer_premium_percent=15.0,
                shipping_cad=20.0,
                sale_date=date(2026, 10, 21),
            ),
            AuctionListing(
                item="Landscape painting",
                description="Oil on canvas.",
                category="Art",
                auction_house="C",
                status="Active",
                price_cad=450.0,
                buyer_premium_percent=10.0,
                shipping_cad=35.0,
                sale_date=None,
            ),
        ]

    def test_keyword_matches_item_or_description(self):
        results = search_listings(self.listings, keyword="floral")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].item, "Blue porcelain vase")

    def test_filters_by_category_status_and_price_range(self):
        results = search_listings(
            self.listings,
            category="Porcelain",
            status="Active",
            min_price_cad=100.0,
            max_price_cad=250.0,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].auction_house, "A")

    def test_filters_by_sale_date_when_available(self):
        results = search_listings(
            self.listings,
            sale_date_from=date(2026, 10, 20),
            sale_date_to=date(2026, 10, 21),
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].sale_date, date(2026, 10, 20))

    def test_sorts_by_estimated_total(self):
        results = search_listings(
            self.listings,
            sort_by="Estimated total (CAD)",
            sort_desc=False,
        )
        self.assertEqual(results[0].item, "Blue porcelain vase")

    def test_relevance_sort_prioritizes_keyword_density(self):
        listings = self.listings + [
            AuctionListing(
                item="Porcelain porcelain statue",
                description="Porcelain details",
                category="Porcelain",
                auction_house="D",
                status="Active",
                price_cad=210.0,
                buyer_premium_percent=20.0,
                shipping_cad=25.0,
            )
        ]
        results = search_listings(
            listings,
            keyword="porcelain",
            sort_by="Relevance",
        )
        self.assertEqual(results[0].auction_house, "D")

    def test_select_top_listings_limits_count(self):
        results = select_top_listings_for_internet_report(
            listings=self.listings,
            keyword="porcelain",
            limit=2,
        )
        self.assertEqual(len(results), 2)

    def test_select_top_listings_prefers_image_match_when_scores_close(self):
        listings = [
            AuctionListing(
                item="Antique vase",
                description="Hand painted antique",
                category="Porcelain",
                auction_house="A",
                status="Active",
                price_cad=200.0,
                buyer_premium_percent=20.0,
                shipping_cad=20.0,
                source_record_id="a",
            ),
            AuctionListing(
                item="Antique vase",
                description="Hand painted antique",
                category="Porcelain",
                auction_house="B",
                status="Active",
                price_cad=200.0,
                buyer_premium_percent=20.0,
                shipping_cad=20.0,
                source_record_id="b",
            ),
        ]

        results = select_top_listings_for_internet_report(
            listings=listings,
            keyword="antique",
            image_match_distances={"b": 4},
            limit=1,
        )
        self.assertEqual(results[0].source_record_id, "b")


if __name__ == "__main__":
    unittest.main()
