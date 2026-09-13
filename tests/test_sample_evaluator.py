from __future__ import annotations

import sys
import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
EVALUATOR_PATH = ROOT / "code" / "evaluation" / "main.py"
SPEC = importlib.util.spec_from_file_location("sample_evaluator", EVALUATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
compare_samples = MODULE.compare_samples


class SampleEvaluatorTests(unittest.TestCase):
    def test_evaluates_all_public_samples_and_reports_fields(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "evaluation_report.csv"
            checked, matched, mismatches, field_mismatches = compare_samples(
                ROOT / "dataset", report_path
            )
            self.assertEqual(checked, 25)
            self.assertEqual(len(mismatches) > 0, matched < checked)
            self.assertEqual(set(field_mismatches), {
                "amount_safe_to_pay",
                "affordability_status",
                "recommended_payment_method",
                "payment_plan",
                "earliest_date_for_full_payment",
                "spending_changes_needed",
            })
            self.assertTrue(report_path.exists())
            header = report_path.read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("mismatched_fields", header)


if __name__ == "__main__":
    unittest.main()