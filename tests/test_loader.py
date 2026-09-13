from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from loader import dataset_summary, load_dataset  # noqa: E402


class LoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_dataset(ROOT / "dataset")

    def test_loads_every_csv(self) -> None:
        summary = dataset_summary(self.bundle)
        for key in (
            "financial_profiles",
            "financial_events",
            "exchange_rates",
            "requests",
            "sample_requests",
            "payment_options",
            "messages",
            "images",
            "output_template_rows",
        ):
            self.assertGreater(summary[key], 0, key)

    def test_money_is_decimal(self) -> None:
        self.assertIsInstance(
            self.bundle.financial_profiles[0].current_available_balance, Decimal
        )
        self.assertIsInstance(self.bundle.financial_events[0].amount, Decimal)
        self.assertIsInstance(self.bundle.exchange_rates[0].rate, Decimal)
        self.assertIsInstance(self.bundle.requests[0].requested_amount, Decimal)
        self.assertIsInstance(self.bundle.payment_options[0].payment_amount, Decimal)
        self.assertIsInstance(
            self.bundle.sample_requests[0].output.amount_safe_to_pay, Decimal
        )

    def test_request_and_template_order_match(self) -> None:
        request_ids = tuple(request.request_id for request in self.bundle.requests)
        self.assertEqual(request_ids, self.bundle.output_template_request_ids)
        self.assertEqual(len(request_ids), len(set(request_ids)))


if __name__ == "__main__":
    unittest.main()
