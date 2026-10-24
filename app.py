
import pandas as pd
import streamlit as st

from pricing import calculate_estimated_cost
from sample_data import AUCTIONS


st.set_page_config(
    page_title="Antique Auction Finder",
    page_icon="🏺",
    layout="wide",
)

st.title("🏺 Antique Auction Price Finder")
st.write(
    "Compare antique listings and investigate "
    "potential bargains across auction houses."
)

st.info(
    "Prototype mode: all listings are fictional. "
    "No live auction data is connected."
)

# Search controls
search = st.text_input(
    "Search antiques",
    placeholder="Try vase, silver, painting...",
)

categories = ["All"] + sorted(
    {listing.category for listing in AUCTIONS}
)
category = st.selectbox("Category", categories)

status = st.selectbox(
    "Auction status",
    ["All", "Active", "Sold"],
)

# Filter the listings
filtered = []

for listing in AUCTIONS:
    if search.strip().lower() not in listing.item.lower():
        continue

    if category != "All" and listing.category != category:
        continue

    if status != "All" and listing.status != status:
        continue

    filtered.append(listing)

# Prepare the comparison table
rows = []

for listing in filtered:
    rows.append(
        {
            "Item": listing.item,
            "Category": listing.category,
            "Auction house": listing.auction_house,
            "Status": listing.status,
            "Listed / hammer price (CAD)": listing.price_cad,
            "Premium (%)": listing.buyer_premium_percent,
            "Shipping (CAD)": listing.shipping_cad,
            "Estimated total (CAD)": calculate_estimated_cost(
                listing
            ),
        }
    )

st.subheader("Auction listings")

col1, col2 = st.columns(2)

col1.metric("Matching listings", len(rows))

if rows:
    df = pd.DataFrame(rows).sort_values(
        "Estimated total (CAD)"
    )

    lowest = df["Estimated total (CAD)"].min()

    col2.metric("Lowest estimated total", f"${lowest:,.2f}")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.warning(
        "No matching listings. Try changing your search."
    )

st.caption(
    "Estimated totals include the displayed price, buyer premium, "
    "and shipping. Taxes are excluded. For active listings, "
    "the displayed price is the current bid, not a final sale price."
)
