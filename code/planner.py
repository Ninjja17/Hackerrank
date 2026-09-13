from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR
from itertools import combinations
from pathlib import Path
from typing import Iterable

from cashflow import earliest_safe_date, safe_amount_today, simulate_cashflow
from evidence import reconcile_events_with_messages, resolve_image_amounts
from models import (
    CashFlowEntry,
    DatasetBundle,
    FinancialEvent,
    FinancialProfile,
    OutputRow,
    PaymentOption,
    Request,
)


@dataclass(frozen=True, slots=True)
class PlanCandidate:
    row: OutputRow
    completes_by_deadline: bool
    spending_changes: int
    total_paid: Decimal
    start_date: date
    payment_count: int
    payment_option_id: str


def _payment_entries(
    request: Request, option: PaymentOption
) -> tuple[CashFlowEntry, ...]:
    interval = option.payment_frequency_days or 0
    return tuple(
        CashFlowEntry(
            date=option.first_payment_date + timedelta(days=index * interval),
            amount=-option.payment_amount,
            source_id=option.payment_option_id,
            source_type="request_payment",
            description="supplied payment option",
            display_amount=option.payment_amount_text,
        )
        for index in range(option.number_of_payments)
    )


def _plan_string(entries: Iterable[CashFlowEntry]) -> str:
    parts = []
    for entry in entries:
        amt = -entry.amount
        display = entry.display_amount
        if display:
            if "." in display and len(display.split(".")[1]) == 1:
                display = f"{display}0"
        else:
            if amt == amt.to_integral():
                display = str(int(amt))
            else:
                display = f"{amt:.2f}"
        parts.append(f"{entry.date.isoformat()}:{display}")
    return "|".join(parts)


def _safe_plan(
    profile: FinancialProfile,
    request: Request,
    events: tuple[FinancialEvent, ...],
    bundle: DatasetBundle,
    entries: tuple[CashFlowEntry, ...],
    resolved_amounts: dict[str, Decimal],
    spending_changes: dict[str, Decimal] | None = None,
    evidence_entries: tuple[CashFlowEntry, ...] = (),
) -> bool:
    result = simulate_cashflow(
        profile,
        request,
        events,
        bundle.exchange_rates,
        additional_entries=(*evidence_entries, *entries),
        resolved_amounts=resolved_amounts,
        spending_changes=spending_changes,
    )
    return result.is_safe and all(
        entry.date <= request.desired_completion_date for entry in entries
    )


def _candidate(
    request: Request,
    amount_safe: Decimal,
    status: str,
    method: str,
    entries: tuple[CashFlowEntry, ...],
    earliest: date | None,
    explanation: str,
    *,
    option_id: str = "",
    spending_changes: str = "none",
    spending_change_count: int = 0,
) -> PlanCandidate:
    return PlanCandidate(
        row=OutputRow(
            request_id=request.request_id,
            amount_safe_to_pay=amount_safe,
            affordability_status=status,
            recommended_payment_method=method,
            payment_plan=_plan_string(entries) if entries else "none",
            earliest_date_for_full_payment=earliest,
            spending_changes_needed=spending_changes,
            decision_explanation=explanation,
        ),
        completes_by_deadline=bool(entries)
        and all(entry.date <= request.desired_completion_date for entry in entries),
        spending_changes=spending_change_count,
        total_paid=sum((-entry.amount for entry in entries), Decimal("0")),
        start_date=entries[0].date if entries else request.request_date,
        payment_count=len(entries),
        payment_option_id=option_id,
    )


def _ranking_key(candidate: PlanCandidate) -> tuple[object, ...]:
    return (
        not candidate.completes_by_deadline,
        candidate.spending_changes,
        candidate.total_paid,
        candidate.start_date,
        candidate.payment_count,
        candidate.payment_option_id,
    )


