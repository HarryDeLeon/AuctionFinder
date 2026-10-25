from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List

from auction_sources.liveauctionworld_html_source import LiveAuctionWorldHtmlAdapter
from models import AuctionListing
from repositories import (
    DEFAULT_DB_PATH,
    complete_crawl_run,
    create_crawl_run,
    get_source_config,
    upsert_ingested_listing,
)


@dataclass(frozen=True)
class CrawlSummary:
    source_config_id: int
    run_id: int
    status: str
    discovered_count: int
    inserted_count: int
    updated_count: int
    rejected_count: int
    error_summary: str | None


class DummyAuctionSourceAdapter:
    def crawl_latest(self, source_config: Dict[str, object]) -> List[AuctionListing]:
        source_name = str(source_config["name"])
        source_id = int(source_config["id"])
        day_key = date.today().isoformat()
        return [
            AuctionListing(
                item=f"Dummy listing from {source_name}",
                category="Other",
                auction_house=source_name,
                status="Active",
                price_cad=100.0,
                buyer_premium_percent=20.0,
                shipping_cad=15.0,
                description="Skeleton crawler output for pipeline validation.",
                listing_url=str(source_config["base_url"]),
                source_name=source_name,
                source_record_id=f"dummy-{source_id}-{day_key}",
            )
        ]


ADAPTER_REGISTRY = {
    "dummy": DummyAuctionSourceAdapter(),
    "html": LiveAuctionWorldHtmlAdapter(),
}


def run_source_crawl(
    source_config_id: int,
    db_path: Path = DEFAULT_DB_PATH,
) -> CrawlSummary:
    source_config = get_source_config(source_config_id, db_path=db_path)
    if source_config is None:
        raise ValueError(f"Source config id {source_config_id} was not found")

    run_id = create_crawl_run(source_config_id=source_config_id, db_path=db_path)
    discovered_count = 0
    inserted_count = 0
    updated_count = 0
    rejected_count = 0

    source_type = str(source_config["source_type"]).strip().lower()
    adapter = ADAPTER_REGISTRY.get(source_type)
    if adapter is None:
        error_summary = f"No adapter is registered for source_type='{source_type}'."
        complete_crawl_run(
            run_id=run_id,
            status="failed",
            discovered_count=0,
            inserted_count=0,
            updated_count=0,
            rejected_count=0,
            error_summary=error_summary,
            db_path=db_path,
        )
        return CrawlSummary(
            source_config_id=source_config_id,
            run_id=run_id,
            status="failed",
            discovered_count=0,
            inserted_count=0,
            updated_count=0,
            rejected_count=0,
            error_summary=error_summary,
        )

    try:
        listings = adapter.crawl_latest(source_config)
        discovered_count = len(listings)
        for listing in listings:
            result = upsert_ingested_listing(
                source_config_id=source_config_id,
                listing=listing,
                raw_url=listing.listing_url,
                db_path=db_path,
            )
            if result == "inserted":
                inserted_count += 1
            else:
                updated_count += 1
        status = "success"
        error_summary = None
    except ValueError as exc:
        rejected_count += 1
        status = "partial"
        error_summary = str(exc)
    except Exception as exc:
        status = "failed"
        error_summary = f"Unexpected crawl failure: {exc}"

    complete_crawl_run(
        run_id=run_id,
        status=status,
        discovered_count=discovered_count,
        inserted_count=inserted_count,
        updated_count=updated_count,
        rejected_count=rejected_count,
        error_summary=error_summary,
        db_path=db_path,
    )
    return CrawlSummary(
        source_config_id=source_config_id,
        run_id=run_id,
        status=status,
        discovered_count=discovered_count,
        inserted_count=inserted_count,
        updated_count=updated_count,
        rejected_count=rejected_count,
        error_summary=error_summary,
    )
