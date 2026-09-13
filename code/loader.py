from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, TypeVar

from models import (
    OUTPUT_COLUMNS,
    DatasetBundle,
    ExchangeRate,
    FinancialEvent,
    FinancialProfile,
    ImageReference,
    Message,
    OutputRow,
    PaymentOption,
    Request,
    SampleRequest,
)


REQUEST_COLUMNS = (
    "request_id",
    "user_id",
    "request_date",
    "request_type",
    "requested_amount",
    "desired_completion_date",
    "allows_partial_payment",
    "request_text",
)
PROFILE_COLUMNS = (
    "user_id",
    "home_currency",
    "current_available_balance",
    "minimum_balance_to_keep",
    "financial_priorities",
    "expense_categories_to_protect",
    "expense_categories_user_is_willing_to_reduce",
    "expense_categories_user_is_willing_to_stop",
    "payment_methods_user_will_consider",
    "max_installment_months",
)
EVENT_COLUMNS = (
    "event_id",
    "user_id",
    "event_type",
    "description",
    "category",
    "direction",
    "amount",
    "currency",
    "event_date",
    "settlement_date",
    "status",
    "linked_event_id",
    "flexibility",
    "minimum_allowed_amount",
)
RATE_COLUMNS = ("rate_date", "from_currency", "to_currency", "rate")
PAYMENT_OPTION_COLUMNS = (
    "payment_option_id",
    "request_id",
    "payment_method",
    "payment_amount",
    "number_of_payments",
    "first_payment_date",
    "payment_frequency_days",
    "financing_fee",
    "total_payable_amount",
)
MESSAGE_COLUMNS = (
    "message_id",
    "user_id",
    "request_id",
    "related_event_id",
    "sent_at",
    "source_type",
    "message_text",
)
IMAGE_COLUMNS = ("image_id", "user_id", "request_id", "related_event_id")
SAMPLE_COLUMNS = REQUEST_COLUMNS + OUTPUT_COLUMNS[1:]


class DatasetLoadError(ValueError):
    pass


Row = dict[str, str]
T = TypeVar("T")