def decide_request(
    bundle: DatasetBundle,
    request: Request,
    evidence_entries: tuple[CashFlowEntry, ...] = (),
    resolved_amounts: dict[str, Decimal] | None = None,
) -> OutputRow:
    profile = next(
        (item for item in bundle.financial_profiles if item.user_id == request.user_id),
        None,
    )
    if profile is None:
        return _fallback(request, "No financial profile was found.")

    raw_user_events = tuple(
        event for event in bundle.financial_events if event.user_id == request.user_id
    )
    user_events, message_extra_entries = reconcile_events_with_messages(
        raw_user_events,
        bundle.messages,
        request.user_id,
        request.request_id,
        request.request_date,
    )
    seen_entry_keys = set()
    unique_evidence = []
    for entry in (*evidence_entries, *message_extra_entries):
        key = (entry.date, entry.source_id, entry.amount)
        if key not in seen_entry_keys:
            seen_entry_keys.add(key)
            unique_evidence.append(entry)
    all_evidence = tuple(unique_evidence)


    if resolved_amounts is None:
        resolved_amounts, _, _ = resolve_image_amounts(
            bundle.images, Path("dataset") / "media" / "images"
        )
    baseline = simulate_cashflow(
        profile,
        request,
        user_events,
        bundle.exchange_rates,
        additional_entries=all_evidence,
        resolved_amounts=resolved_amounts,
    )
    amount_safe = safe_amount_today(baseline, request.requested_amount)
    amount_safe = amount_safe.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
    if amount_safe == amount_safe.to_integral():
        amount_safe = amount_safe.quantize(Decimal("1"))
    earliest = earliest_safe_date(baseline, request.requested_amount)
    methods = set(profile.payment_methods_user_will_consider)
    candidates: list[PlanCandidate] = []

    flexible_changes = _permitted_single_changes(
        profile, user_events, request, bundle.exchange_rates
    )
    flexible_combinations = _change_combinations(flexible_changes)

    if "full_payment" in methods:
        full_entries = (
            CashFlowEntry(
                date=request.request_date,
                amount=-request.requested_amount,
                source_id=request.request_id,
                source_type="request_payment",
                description="full payment",
                display_amount=request.requested_amount_text or None,
            ),
        )
        if _safe_plan(
            profile, request, user_events, bundle, full_entries, resolved_amounts,
            evidence_entries=all_evidence,
        ):
            candidates.append(
                _candidate(
                    request,
                    amount_safe,
                    "affordable_now",
                    "full_payment",
                    full_entries,
                    request.request_date,
                    f"Pay {request.requested_amount} {profile.home_currency} today; "
                    f"the projected balance remains at or above "
                    f"{profile.minimum_balance_to_keep} {profile.home_currency}.",
                )
            )
        for change_group in flexible_combinations:
            change_amounts = {item[0]: item[1] for item in change_group}
            change_text = "|".join(item[2] for item in change_group)
            if _safe_plan(
                profile,
                request,
                user_events,
                bundle,
                full_entries,
                resolved_amounts,
                change_amounts,
                evidence_entries=all_evidence,
            ):
                candidates.append(
                    _candidate(
                        request,
                        amount_safe,
                        "affordable_with_plan",
                        "full_payment",
                        full_entries,
                        earliest,
                        f"Pay {request.requested_amount} {profile.home_currency} today "
                        f"after {change_text}; the projected balance remains at or "
                        f"above {profile.minimum_balance_to_keep} {profile.home_currency}.",
                        spending_changes=change_text,
                        spending_change_count=len(change_group),
                    )
                )

    if "installments" in methods:
        for option in sorted(
            (item for item in bundle.payment_options if item.request_id == request.request_id),
            key=lambda item: item.payment_option_id,
        ):
            if option.payment_method != "installments":
                continue
            if profile.max_installment_months is not None and (
                option.number_of_payments > profile.max_installment_months
            ):
                continue
            entries = _payment_entries(request, option)
            if _safe_plan(
                profile, request, user_events, bundle, entries, resolved_amounts,
                evidence_entries=all_evidence,
            ):
                candidates.append(
                    _candidate(
                        request,
                        amount_safe,
                        "affordable_with_plan",
                        "installments",
                        entries,
                        earliest,
                        f"Use the supplied {option.number_of_payments}-payment plan in "
                        f"{profile.home_currency}; total payable is "
                        f"{option.total_payable_amount} including fees.",
                        option_id=option.payment_option_id,
                    )
                )
            for change_group in flexible_combinations:
                change_amounts = {item[0]: item[1] for item in change_group}
                change_text = "|".join(item[2] for item in change_group)
                if _safe_plan(
                    profile,
                    request,
                    user_events,
                    bundle,
                    entries,
                    resolved_amounts,
                    change_amounts,
                    evidence_entries=all_evidence,
                ):
                    candidates.append(
                        _candidate(
                            request,
                            amount_safe,
                            "affordable_with_plan",
                            "installments",
                            entries,
                            earliest,
                            f"Use the supplied {option.number_of_payments}-payment "
                            f"plan after {change_text}; total payable is "
                            f"{option.total_payable_amount} including fees.",
                            option_id=option.payment_option_id,
                            spending_changes=change_text,
                            spending_change_count=len(change_group),
                        )
                    )

    if (
        request.allows_partial_payment
        and "partial_payment" in methods
        and amount_safe > 0
        and amount_safe < request.requested_amount
        and earliest is not None
        and earliest <= request.desired_completion_date
    ):
        rem = request.requested_amount - amount_safe
        p0_str = str(int(amount_safe)) if amount_safe == amount_safe.to_integral() else f"{amount_safe:.2f}"
        p1_str = str(int(rem)) if rem == rem.to_integral() else f"{rem:.2f}"
        partial_entries = (
            CashFlowEntry(
                date=request.request_date,
                amount=-amount_safe,
                source_id=request.request_id,
                source_type="request_payment",
                description="partial payment",
                display_amount=p0_str,
            ),
            CashFlowEntry(
                date=earliest,
                amount=-rem,
                source_id=request.request_id,
                source_type="request_payment",
                description="partial payment remainder",
                display_amount=p1_str,
            ),
        )
        if _safe_plan(
            profile, request, user_events, bundle, partial_entries, resolved_amounts,
            evidence_entries=all_evidence,
        ):
            candidates.append(
                _candidate(
                    request,
                    amount_safe,
                    "affordable_with_plan",
                    "partial_payment",
                    partial_entries,
                    earliest,
                    f"Pay {p0_str} {profile.home_currency} today and the "
                    f"remaining balance on {earliest.isoformat()} while keeping at "
                    f"least {profile.minimum_balance_to_keep} {profile.home_currency}.",
                )
            )

    if (
        "full_payment" in methods
        and earliest is not None
        and earliest > request.request_date
        and earliest <= request.desired_completion_date
    ):
        wait_entry = CashFlowEntry(
            date=earliest,
            amount=-request.requested_amount,
            source_id=request.request_id,
            source_type="request_payment",
            description="wait then pay in full",
            display_amount=request.requested_amount_text or None,
        )
        if _safe_plan(
            profile, request, user_events, bundle, (wait_entry,), resolved_amounts,
            evidence_entries=all_evidence,
        ):
            candidates.append(
                _candidate(
                    request,
                    amount_safe,
                    "affordable_later",
                    "wait",
                    (wait_entry,),
                    earliest,
                    f"Wait until {earliest.isoformat()} to pay "
                    f"{request.requested_amount} {profile.home_currency}; paying earlier "
                    f"would risk the minimum balance of {profile.minimum_balance_to_keep}.",
                )
            )

    if not candidates:
        return _fallback(
            request,
            f"No safe supported plan was found within the deadline and 90-day forecast "
            f"while maintaining {profile.minimum_balance_to_keep} {profile.home_currency}.",
            amount_safe=amount_safe,
        )
    return min(candidates, key=_ranking_key).row


