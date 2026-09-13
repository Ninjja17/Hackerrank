from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from llm_agent import deterministic_message_entries_by_request  # noqa: E402
from loader import load_dataset  # noqa: E402


class MessageStateTests(unittest.TestCase):
    def test_explicitly_dated_salary_messages_produce_entries(self) -> None:
        bundle = load_dataset(ROOT / "dataset")
        entries = deterministic_message_entries_by_request(bundle)
        self.assertIn("request_15", entries)
        self.assertGreater(len(entries["request_15"]), 0)


if __name__ == "__main__":
    unittest.main()