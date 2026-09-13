from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Iterable

from models import (
    CashFlowEntry,
    ExchangeRate,
    FinancialEvent,
    FinancialProfile,
    Request,
    SimulationResult,
)


class CurrencyConversionError(ValueError):
    pass


class MissingEventAmountError(ValueError):
    pass


RECURRING_EVENT_TYPES = frozenset({"subscription", "debt_payment"})
RECURRING_EXPENSE_CATEGORIES = frozenset(
    {"rent", "housing", "utilities", "insurance", "education"}
)


def _add_months(d: date, n: int) -> date:
    import calendar
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True, slots=True)
class Recurrence:
    user_id: str
    category: str
    direction: str
    amount: Decimal
    currency: str
    interval_days: int
    next_date: date
    description: str
    source_event_id: str
    is_monthly: bool = False
    latest_event_date: date = date.min


class CurrencyConverter:
    def __init__(self, rates: Iterable[ExchangeRate]) -> None:
        self._rates = {
            (rate.rate_date, rate.from_currency, rate.to_currency): rate.rate
            for rate in rates
        }

    def convert(
        self, amount: Decimal, from_currency: str, to_currency: str, on_date: date
    ) -> Decimal:
        if from_currency == to_currency:
            return amount
        direct = self._rates.get((on_date, from_currency, to_currency))
        if direct is not None:
            return amount * direct
        reverse = self._rates.get((on_date, to_currency, from_currency))
        if reverse is not None and reverse != 0:
            return amount / reverse
        raise CurrencyConversionError(
            f"No exchange rate for {from_currency}->{to_currency} on {on_date}"
        )


def _event_date(event: FinancialEvent, request_date: date) -> date:
    return event.settlement_date or event.event_date or request_date


def _is_usable_event(event: FinancialEvent) -> bool:
    if event.amount is None:
        return False
    if event.status in {"failed", "cancelled", "unrealized"}:
        return False
    if event.direction == "non_cash" or event.event_type == "investment_valuation":
        return False
    if event.status == "pending" and event.direction == "credit":
        return False
    return event.status in {"settled", "scheduled", "pending"}


def _cash_effect(event: FinancialEvent, amount: Decimal) -> Decimal:
    return amount if event.direction == "credit" else -amount


def _canonical_events(events: Iterable[FinancialEvent]) -> tuple[FinancialEvent, ...]:
    event_list = list(events)
    superseded_ids: set[str] = set()
    for event in event_list:
        if event.linked_event_id and event.status in {"settled", "scheduled"}:
            for earlier in event_list:
                if earlier.event_id == event.linked_event_id:
                    if earlier.direction == event.direction and earlier.status in {"pending", "scheduled"}:
                        superseded_ids.add(earlier.event_id)
    return tuple(e for e in event_list if e.event_id not in superseded_ids)


VARIABLE_EXPENSE_CATEGORIES = frozenset(
    {"groceries", "transport"}
)


def detect_recurrences(
    events: Iterable[FinancialEvent],
    user_id: str,
    before_date: date,
    essential_categories: frozenset[str] = frozenset(),
    willing_categories: frozenset[str] = frozenset(),
) -> tuple[Recurrence, ...]:
    grouped: dict[tuple[str, str, str, str, bool], list[FinancialEvent]] = defaultdict(list)
    for event in events:
        if (
            event.user_id == user_id
            and event.event_date < before_date
            and event.amount is not None
            and event.status == "settled"
            and event.direction == "debit"
            and event.event_type != "investment_valuation"
        ):
            is_explicit = event.event_type in RECURRING_EVENT_TYPES or event.category in RECURRING_EXPENSE_CATEGORIES
            is_variable = event.category in VARIABLE_EXPENSE_CATEGORIES or event.category in essential_categories
            if not (is_explicit or is_variable):
                continue

            if event.category in VARIABLE_EXPENSE_CATEGORIES:
                key = (
                    event.category,
                    event.direction,
                    event.currency,
                    "",
                    False,
                )
            else:
                key = (
                    event.category,
                    event.direction,
                    event.currency,
                    " ".join(event.description.lower().split()),
                    True,
                )
            grouped[key].append(event)

    recurrences: list[Recurrence] = []
    for (category, direction, currency, desc_key, is_individual), group in grouped.items():
        ordered = sorted(group, key=lambda event: event.event_date)
        is_explicit_recurring = is_individual or category in RECURRING_EXPENSE_CATEGORIES
        minimum_observations = 2 if is_explicit_recurring else 3
        if len(ordered) < minimum_observations:
            continue
        intervals = [
            (right.event_date - left.event_date).days
            for left, right in zip(ordered, ordered[1:])
        ]
        typical_interval = int(median(intervals))
        if typical_interval < 4 or typical_interval > 45:
            continue
        amount = median(event.amount for event in ordered if event.amount is not None)
        latest = ordered[-1]
        is_monthly = (
            28 <= typical_interval <= 31
            and len(set(e.event_date.day for e in ordered)) <= 2
            and (ordered[-1].event_date.day == ordered[0].event_date.day or len(ordered) >= 3)
        )
        desc = latest.description if is_individual else f"Regular {category}"
        recurrences.append(
            Recurrence(
                user_id=user_id,
                category=latest.category,
                direction=latest.direction,
                amount=amount,
                currency=latest.currency,
                interval_days=typical_interval,
                next_date=latest.event_date + timedelta(days=typical_interval),
                description=desc,
                source_event_id=latest.event_id,
                is_monthly=is_monthly,
                latest_event_date=latest.event_date,
            )
        )
    return tuple(recurrences)


