from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping

from loader import DatasetLoadError, load_output_rows
from cashflow import detect_recurrences, simulate_cashflow
from evidence import resolve_image_amounts
from models import (
    ALLOWED_AFFORDABILITY_STATUSES,
    ALLOWED_PAYMENT_METHODS,
    OutputRow,
    Request,
    DatasetBundle,
)


PAYMENT_ENTRY_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}):(?P<amount>\d+(?:\.\d+)?)$"
)
SPENDING_CHANGE_PATTERN = re.compile(
    r"^(?:stop:[^:|]+|reduce_to:[^:|]+:\d+(?:\.\d+)?)$"
)


class OutputValidationError(ValueError):
    def __init__(self, issues: Iterable[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("\n".join(self.issues))


def _validate_plan(row: OutputRow, request: Request, issues: list[str]) -> None:
    prefix = row.request_id
    if row.payment_plan == "none":
        if row.recommended_payment_method != "not_recommended":
            issues.append(f"{prefix}: payment_plan cannot be none for a recommendation")
        return

    if row.recommended_payment_method == "not_recommended":
        issues.append(f"{prefix}: not_recommended must use payment_plan none")
        return

    previous_date = None
    for entry in row.payment_plan.split("|"):
        match = PAYMENT_ENTRY_PATTERN.fullmatch(entry)
        if not match:
            issues.append(f"{prefix}: invalid payment-plan entry {entry!r}")
            return
        try:
            payment_date = request.request_date.fromisoformat(match.group("date"))
            amount = Decimal(match.group("amount"))
        except (InvalidOperation, ValueError):
            issues.append(f"{prefix}: invalid payment-plan entry {entry!r}")
            return
        if amount <= 0:
            issues.append(f"{prefix}: payment amounts must be positive")
        if payment_date < request.request_date:
            issues.append(f"{prefix}: payment date precedes request_date")
        if payment_date > request.desired_completion_date:
            issues.append(f"{prefix}: payment date exceeds desired_completion_date")
        if previous_date is not None and payment_date < previous_date:
            issues.append(f"{prefix}: payment_plan is not chronological")
        previous_date = payment_date


def _parsed_plan(row: OutputRow) -> tuple[tuple[date, Decimal], ...]:
    if row.payment_plan == "none":
        return ()
    parsed: list[tuple[date, Decimal]] = []
    for entry in row.payment_plan.split("|"):
        match = PAYMENT_ENTRY_PATTERN.fullmatch(entry)
        if match is None:
            return ()
        try:
            parsed.append((date.fromisoformat(match.group("date")), Decimal(match.group("amount"))))
        except (InvalidOperation, ValueError):
            return ()
    return tuple(parsed)


def _spending_change_amounts(row: OutputRow) -> dict[str, Decimal]:
    if row.spending_changes_needed == "none":
        return {}
    changes: dict[str, Decimal] = {}
    for change in row.spending_changes_needed.split("|"):
        parts = change.split(":")
        if len(parts) == 2 and parts[0] == "stop":
            changes[parts[1]] = Decimal("0")
        elif len(parts) == 3 and parts[0] == "reduce_to":
            try:
                changes[parts[1]] = Decimal(parts[2])
            except InvalidOperation:
                continue
    return changes


def _validate_decision_semantics(
    row: OutputRow,
    request: Request,
    bundle: DatasetBundle,
    issues: list[str],
    evidence_entries: tuple[object, ...] = (),
) -> None:
    plan = _parsed_plan(row)
    prefix = row.request_id
    if row.recommended_payment_method == "full_payment":
        if row.affordability_status not in {"affordable_now", "affordable_with_plan"}:
            issues.append(
                f"{prefix}: full_payment requires affordable_now or affordable_with_plan"
            )
        if plan != ((request.request_date, request.requested_amount),):
            issues.append(f"{prefix}: full_payment plan must pay the request today")
    elif row.recommended_payment_method == "wait":
        if row.affordability_status != "affordable_later":
            issues.append(f"{prefix}: wait requires affordable_later")
        if len(plan) != 1 or plan[0][1] != request.requested_amount:
            issues.append(f"{prefix}: wait plan must contain the full request amount")
    elif row.recommended_payment_method == "partial_payment":
        if row.affordability_status != "affordable_with_plan":
            issues.append(f"{prefix}: partial_payment requires affordable_with_plan")
        if not request.allows_partial_payment or len(plan) != 2:
            issues.append(f"{prefix}: partial payment requires exactly two payments")
        elif (
            plan[0][0] != request.request_date
            or plan[0][1] != row.amount_safe_to_pay
            or plan[1][1] != request.requested_amount - row.amount_safe_to_pay
            or plan[0][1] <= 0
            or plan[0][1] >= request.requested_amount
            or plan[1][0] > request.desired_completion_date
        ):
            issues.append(f"{prefix}: partial payment arithmetic or dates are invalid")
    elif row.recommended_payment_method == "installments":
        if row.affordability_status != "affordable_with_plan":
            issues.append(f"{prefix}: installments requires affordable_with_plan")
        matching = []
        for option in bundle.payment_options:
            if option.request_id != request.request_id or option.payment_method != "installments":
                continue
            option_dates = tuple(
                option.first_payment_date
                + timedelta(days=index * (option.payment_frequency_days or 0))
                for index in range(option.number_of_payments)
            )
            if plan == tuple(zip(option_dates, [option.payment_amount] * option.number_of_payments)):
                matching.append(option)
        if not matching:
            issues.append(f"{prefix}: installment plan does not match a supplied option")

    if row.recommended_payment_method in {"full_payment", "partial_payment", "installments", "wait"}:
        profile = next((item for item in bundle.financial_profiles if item.user_id == request.user_id), None)
        if profile is not None and plan:
            from models import CashFlowEntry
            from evidence import reconcile_events_with_messages

            entries = tuple(
                CashFlowEntry(
                    date=payment_date,
                    amount=-amount,
                    source_id=request.request_id,
                    source_type="request_payment",
                    description="validated output payment",
                )
                for payment_date, amount in plan
            )
            raw_events = tuple(event for event in bundle.financial_events if event.user_id == request.user_id)
            user_events, message_extra_entries = reconcile_events_with_messages(
                raw_events,
                bundle.messages,
                request.user_id,
                request.request_id,
                request.request_date,
            )
            seen_entry_keys = set()
            all_evidence = []
            for entry in (*evidence_entries, *message_extra_entries):
                key = (entry.date, entry.source_id, entry.amount)
                if key not in seen_entry_keys:
                    seen_entry_keys.add(key)
                    all_evidence.append(entry)

            result = simulate_cashflow(
                profile,
                request,
                user_events,
                bundle.exchange_rates,
                additional_entries=(*all_evidence, *entries),
                spending_changes=_spending_change_amounts(row),
                resolved_amounts=resolve_image_amounts(
                    bundle.images, Path("dataset") / "media" / "images"
                )[0],
            )
            if not result.is_safe:
                issues.append(f"{prefix}: payment plan violates minimum balance safety")


def _validate_spending_permissions(
    row: OutputRow, request: Request, bundle: DatasetBundle, issues: list[str]
) -> None:
    if row.spending_changes_needed == "none":
        return
    profile = next((item for item in bundle.financial_profiles if item.user_id == request.user_id), None)
    if profile is None:
        issues.append(f"{row.request_id}: spending changes require a financial profile")
        return
    from evidence import reconcile_events_with_messages

    raw_events = tuple(event for event in bundle.financial_events if event.user_id == request.user_id)
    user_events, _ = reconcile_events_with_messages(
        raw_events,
        bundle.messages,
        request.user_id,
        request.request_id,
        request.request_date,
    )
    recurring_ids = {item.source_event_id for item in detect_recurrences(user_events, request.user_id, request.request_date)}
    seen: set[str] = set()
    for change in row.spending_changes_needed.split("|"):
        parts = change.split(":")
        event_id = parts[1] if len(parts) > 1 else ""
        event = next((item for item in user_events if item.event_id == event_id), None)
        if event_id in seen:
            continue
        seen.add(event_id)
        if event is None or event_id not in recurring_ids:
            issues.append(f"{row.request_id}: spending change must target a recurring event")
            continue
        if event.category in profile.expense_categories_to_protect:
            issues.append(f"{row.request_id}: protected category cannot be changed")
        if parts[0] == "stop" and event.category not in profile.expense_categories_user_is_willing_to_stop:
            issues.append(f"{row.request_id}: user does not permit stopping {event_id}")
        if parts[0] == "reduce_to" and event.category not in profile.expense_categories_user_is_willing_to_reduce:
            issues.append(f"{row.request_id}: user does not permit reducing {event_id}")


def _validate_spending_changes(row: OutputRow, issues: list[str]) -> None:
    if row.spending_changes_needed == "none":
        return
    changes = row.spending_changes_needed.split("|")
    if len(changes) > 3:
        issues.append(f"{row.request_id}: at most three spending changes are allowed")
    event_ids: set[str] = set()
    for change in changes:
        if not SPENDING_CHANGE_PATTERN.fullmatch(change):
            issues.append(f"{row.request_id}: invalid spending change {change!r}")
            continue
        event_id = change.split(":")[1]
        if event_id in event_ids:
            issues.append(
                f"{row.request_id}: an event cannot have multiple spending changes"
            )
        event_ids.add(event_id)


def validate_output_rows(
    rows: Iterable[OutputRow], requests: Iterable[Request]
) -> tuple[str, ...]:
    output_rows = tuple(rows)
    expected_requests = tuple(requests)
    request_by_id: Mapping[str, Request] = {
        request.request_id: request for request in expected_requests
    }
    issues: list[str] = []
    seen: set[str] = set()

    for row in output_rows:
        if row.request_id in seen:
            issues.append(f"duplicate request_id: {row.request_id}")
            continue
        seen.add(row.request_id)
        request = request_by_id.get(row.request_id)
        if request is None:
            issues.append(f"unknown request_id: {row.request_id}")
            continue

        if row.amount_safe_to_pay < 0 or row.amount_safe_to_pay > request.requested_amount:
            issues.append(
                f"{row.request_id}: amount_safe_to_pay must be between 0 and "
                f"{request.requested_amount}"
            )
        if row.affordability_status not in ALLOWED_AFFORDABILITY_STATUSES:
            issues.append(f"{row.request_id}: invalid affordability_status")
        if row.recommended_payment_method not in ALLOWED_PAYMENT_METHODS:
            issues.append(f"{row.request_id}: invalid recommended_payment_method")

        if row.earliest_date_for_full_payment is not None:
            forecast_end = request.request_date + timedelta(days=89)
            if not request.request_date <= row.earliest_date_for_full_payment <= forecast_end:
                issues.append(
                    f"{row.request_id}: earliest_date_for_full_payment is outside "
                    "the 90-day forecast"
                )

        if row.affordability_status == "affordable_now":
            if row.recommended_payment_method != "full_payment":
                issues.append(f"{row.request_id}: affordable_now requires full_payment")
            if row.earliest_date_for_full_payment != request.request_date:
                issues.append(
                    f"{row.request_id}: affordable_now earliest date must equal request_date"
                )
        elif row.affordability_status == "affordable_later":
            if row.recommended_payment_method != "wait":
                issues.append(f"{row.request_id}: affordable_later requires wait")
            if row.earliest_date_for_full_payment is None:
                issues.append(f"{row.request_id}: affordable_later requires an earliest date")
        elif row.affordability_status == "not_affordable":
            if row.recommended_payment_method != "not_recommended":
                issues.append(
                    f"{row.request_id}: not_affordable requires not_recommended"
                )
            if row.earliest_date_for_full_payment is not None:
                issues.append(
                    f"{row.request_id}: not_affordable earliest date must be blank"
                )

        if not row.decision_explanation.strip():
            issues.append(f"{row.request_id}: decision_explanation cannot be blank")
        _validate_plan(row, request, issues)
        _validate_spending_changes(row, issues)

    expected_ids = set(request_by_id)
    missing = sorted(expected_ids - seen)
    if missing:
        issues.append(f"missing request_ids: {', '.join(missing)}")
    actual_order = tuple(row.request_id for row in output_rows)
    expected_order = tuple(request.request_id for request in expected_requests)
    if len(actual_order) == len(expected_order) and actual_order != expected_order:
        issues.append("output rows must follow requests.csv order")
    return tuple(issues)


def validate_decision_rows(
    rows: Iterable[OutputRow],
    bundle: DatasetBundle,
    evidence_entries_by_request: Mapping[str, tuple[object, ...]] | None = None,
    resolved_amounts: dict[str, Decimal] | None = None,
) -> tuple[str, ...]:
    issues = list(validate_output_rows(rows, bundle.requests))
    requests_by_id = {request.request_id: request for request in bundle.requests}
    for row in rows:
        request = requests_by_id.get(row.request_id)
        if request is None:
            continue
        _validate_decision_semantics(
            row,
            request,
            bundle,
            issues,
            (evidence_entries_by_request or {}).get(row.request_id, ()),
        )
        _validate_spending_permissions(row, request, bundle, issues)
    return tuple(issues)


def validate_output_file(
    path: Path,
    requests: Iterable[Request],
    bundle: DatasetBundle | None = None,
    evidence_entries_by_request: Mapping[str, tuple[object, ...]] | None = None,
) -> None:
    try:
        rows = load_output_rows(path)
    except DatasetLoadError as error:
        raise OutputValidationError((str(error),)) from error
    issues = (
        validate_decision_rows(rows, bundle, evidence_entries_by_request)
        if bundle is not None
        else validate_output_rows(rows, requests)
    )
    if issues:
        raise OutputValidationError(issues)