def _permitted_single_changes(
    profile: FinancialProfile,
    events: tuple[FinancialEvent, ...],
    request: Request,
    rates: tuple[object, ...],
) -> tuple[tuple[str, Decimal, str], ...]:
    from cashflow import detect_recurrences

    recurrence_ids = {
        recurrence.source_event_id
        for recurrence in detect_recurrences(events, request.user_id, request.request_date)
    }
    changes: list[tuple[str, Decimal, str]] = []
    for event in events:
        if event.event_id not in recurrence_ids or event.category in profile.expense_categories_to_protect:
            continue
        if event.flexibility in {"stoppable", "reducible_or_stoppable"} and event.category in profile.expense_categories_user_is_willing_to_stop:
            changes.append((event.event_id, Decimal("0"), f"stop:{event.event_id}"))
        if event.flexibility in {"reducible", "reducible_or_stoppable"} and event.category in profile.expense_categories_user_is_willing_to_reduce:
            minimum = event.minimum_allowed_amount or Decimal("0")
            if event.amount is not None and minimum < event.amount:
                changes.append(
                    (
                        event.event_id,
                        minimum,
                        f"reduce_to:{event.event_id}:{format(minimum, 'f')}",
                    )
                )
    return tuple(changes)


def _change_combinations(
    changes: tuple[tuple[str, Decimal, str], ...],
) -> tuple[tuple[tuple[str, Decimal, str], ...], ...]:
    unique: dict[str, tuple[str, Decimal, str]] = {
        change[0]: change for change in changes
    }
    ordered = tuple(unique[event_id] for event_id in sorted(unique))
    combinations_to_test: list[tuple[tuple[str, Decimal, str], ...]] = []
    for size in range(1, min(3, len(ordered)) + 1):
        combinations_to_test.extend(combinations(ordered, size))
    return tuple(combinations_to_test)


def _fallback(
    request: Request,
    explanation: str,
    amount_safe: Decimal = Decimal("0"),
) -> OutputRow:
    amount_safe = amount_safe.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
    if amount_safe == amount_safe.to_integral():
        amount_safe = amount_safe.quantize(Decimal("1"))
    return OutputRow(
        request_id=request.request_id,
        amount_safe_to_pay=amount_safe,
        affordability_status="not_affordable",
        recommended_payment_method="not_recommended",
        payment_plan="none",
        earliest_date_for_full_payment=None,
        spending_changes_needed="none",
        decision_explanation=explanation,
    )


def decide_all(
    bundle: DatasetBundle,
    evidence_entries_by_request: dict[str, tuple[CashFlowEntry, ...]] | None = None,
    resolved_amounts: dict[str, Decimal] | None = None,
) -> tuple[OutputRow, ...]:
    rows: list[OutputRow] = []
    for request in bundle.requests:
        try:
            rows.append(
                decide_request(
                    bundle,
                    request,
                    (evidence_entries_by_request or {}).get(request.request_id, ()),
                    resolved_amounts,
                )
            )
        except Exception as error:  # one request must not stop the batch
            rows.append(
                _fallback(
                    request,
                    "No safe supported plan was found because required financial "
                    "evidence could not be verified.",
                )
            )
    return tuple(rows)

