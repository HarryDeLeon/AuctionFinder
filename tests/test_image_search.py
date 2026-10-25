import unittest
from unittest.mock import patch

from PIL import Image

from image_search import filter_listings_by_image
from models import AuctionListing


class ImageSearchTests(unittest.TestCase):
    def _solid_image_bytes(self, color: tuple[int, int, int]) -> bytes:
        import io

        image = Image.new("RGB", (32, 32), color=color)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _checker_image_bytes(self) -> bytes:
        import io

        image = Image.new("RGB", (32, 32), color=(255, 255, 255))
        pixels = image.load()
        for x in range(32):
            for y in range(32):
                if (x + y) % 2 == 0:
                    pixels[x, y] = (0, 0, 0)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_filters_listings_by_visual_similarity(self):
        listings = [
            AuctionListing(
                item="Red vase",
                category="Porcelain",
                auction_house="House A",
                status="Active",
                price_cad=100.0,
                buyer_premium_percent=20.0,
                shipping_cad=15.0,
                image_url="https://example.com/red.png",
                source_record_id="1",
            ),
            AuctionListing(
                item="Blue vase",
                category="Porcelain",
                auction_house="House B",
                status="Active",
                price_cad=110.0,
                buyer_premium_percent=20.0,
                shipping_cad=15.0,
                image_url="https://example.com/blue.png",
                source_record_id="2",
            ),
        ]

        image_map = {
            "https://example.com/red.png": self._checker_image_bytes(),
            "https://example.com/blue.png": self._solid_image_bytes((0, 0, 255)),
        }

        def fake_fetch(url: str, user_agent: str = "AuctionFinderBot/0.1", timeout_seconds: float = 10.0) -> bytes:
            return image_map[url]

        with patch("image_search._fetch_image_bytes", side_effect=fake_fetch):
            filtered, distances = filter_listings_by_image(
                listings,
                self._checker_image_bytes(),
                max_hamming_distance=0,
            )

        self.assertEqual(len(filtered), 1)
        self.assertIn("1", distances)
        self.assertNotIn("2", distances)


if __name__ == "__main__":
    unittest.main()
