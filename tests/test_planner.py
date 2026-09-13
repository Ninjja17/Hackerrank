from __future__ import annotations

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from cashflow import simulate_cashflow  # noqa: E402
from loader import load_dataset  # noqa: E402
from planner import decide_all, decide_request  # noqa: E402


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_dataset(ROOT / "dataset")

    def test_decides_every_request_without_stopping(self) -> None:
        rows = decide_all(self.bundle)
        self.assertEqual(len(rows), len(self.bundle.requests))
        self.assertEqual(
            tuple(row.request_id for row in rows),
            tuple(request.request_id for request in self.bundle.requests),
        )

    def test_sample_regression_is_structurally_consistent(self) -> None:
        sample_by_id = {
            sample.request.request_id: sample.output
            for sample in self.bundle.sample_requests
        }
        for request in self.bundle.requests:
            if request.request_id not in sample_by_id:
                continue
            row = decide_request(self.bundle, request)
            self.assertGreaterEqual(row.amount_safe_to_pay, Decimal("0"))
            self.assertLessEqual(row.amount_safe_to_pay, request.requested_amount)
            if row.affordability_status == "affordable_now":
                self.assertEqual(row.earliest_date_for_full_payment, request.request_date)

    def test_generated_spending_changes_use_allowed_forms(self) -> None:
        rows = decide_all(self.bundle)
        for row in rows:
            if row.spending_changes_needed == "none":
                continue
            for change in row.spending_changes_needed.split("|"):
                parts = change.split(":")
                self.assertIn(parts[0], {"stop", "reduce_to"})
                self.assertGreaterEqual(len(parts), 2)
                if parts[0] == "reduce_to":
                    self.assertEqual(len(parts), 3)
                    self.assertGreaterEqual(Decimal(parts[2]), Decimal("0"))

    def test_fallback_explanation_does_not_expose_internal_errors(self) -> None:
        request = self.bundle.requests[0]
        broken_bundle = type(self.bundle)(
            financial_profiles=self.bundle.financial_profiles,
            financial_events=self.bundle.financial_events,
            exchange_rates=(),
            requests=self.bundle.requests,
            sample_requests=self.bundle.sample_requests,
            payment_options=self.bundle.payment_options,
            messages=self.bundle.messages,
            images=self.bundle.images,
            output_template_request_ids=self.bundle.output_template_request_ids,
        )
        row = decide_all(broken_bundle)[0]
        self.assertEqual(row.request_id, request.request_id)
        self.assertNotIn("No exchange rate", row.decision_explanation)


if __name__ == "__main__":
    unittest.main()