def _read_rows(path: Path, expected_columns: tuple[str, ...]) -> list[Row]:
    if not path.is_file():
        raise DatasetLoadError(f"Missing required CSV: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        actual_columns = tuple(reader.fieldnames or ())
        if actual_columns != expected_columns:
            raise DatasetLoadError(
                f"{path.name}: expected columns {expected_columns}, got {actual_columns}"
            )

        rows: list[Row] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise DatasetLoadError(f"{path.name}:{row_number}: too many fields")
            if any(value is None for value in row.values()):
                raise DatasetLoadError(f"{path.name}:{row_number}: missing field")
            rows.append({key: value.strip() for key, value in row.items()})
        return rows


def _parse_records(
    path: Path,
    columns: tuple[str, ...],
    parser: Callable[[Row], T],
) -> tuple[T, ...]:
    records: list[T] = []
    for row_number, row in enumerate(_read_rows(path, columns), start=2):
        try:
            records.append(parser(row))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise DatasetLoadError(f"{path.name}:{row_number}: {error}") from error
    return tuple(records)


def _decimal(value: str, field: str, *, optional: bool = False) -> Decimal | None:
    if value == "":
        if optional:
            return None
        raise ValueError(f"{field} cannot be blank")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _date(value: str, field: str, *, optional: bool = False) -> date | None:
    if value == "":
        if optional:
            return None
        raise ValueError(f"{field} cannot be blank")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD") from error


def _datetime(value: str, field: str) -> datetime:
    if not value:
        raise ValueError(f"{field} cannot be blank")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be ISO-8601") from error


def _integer(value: str, field: str, *, optional: bool = False) -> int | None:
    if value == "":
        if optional:
            return None
        raise ValueError(f"{field} cannot be blank")
    return int(value)


def _boolean(value: str, field: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{field} must be true or false")


def _optional_text(value: str) -> str | None:
    return value or None


def _pipe_values(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split("|") if part)


def _request(row: Row) -> Request:
    return Request(
        request_id=row["request_id"],
        user_id=row["user_id"],
        request_date=_required_date(row["request_date"], "request_date"),
        request_type=row["request_type"],
        requested_amount=_required_decimal(row["requested_amount"], "requested_amount"),
        desired_completion_date=_required_date(
            row["desired_completion_date"], "desired_completion_date"
        ),
        allows_partial_payment=_boolean(
            row["allows_partial_payment"], "allows_partial_payment"
        ),
        request_text=row["request_text"],
        requested_amount_text=row["requested_amount"],
    )


def _required_decimal(value: str, field: str) -> Decimal:
    parsed = _decimal(value, field)
    assert parsed is not None
    return parsed


def _required_date(value: str, field: str) -> date:
    parsed = _date(value, field)
    assert parsed is not None
    return parsed


def _required_integer(value: str, field: str) -> int:
    parsed = _integer(value, field)
    assert parsed is not None
    return parsed


def _output(row: Row) -> OutputRow:
    return OutputRow(
        request_id=row["request_id"],
        amount_safe_to_pay=_required_decimal(
            row["amount_safe_to_pay"], "amount_safe_to_pay"
        ),
        affordability_status=row["affordability_status"],
        recommended_payment_method=row["recommended_payment_method"],
        payment_plan=row["payment_plan"],
        earliest_date_for_full_payment=_date(
            row["earliest_date_for_full_payment"],
            "earliest_date_for_full_payment",
            optional=True,
        ),
        spending_changes_needed=row["spending_changes_needed"],
        decision_explanation=row["decision_explanation"],
    )


def load_output_rows(path: Path) -> tuple[OutputRow, ...]:
    return _parse_records(path, OUTPUT_COLUMNS, _output)


def load_dataset(dataset_dir: Path) -> DatasetBundle:
    profiles = _parse_records(
        dataset_dir / "financial_profiles.csv",
        PROFILE_COLUMNS,
        lambda row: FinancialProfile(
            user_id=row["user_id"],
            home_currency=row["home_currency"],
            current_available_balance=_required_decimal(
                row["current_available_balance"], "current_available_balance"
            ),
            minimum_balance_to_keep=_required_decimal(
                row["minimum_balance_to_keep"], "minimum_balance_to_keep"
            ),
            financial_priorities=_pipe_values(row["financial_priorities"]),
            expense_categories_to_protect=_pipe_values(
                row["expense_categories_to_protect"]
            ),
            expense_categories_user_is_willing_to_reduce=_pipe_values(
                row["expense_categories_user_is_willing_to_reduce"]
            ),
            expense_categories_user_is_willing_to_stop=_pipe_values(
                row["expense_categories_user_is_willing_to_stop"]
            ),
            payment_methods_user_will_consider=_pipe_values(
                row["payment_methods_user_will_consider"]
            ),
            max_installment_months=_integer(
                row["max_installment_months"],
                "max_installment_months",
                optional=True,
            ),
        ),
    )
    events = _parse_records(
        dataset_dir / "financial_events.csv",
        EVENT_COLUMNS,
        lambda row: FinancialEvent(
            event_id=row["event_id"],
            user_id=row["user_id"],
            event_type=row["event_type"],
            description=row["description"],
            category=row["category"],
            direction=row["direction"],
            amount=_decimal(row["amount"], "amount", optional=True),
            currency=row["currency"],
            event_date=_required_date(row["event_date"], "event_date"),
            settlement_date=_date(
                row["settlement_date"], "settlement_date", optional=True
            ),
            status=row["status"],
            linked_event_id=_optional_text(row["linked_event_id"]),
            flexibility=row["flexibility"],
            minimum_allowed_amount=_decimal(
                row["minimum_allowed_amount"],
                "minimum_allowed_amount",
                optional=True,
            ),
        ),
    )
    rates = _parse_records(
        dataset_dir / "exchange_rates.csv",
        RATE_COLUMNS,
        lambda row: ExchangeRate(
            rate_date=_required_date(row["rate_date"], "rate_date"),
            from_currency=row["from_currency"],
            to_currency=row["to_currency"],
            rate=_required_decimal(row["rate"], "rate"),
        ),
    )
    requests = _parse_records(dataset_dir / "requests.csv", REQUEST_COLUMNS, _request)
    samples = _parse_records(
        dataset_dir / "sample_requests.csv",
        SAMPLE_COLUMNS,
        lambda row: SampleRequest(request=_request(row), output=_output(row)),
    )
    options = _parse_records(
        dataset_dir / "request_payment_options.csv",
        PAYMENT_OPTION_COLUMNS,
        lambda row: PaymentOption(
            payment_option_id=row["payment_option_id"],
            request_id=row["request_id"],
            payment_method=row["payment_method"],
            payment_amount=_required_decimal(row["payment_amount"], "payment_amount"),
            number_of_payments=_required_integer(
                row["number_of_payments"], "number_of_payments"
            ),
            first_payment_date=_required_date(
                row["first_payment_date"], "first_payment_date"
            ),
            payment_frequency_days=_integer(
                row["payment_frequency_days"],
                "payment_frequency_days",
                optional=True,
            ),
            financing_fee=_required_decimal(row["financing_fee"], "financing_fee"),
            total_payable_amount=_required_decimal(
                row["total_payable_amount"], "total_payable_amount"
            ),
            payment_amount_text=row["payment_amount"],
        ),
    )
    messages = _parse_records(
        dataset_dir / "messages.csv",
        MESSAGE_COLUMNS,
        lambda row: Message(
            message_id=row["message_id"],
            user_id=row["user_id"],
            request_id=_optional_text(row["request_id"]),
            related_event_id=_optional_text(row["related_event_id"]),
            sent_at=_datetime(row["sent_at"], "sent_at"),
            source_type=row["source_type"],
            message_text=row["message_text"],
        ),
    )
    images = _parse_records(
        dataset_dir / "images.csv",
        IMAGE_COLUMNS,
        lambda row: ImageReference(
            image_id=row["image_id"],
            user_id=row["user_id"],
            request_id=_optional_text(row["request_id"]),
            related_event_id=_optional_text(row["related_event_id"]),
        ),
    )

    template_rows = _read_rows(dataset_dir / "output.csv", OUTPUT_COLUMNS)
    template_ids: list[str] = []
    for row_number, row in enumerate(template_rows, start=2):
        if not row["request_id"]:
            raise DatasetLoadError(f"output.csv:{row_number}: request_id cannot be blank")
        if any(row[column] for column in OUTPUT_COLUMNS[1:]):
            raise DatasetLoadError(
                f"output.csv:{row_number}: prediction columns must be blank"
            )
        template_ids.append(row["request_id"])

    return DatasetBundle(
        financial_profiles=profiles,
        financial_events=events,
        exchange_rates=rates,
        requests=requests,
        sample_requests=samples,
        payment_options=options,
        messages=messages,
        images=images,
        output_template_request_ids=tuple(template_ids),
    )


def dataset_summary(bundle: DatasetBundle) -> dict[str, object]:
    return {
        "financial_profiles": len(bundle.financial_profiles),
        "financial_events": len(bundle.financial_events),
        "exchange_rates": len(bundle.exchange_rates),
        "requests": len(bundle.requests),
        "sample_requests": len(bundle.sample_requests),
        "payment_options": len(bundle.payment_options),
        "messages": len(bundle.messages),
        "images": len(bundle.images),
        "output_template_rows": len(bundle.output_template_request_ids),
        "currencies": tuple(
            sorted({profile.home_currency for profile in bundle.financial_profiles})
        ),
        "request_date_range": (
            min(request.request_date for request in bundle.requests).isoformat(),
            max(request.request_date for request in bundle.requests).isoformat(),
        ),
    }