def _recurrence_entries(
    recurrences: Iterable[Recurrence],
    start: date,
    end: date,
    home_currency: str,
    converter: CurrencyConverter,
) -> list[CashFlowEntry]:
    entries: list[CashFlowEntry] = []
    for recurrence in recurrences:
        if recurrence.is_monthly:
            n = 1
            while True:
                current = _add_months(recurrence.latest_event_date, n)
                if current > end:
                    break
                if current >= start:
                    amount = converter.convert(
                        recurrence.amount, recurrence.currency, home_currency, current
                    )
                    if recurrence.direction == "debit":
                        amount = -amount
                    entries.append(
                        CashFlowEntry(
                            date=current,
                            amount=amount,
                            source_id=recurrence.source_event_id,
                            source_type="recurrence",
                            description=recurrence.description,
                        )
                    )
                n += 1
        else:
            current = recurrence.latest_event_date + timedelta(days=recurrence.interval_days)
            while current < start:
                current += timedelta(days=recurrence.interval_days)
            while current <= end:
                amount = converter.convert(
                    recurrence.amount, recurrence.currency, home_currency, current
                )
                if recurrence.direction == "debit":
                    amount = -amount
                entries.append(
                    CashFlowEntry(
                        date=current,
                        amount=amount,
                        source_id=recurrence.source_event_id,
                        source_type="recurrence",
                        description=recurrence.description,
                    )
                )
                current += timedelta(days=recurrence.interval_days)
    return entries




