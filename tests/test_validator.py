from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from loader import load_dataset  # noqa: E402
from main import build_baseline_rows  # noqa: E402
from validator import validate_output_rows  # noqa: E402


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_dataset(ROOT / "dataset")
        cls.rows = build_baseline_rows(cls.bundle.requests)

    def test_baseline_is_structurally_valid(self) -> None:
        self.assertEqual(validate_output_rows(self.rows, self.bundle.requests), ())

    def test_rejects_invalid_status_method_plan_date_and_range(self) -> None:
        first = self.rows[0]
        bad = replace(
            first,
            amount_safe_to_pay=Decimal("-1"),
            affordability_status="maybe",
            recommended_payment_method="cash",
            payment_plan="not-a-plan",
            earliest_date_for_full_payment=self.bundle.requests[0].request_date,
        )
        issues = validate_output_rows((bad, *self.rows[1:]), self.bundle.requests)
        combined = "\n".join(issues)
        self.assertIn("amount_safe_to_pay", combined)
        self.assertIn("invalid affordability_status", combined)
        self.assertIn("invalid recommended_payment_method", combined)
        self.assertIn("invalid payment-plan entry", combined)

        bad_date = replace(
            first,
            earliest_date_for_full_payment=self.bundle.requests[0].request_date,
        )
        date_issues = validate_output_rows(
            (bad_date, *self.rows[1:]), self.bundle.requests
        )
        self.assertIn("earliest date must be blank", "\n".join(date_issues))

    def test_rejects_duplicates_and_missing_coverage(self) -> None:
        issues = validate_output_rows(
            (self.rows[0], self.rows[0], *self.rows[2:]), self.bundle.requests
        )
        combined = "\n".join(issues)
        self.assertIn("duplicate request_id", combined)
        self.assertIn("missing request_ids", combined)

    def test_rejects_wrong_row_order(self) -> None:
        reordered = (self.rows[1], self.rows[0], *self.rows[2:])
        issues = validate_output_rows(reordered, self.bundle.requests)
        self.assertIn("output rows must follow requests.csv order", issues)


if __name__ == "__main__":
    unittest.main()