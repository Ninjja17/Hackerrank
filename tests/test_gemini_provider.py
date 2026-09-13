from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from gemini_provider import GeminiEvidenceProvider, GeminiProviderError  # noqa: E402
from llm_agent import AgentRun  # noqa: E402


class GeminiProviderTests(unittest.TestCase):
    def test_validates_structured_fact(self) -> None:
        provider = GeminiEvidenceProvider(api_key="test")
        fact = provider._validate_fact(
            {
                "source_id": "message_1",
                "fact_type": "income_update",
                "amount": "100.50",
                "currency": "USD",
                "effective_date": "2026-01-01",
                "confidence": "0.9",
            }
        )
        self.assertEqual(str(fact.amount), "100.50")

    def test_rejects_invalid_fact_type(self) -> None:
        provider = GeminiEvidenceProvider(api_key="test")
        with self.assertRaises(GeminiProviderError):
            provider._validate_fact({"source_id": "message_1", "fact_type": "approve_request"})

    def test_rejects_unsafe_pending_fact_for_cashflow(self) -> None:
        provider = GeminiEvidenceProvider(api_key="test")
        fact = provider._validate_fact(
            {
                "source_id": "message_1",
                "fact_type": "bonus",
                "status": "pending",
                "amount": "100",
                "currency": "USD",
                "confidence": "0.9",
                "usable_for_cashflow": True,
            }
        )
        self.assertFalse(fact.usable_for_cashflow)

    def test_agent_run_reports_fact_count(self) -> None:
        run = AgentRun({}, {})
        self.assertEqual(run.fact_count, 0)


if __name__ == "__main__":
    unittest.main()