from __future__ import annotations

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from cashflow import (  # noqa: E402
    CurrencyConverter,
    detect_recurrences,
    earliest_safe_date,
    safe_amount_today,
    simulate_cashflow,
)
from models import ExchangeRate, FinancialEvent, FinancialProfile, Request  # noqa: E402


def profile(balance: str = "1000", minimum: str = "200") -> FinancialProfile:
    return FinancialProfile(
        user_id="user_1",
        home_currency="USD",
        current_available_balance=Decimal(balance),
        minimum_balance_to_keep=Decimal(minimum),
        financial_priorities=(),
        expense_categories_to_protect=(),
        expense_categories_user_is_willing_to_reduce=(),
        expense_categories_user_is_willing_to_stop=(),
        payment_methods_user_will_consider=("full_payment",),
        max_installment_months=None,
    )


def request() -> Request:
    return Request(
        request_id="request_1",
        user_id="user_1",
        request_date=date(2026, 1, 1),
        request_type="purchase",
        requested_amount=Decimal("900"),
        desired_completion_date=date(2026, 1, 30),
        allows_partial_payment=False,
        request_text="",
    )


def event(
    event_id: str,
    event_date: date,
    amount: str,
    direction: str = "debit",
    status: str = "scheduled",
    event_type: str = "expense",
    currency: str = "USD",
    category: str = "rent",
    description: str | None = None,
) -> FinancialEvent:
    return FinancialEvent(
        event_id=event_id,
        user_id="user_1",
        event_type=event_type,
        description=description or event_id,
        category=category,
        direction=direction,
        amount=Decimal(amount),
        currency=currency,
        event_date=event_date,
        settlement_date=event_date,
        status=status,
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )


class CashflowTests(unittest.TestCase):
    def test_currency_conversion_uses_decimal_and_reverse_rate(self) -> None:
        converter = CurrencyConverter(
            (ExchangeRate(date(2026, 1, 1), "EUR", "USD", Decimal("2")),)
        )
        self.assertEqual(
            converter.convert(Decimal("10"), "USD", "EUR", date(2026, 1, 1)),
            Decimal("5"),
        )

    def test_failed_cancelled_pending_credit_and_unrealized_are_excluded(self) -> None:
        events = (
            event("failed", date(2026, 1, 2), "500", status="failed"),
            event("cancelled", date(2026, 1, 3), "500", status="cancelled"),
            event("credit", date(2026, 1, 4), "500", direction="credit", status="pending"),
            event("investment", date(2026, 1, 5), "500", direction="non_cash", status="unrealized"),
        )
        result = simulate_cashflow(profile(), request(), events, ())
        self.assertEqual(result.lowest_balance, Decimal("1000"))

    def test_scheduled_debit_and_future_salary_affect_balance(self) -> None:
        events = (
            event("bill", date(2026, 1, 5), "300"),
            event("salary", date(2026, 1, 10), "500", direction="credit", event_type="income"),
        )
        result = simulate_cashflow(profile(), request(), events, ())
        self.assertEqual(dict(result.balances)[date(2026, 1, 4)], Decimal("1000"))
        self.assertEqual(dict(result.balances)[date(2026, 1, 5)], Decimal("700"))
        self.assertEqual(dict(result.balances)[date(2026, 1, 10)], Decimal("1200"))

    def test_recurrence_is_detected_and_applied(self) -> None:
        historical = (
            event("r1", date(2025, 12, 1), "100", status="settled", description="Rent"),
            event("r2", date(2025, 12, 31), "100", status="settled", description="Rent"),
        )
        recurrences = detect_recurrences(historical, "user_1", date(2026, 1, 1))
        self.assertEqual(len(recurrences), 1)
        result = simulate_cashflow(profile(), request(), historical, ())
        self.assertEqual(dict(result.balances)[date(2026, 1, 30)], Decimal("900"))

    def test_recurrence_requires_the_same_description(self) -> None:
        historical = (
            event("rent", date(2025, 12, 1), "100", status="settled"),
            event("utilities", date(2025, 12, 31), "100", status="settled"),
        )
        self.assertEqual(
            detect_recurrences(historical, "user_1", date(2026, 1, 1)), ()
        )

    def test_ordinary_expenses_need_three_matching_observations(self) -> None:
        historical = (
            event("shop_1", date(2025, 12, 1), "100", status="settled", category="groceries", description="Market"),
            event("shop_2", date(2025, 12, 8), "100", status="settled", category="groceries", description="Market"),
        )
        self.assertEqual(
            detect_recurrences(
                historical,
                "user_1",
                date(2026, 1, 1),
                frozenset({"groceries"}),
            ),
            (),
        )

    def test_safe_amount_and_earliest_date(self) -> None:
        result = simulate_cashflow(
            profile(), request(), (event("income", date(2026, 1, 5), "500", direction="credit"),), ()
        )
        self.assertEqual(safe_amount_today(result, Decimal("900")), Decimal("800"))
        self.assertEqual(earliest_safe_date(result, Decimal("900")), date(2026, 1, 5))

    def test_settled_salary_history_forecasts_the_next_monthly_payment(self) -> None:
        salaries = (
            event("salary_june", date(2025, 11, 15), "500", direction="credit", status="settled", category="salary", description="Payroll credit"),
            event("salary_july", date(2025, 12, 15), "500", direction="credit", status="settled", category="salary", description="Payroll credit"),
            event("bonus", date(2025, 12, 20), "800", direction="credit", status="settled", category="salary", description="Promotion arrears"),
        )
        result = simulate_cashflow(profile(), request(), salaries, ())
        self.assertEqual(dict(result.balances)[date(2026, 1, 15)], Decimal("1500"))

    def test_reducing_a_recurring_event_changes_future_occurrences(self) -> None:
        historical = (
            event("subscription_1", date(2025, 12, 1), "100", status="settled", description="Shared storage plan"),
            event("subscription_2", date(2025, 12, 31), "100", status="settled", description="Shared storage plan"),
        )
        result = simulate_cashflow(
            profile(),
            request(),
            historical,
            (),
            spending_changes={"subscription_2": Decimal("25")},
        )
        self.assertEqual(dict(result.balances)[date(2026, 1, 30)], Decimal("975"))

    def test_stopping_a_recurring_event_removes_future_occurrences(self) -> None:
        historical = (
            event("subscription_1", date(2025, 12, 1), "100", status="settled", description="Shared storage plan"),
            event("subscription_2", date(2025, 12, 31), "100", status="settled", description="Shared storage plan"),
        )
        result = simulate_cashflow(
            profile(),
            request(),
            historical,
            (),
            spending_changes={"subscription_2": Decimal("0")},
        )
        self.assertEqual(dict(result.balances)[date(2026, 1, 30)], Decimal("1000"))


if __name__ == "__main__":
    unittest.main()