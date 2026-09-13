from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from cashflow import simulate_cashflow  # noqa: E402
from evidence import extract_message_facts  # noqa: E402
from models import FinancialEvent, FinancialProfile, Message, Request  # noqa: E402


class ServiceTests(unittest.TestCase):
    def test_message_fact_extraction_is_structured(self) -> None:
        messages = (
            Message(
                "message_salary",
                "user_1",
                "request_1",
                None,
                datetime(2026, 1, 2, tzinfo=timezone.utc),
                "employer",
                "Payroll confirms salary is IDR 42750000 from 2026-01-15.",
            ),
        )
        facts = extract_message_facts(messages, "user_1", "request_1")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].fact_type, "income_update")
        self.assertEqual(facts[0].amount, Decimal("42750000"))
        self.assertEqual(facts[0].currency, "IDR")
        self.assertEqual(facts[0].effective_date, "2026-01-15")

    def test_missing_event_fx_is_conservative_and_nonfatal(self) -> None:
        profile = FinancialProfile(
            "user_1", "INR", Decimal("1000"), Decimal("100"), (), (), (), (), (), None
        )
        request = Request(
            "request_1", "user_1", date(2026, 1, 1), "purchase", Decimal("50"),
            date(2026, 1, 10), False, "",
        )
        event = FinancialEvent(
            "event_usd", "user_1", "expense", "future USD bill", "utilities",
            "debit", Decimal("50"), "USD", date(2026, 1, 2), date(2026, 1, 2),
            "scheduled", None, "fixed", None,
        )
        result = simulate_cashflow(profile, request, (event,), ())
        self.assertEqual(result.unresolved_event_ids, ("event_usd",))
        self.assertEqual(result.lowest_balance, Decimal("1000"))
        self.assertFalse(result.is_safe)


if __name__ == "__main__":
    unittest.main()