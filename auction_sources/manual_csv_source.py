import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Iterable, List

from auction_sources.base import AuctionSource, SourceRecord

REQUIRED_COLUMNS = [
    "source_record_id",
    "item_title",
    "category",
    "auction_house",
    "status",
    "price_cad",
    "buyer_premium_percent",
    "shipping_cad",
]


@dataclass(frozen=True)
class ManualCsvRowError:
    row_number: int
    error_message: str
    row_data: dict[str, str]


@dataclass(frozen=True)
class ParsedSourceRecord:
    row_number: int
    row_data: dict[str, str]
    record: SourceRecord


@dataclass(frozen=True)
class ManualCsvImportReport:
    parsed_records: List[ParsedSourceRecord]
    errors: List[ManualCsvRowError]
    fieldnames: List[str]

    @property
    def total_rows(self) -> int:
        return len(self.parsed_records) + len(self.errors)

    @property
    def valid_rows(self) -> int:
        return len(self.parsed_records)

    @property
    def rejected_rows(self) -> int:
        return len(self.errors)

    def records(self) -> List[SourceRecord]:
        return [parsed.record for parsed in self.parsed_records]

    def rejected_rows_to_csv(self) -> str:
        output = StringIO()
        headers = ["row_number", "error_message"] + self.fieldnames
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for error in self.errors:
            row: dict[str, str | int] = {
                "row_number": error.row_number,
                "error_message": error.error_message,
            }
            for field in self.fieldnames:
                row[field] = error.row_data.get(field, "")
            writer.writerow(row)
        return output.getvalue()


class ManualCsvAuctionSource(AuctionSource):
    def __init__(self, csv_text: str, source_name: str = "manual_csv"):
        self._csv_text = csv_text
        self._source_name = source_name

    @property
    def source_name(self) -> str:
        return self._source_name

    def load_records(self) -> Iterable[SourceRecord]:
        report = self.load_records_with_report()
        if report.errors:
            first_error = report.errors[0]
            raise ValueError(
                f"Row {first_error.row_number}: {first_error.error_message}"
            )
        return report.records()

    def load_records_with_report(self) -> ManualCsvImportReport:
        reader = csv.DictReader(StringIO(self._csv_text))
        if reader.fieldnames is None:
            raise ValueError("CSV must include a header row")
        missing = [
            column
            for column in REQUIRED_COLUMNS
            if column not in reader.fieldnames
        ]
        if missing:
            raise ValueError(
                "CSV missing required columns: " + ", ".join(missing)
            )

        parsed_records: List[ParsedSourceRecord] = []
        errors: List[ManualCsvRowError] = []
        for row_index, row in enumerate(reader, start=2):
            try:
                record = self._parse_row(row, row_index)
                parsed_records.append(
                    ParsedSourceRecord(
                        row_number=row_index,
                        row_data={field: row.get(field, "") for field in reader.fieldnames},
                        record=record,
                    )
                )
            except ValueError as exc:
                errors.append(
                    ManualCsvRowError(
                        row_number=row_index,
                        error_message=str(exc),
                        row_data={field: row.get(field, "") for field in reader.fieldnames},
                    )
                )

        return ManualCsvImportReport(
            parsed_records=parsed_records,
            errors=errors,
            fieldnames=list(reader.fieldnames),
        )

    def _parse_row(
        self,
        row: dict[str, str],
        row_index: int,
    ) -> SourceRecord:
        source_record_id = (row.get("source_record_id") or "").strip()
        item_title = (row.get("item_title") or "").strip()
        category = (row.get("category") or "").strip()
        auction_house = (row.get("auction_house") or "").strip()
        status = (row.get("status") or "").strip()
        if not source_record_id:
            raise ValueError("source_record_id is required")
        if not item_title:
            raise ValueError("item_title is required")
        if not category:
            raise ValueError("category is required")
        if not auction_house:
            raise ValueError("auction_house is required")
        if not status:
            raise ValueError("status is required")

        try:
            price_cad = float((row.get("price_cad") or "").strip())
            buyer_premium_percent = float(
                (row.get("buyer_premium_percent") or "").strip()
            )
            shipping_cad = float((row.get("shipping_cad") or "").strip())
        except ValueError as exc:
            raise ValueError(
                "price_cad, buyer_premium_percent, and shipping_cad must be numeric"
            ) from exc

        other_fees_text = (row.get("other_fees_cad") or "").strip()
        tax_text = (row.get("tax_percent") or "").strip()
        try:
            other_fees_cad = float(other_fees_text) if other_fees_text else 0.0
            tax_percent = float(tax_text) if tax_text else None
        except ValueError as exc:
            raise ValueError(
                "other_fees_cad and tax_percent must be numeric when provided"
            ) from exc

        return SourceRecord(
            source_name=self.source_name,
            source_record_id=source_record_id,
            item_title=item_title,
            category=category,
            auction_house=auction_house,
            status=status,
            price_cad=price_cad,
            buyer_premium_percent=buyer_premium_percent,
            shipping_cad=shipping_cad,
            other_fees_cad=other_fees_cad,
            tax_percent=tax_percent,
            description=(row.get("description") or "").strip(),
            location=(row.get("location") or "").strip() or None,
            listing_url=(row.get("listing_url") or "").strip() or None,
            lot_number=(row.get("lot_number") or "").strip() or None,
            sale_date_iso=(row.get("sale_date_iso") or "").strip() or None,
            collected_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_file(
        cls,
        file_path: Path,
        source_name: str = "manual_csv",
    ) -> "ManualCsvAuctionSource":
        text = file_path.read_text(encoding="utf-8")
        return cls(csv_text=text, source_name=source_name)
