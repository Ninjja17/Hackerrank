from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from evidence import resolve_image_amounts  # noqa: E402
from loader import load_dataset  # noqa: E402


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_dataset(ROOT / "dataset")

    def test_all_linked_blank_amounts_have_verified_provenance(self) -> None:
        amounts, facts, failures = resolve_image_amounts(
            self.bundle.images, ROOT / "dataset" / "media" / "images"
        )
        self.assertEqual(failures, ())
        self.assertEqual(len(facts), 16)
        self.assertEqual(amounts["event_253"], Decimal("4365000"))
        self.assertEqual(amounts["event_7307"], Decimal("33.50"))
        self.assertEqual(amounts["event_10521"], Decimal("393.22"))
        self.assertTrue(all(fact.source_type == "image" for fact in facts))


if __name__ == "__main__":
    unittest.main()