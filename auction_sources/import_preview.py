from dataclasses import dataclass
from typing import List

from auction_sources.manual_csv_source import (
    ManualCsvAuctionSource,
    ManualCsvImportReport,
    ManualCsvRowError,
)
from auction_sources.normalization import normalize_source_record
from models import AuctionListing


@dataclass(frozen=True)
class ManualSourcePreviewResult:
    listings: List[AuctionListing]
    rejected_rows: List[ManualCsvRowError]
    rejected_rows_csv: str
    total_rows: int

    @property
    def valid_rows(self) -> int:
        return len(self.listings)


def _combine_errors_to_csv(
    report: ManualCsvImportReport,
    normalization_errors: List[ManualCsvRowError],
) -> str:
    merged_errors = report.errors + normalization_errors
    merged_report = ManualCsvImportReport(
        parsed_records=[],
        errors=merged_errors,
        fieldnames=report.fieldnames,
    )
    return merged_report.rejected_rows_to_csv()


def load_manual_source_csv_preview_with_report(
    csv_text: str,
    source_name: str = "manual_csv_preview",
) -> ManualSourcePreviewResult:
    source = ManualCsvAuctionSource(
        csv_text=csv_text,
        source_name=source_name,
    )
    report = source.load_records_with_report()

    listings: List[AuctionListing] = []
    normalization_errors: List[ManualCsvRowError] = []
    for parsed_record in report.parsed_records:
        try:
            listings.append(normalize_source_record(parsed_record.record))
        except ValueError as exc:
            normalization_errors.append(
                ManualCsvRowError(
                    row_number=parsed_record.row_number,
                    error_message=str(exc),
                    row_data=parsed_record.row_data,
                )
            )

    rejected_rows = report.errors + normalization_errors
    return ManualSourcePreviewResult(
        listings=listings,
        rejected_rows=rejected_rows,
        rejected_rows_csv=_combine_errors_to_csv(
            report,
            normalization_errors,
        ),
        total_rows=report.total_rows,
    )


def load_manual_source_csv_preview(
    csv_text: str,
    source_name: str = "manual_csv_preview",
) -> List[AuctionListing]:
    preview_result = load_manual_source_csv_preview_with_report(
        csv_text=csv_text,
        source_name=source_name,
    )
    if preview_result.rejected_rows:
        first_error = preview_result.rejected_rows[0]
        raise ValueError(
            f"Row {first_error.row_number}: {first_error.error_message}"
        )
    return preview_result.listings