def simulate_cashflow(
    profile: FinancialProfile,
    request: Request,
    events: Iterable[FinancialEvent],
    rates: Iterable[ExchangeRate],
    *,
    additional_entries: Iterable[CashFlowEntry] = (),
    spending_changes: dict[str, Decimal] | None = None,
    resolved_amounts: dict[str, Decimal] | None = None,
) -> SimulationResult:
    end_date = request.request_date + timedelta(days=89)
    converter = CurrencyConverter(rates)
    user_events = _canonical_events(event for event in events if event.user_id == request.user_id)
    unresolved: list[str] = []
    entries: list[CashFlowEntry] = list(additional_entries)

    for event in user_events:
        event_date = _event_date(event, request.request_date)
        event_amount = event.amount
        if event_amount is None and resolved_amounts is not None:
            event_amount = resolved_amounts.get(event.event_id)
        if event_amount is None:
            if request.request_date <= event_date <= end_date:
                unresolved.append(event.event_id)
            continue
        if event_date < request.request_date or event_date > end_date:
            continue
        if not _is_usable_event(event):
            continue
        try:
            converted = converter.convert(
                event_amount, event.currency, profile.home_currency, event_date
            )
        except CurrencyConversionError:
            unresolved.append(event.event_id)
            continue
        if spending_changes and event.event_id in spending_changes:
            converted = converter.convert(
                spending_changes[event.event_id],
                profile.home_currency,
                profile.home_currency,
                event_date,
            )
        entries.append(
            CashFlowEntry(
                date=max(event_date, request.request_date),
                amount=_cash_effect(event, converted),
                source_id=event.event_id,
                source_type="financial_event",
                description=event.description,
            )
        )

    recurrences = detect_recurrences(
        events,
        request.user_id,
        request.request_date,
        essential_categories=frozenset(profile.expense_categories_to_protect),
        willing_categories=frozenset(
            tuple(profile.expense_categories_user_is_willing_to_reduce)
            + tuple(profile.expense_categories_user_is_willing_to_stop)
        ),
    )

    adjusted_recurrences: list[Recurrence] = []
    for recurrence in recurrences:
        if not spending_changes or recurrence.source_event_id not in spending_changes:
            adjusted_recurrences.append(recurrence)
            continue
        adjusted_amount = spending_changes[recurrence.source_event_id]
        if adjusted_amount <= 0:
            continue
        adjusted_recurrences.append(
            Recurrence(
                user_id=recurrence.user_id,
                category=recurrence.category,
                direction=recurrence.direction,
                amount=adjusted_amount,
                currency=recurrence.currency,
                interval_days=recurrence.interval_days,
                next_date=recurrence.next_date,
                description=recurrence.description,
                source_event_id=recurrence.source_event_id,
                is_monthly=recurrence.is_monthly,
                latest_event_date=recurrence.latest_event_date,
            )
        )
    for recurrence in adjusted_recurrences:
        try:
            entries.extend(
                _recurrence_entries(
                    (recurrence,),
                    request.request_date,
                    end_date,
                    profile.home_currency,
                    converter,
                )
            )
        except CurrencyConversionError:
            unresolved.append(recurrence.source_event_id)

    all_sal_events = [
        e for e in user_events
        if e.category == "salary"
        and e.direction == "credit"
        and e.status in {"settled", "scheduled"}
    ]
    if all_sal_events:
        latest_sal = max(
            all_sal_events,
            key=lambda event: _event_date(event, request.request_date),
        )
        if "final" in latest_sal.description.lower():
            sal_events = []
        else:
            sal_events = [
                e for e in all_sal_events
                if (e.amount is not None or (resolved_amounts and e.event_id in resolved_amounts))
                and "arrears" not in e.description.lower()
                and "bonus" not in e.description.lower()
                and "commission" not in e.description.lower()
            ]
    else:
        sal_events = []

    sal_dates_in_events = {
        _event_date(e, request.request_date) for e in sal_events
    } | {
        entry.date for entry in additional_entries if "salary" in entry.description.lower()
    }
    if sal_events:
        sal_event = max(
            sal_events,
            key=lambda event: _event_date(event, request.request_date),
        )
        sal_amt = sal_event.amount
        if sal_amt is None and resolved_amounts is not None:
            sal_amt = resolved_amounts.get(sal_event.event_id)
        if sal_amt is not None:
            sal_date = _event_date(sal_event, request.request_date)
            monthly_days = [
                _event_date(e, request.request_date).day
                for e in sal_events
            ]
            if monthly_days:
                dom_day = Counter(monthly_days).most_common(1)[0][0]
                if monthly_days.count(dom_day) >= 2:
                    max_day = calendar.monthrange(sal_date.year, sal_date.month)[1]
                    sal_date = date(sal_date.year, sal_date.month, min(dom_day, max_day))
            n = 1
            while True:
                nxt = _add_months(sal_date, n)
                if nxt > end_date:
                    break
                if nxt >= request.request_date and not any(abs((nxt - d).days) <= 5 for d in sal_dates_in_events):
                    try:
                        conv = converter.convert(
                            sal_amt, sal_event.currency, profile.home_currency, nxt
                        )
                        entries.append(
                            CashFlowEntry(
                                date=nxt,
                                amount=conv,
                                source_id="recurring_salary",
                                source_type="salary_recurrence",
                                description="ongoing monthly salary",
                            )
                        )
                        sal_dates_in_events.add(nxt)
                    except CurrencyConversionError:
                        pass
                n += 1




    daily_changes: dict[date, Decimal] = defaultdict(Decimal)
    for entry in entries:
        daily_changes[entry.date] += entry.amount

    balances: list[tuple[date, Decimal]] = []
    balance = profile.current_available_balance
    current = request.request_date
    while current <= end_date:
        balance += daily_changes[current]
        balances.append((current, balance))
        current += timedelta(days=1)

    return SimulationResult(
        request_date=request.request_date,
        end_date=end_date,
        minimum_balance=profile.minimum_balance_to_keep,
        balances=tuple(balances),
        entries=tuple(sorted(entries, key=lambda entry: (entry.date, entry.source_id))),
        unresolved_event_ids=tuple(sorted(set(unresolved))),
    )


def safe_amount_today(result: SimulationResult, requested_amount: Decimal) -> Decimal:
    future_headroom = min(
        balance - result.minimum_balance for _, balance in result.balances
    )
    return max(Decimal("0"), min(requested_amount, future_headroom))


def earliest_safe_date(
    result: SimulationResult, amount: Decimal
) -> date | None:
    balance_by_date = dict(result.balances)
    dates = sorted(balance_by_date)
    for i, current in enumerate(dates):
        if all(balance_by_date[d] - amount >= result.minimum_balance for d in dates[i:]):
            return current
    return None

