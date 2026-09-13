from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from gemini_provider import GeminiEvidenceProvider, GeminiProviderError  # noqa: E402
from llm_agent import AgentRun, income_entries_by_request  # noqa: E402
from models import Message  # noqa: E402
from main import write_usage_report  # noqa: E402


class HarnessGovernanceTests(unittest.TestCase):
    def test_call_budget_is_enforced(self) -> None:
        provider = GeminiEvidenceProvider(api_key="test", max_calls=0)
        with self.assertRaises(GeminiProviderError):
            provider.extract(
                (
                    Message(
                        "message_1", "user_1", "request_1", None, None, "bank", "confirmed"
                    ),
                ),
                "user_1",
                "request_1",
            )

    def test_provider_timeout_default_is_bounded(self) -> None:
        provider = GeminiEvidenceProvider(api_key="test")
        self.assertLessEqual(provider.timeout, 8)

    def test_low_confidence_facts_enter_review_queue(self) -> None:
        from gemini_provider import GeminiFact

        run = AgentRun(
            {
                "request_1": (
                    GeminiFact(
                        "message_1", "confirmation", "confirmed", None, None, None,
                        Decimal("0.2"), False
                    ),
                )
            },
            {},
        )
        rows = run.review_rows()
        self.assertEqual(rows[0]["reason"], "low_confidence_fact")

    def test_only_high_confidence_income_facts_become_entries(self) -> None:
        from datetime import date
        from models import DatasetBundle, FinancialProfile, Request

        profile = FinancialProfile(
            "user_1", "USD", Decimal("100"), Decimal("10"), (), (), (), (), (), None
        )
        request = Request(
            "request_1", "user_1", date(2026, 1, 1), "purchase", Decimal("1"),
            date(2026, 1, 2), False, "",
        )
        bundle = DatasetBundle(
            (profile,), (), (), (request,), (), (), (), (), ("request_1",)
        )
        from gemini_provider import GeminiFact

        run = AgentRun(
            {
                "request_1": (
                    GeminiFact(
                        "message_1", "income_update", "confirmed", Decimal("50"),
                        "USD", "2026-01-01", Decimal("0.9"), True
                    ),
                )
            },
            {},
        )
        entries = income_entries_by_request(bundle, run)
        self.assertEqual(entries["request_1"][0].amount, Decimal("50"))

    def test_deterministic_run_usage_report_records_zero_model_cost(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "usage_report.md"
            write_usage_report(
                report_path,
                request_count=250,
                output_path=Path("output.csv"),
                provider=None,
            )
            report = report_path.read_text(encoding="utf-8")
        self.assertIn("| Model calls | 0 |", report)
        self.assertIn("| Estimated total cost (USD) | $0.000000 |", report)


if __name__ == "__main__":
    unittest.main()