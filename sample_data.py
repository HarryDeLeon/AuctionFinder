from models import AuctionListing


AUCTIONS = [
    AuctionListing(
        item="Blue and white porcelain vase",
        category="Porcelain",
        auction_house="Demo Auction House A",
        status="Sold",
        price_cad=420.00,
        buyer_premium_percent=20,
        shipping_cad=35.00,
    ),
    AuctionListing(
        item="Antique decorative vase",
        category="Porcelain",
        auction_house="Demo Auction House B",
        status="Active",
        price_cad=275.00,
        buyer_premium_percent=22,
        shipping_cad=40.00,
    ),
    AuctionListing(
        item="Vintage silver serving bowl",
        category="Silver",
        auction_house="Demo Auction House C",
        status="Sold",
        price_cad=310.00,
        buyer_premium_percent=18,
        shipping_cad=25.00,
    ),
    AuctionListing(
        item="Landscape oil painting",
        category="Art",
        auction_house="Demo Auction House A",
        status="Active",
        price_cad=650.00,
        buyer_premium_percent=20,
        shipping_cad=60.00,
    ),
    AuctionListing(
        item="Vintage porcelain vase",
        category="Porcelain",
        auction_house="Demo Auction House C",
        status="Sold",
        price_cad=195.00,
        buyer_premium_percent=18,
        shipping_cad=30.00,
    ),
]