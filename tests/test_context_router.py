from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from context_router import Route, build_context, route_context  # noqa: E402
from loader import load_dataset  # noqa: E402


class ContextRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_dataset(ROOT / "dataset")

    def test_context_routes_real_requests_without_provider(self) -> None:
        context = build_context(self.bundle, self.bundle.requests[0])
        route = route_context(context, provider_available=False)
        self.assertIn(route, {Route.DETERMINISTIC_ONLY, Route.LLM_EVIDENCE_EXTRACTION_WITH_REVIEW})

    def test_clean_context_skips_model(self) -> None:
        from context_router import RequestContext

        context = RequestContext("r", "u", "purchase", "", False, False, False, False, False, False, False, False, False, False, False, False)
        self.assertEqual(route_context(context, provider_available=True), Route.DETERMINISTIC_ONLY)


if __name__ == "__main__":
    unittest.main()