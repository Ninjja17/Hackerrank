from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "code" / "package_submission.py"
SPEC = importlib.util.spec_from_file_location("package_submission", PACKAGE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PackagingTests(unittest.TestCase):
    def test_archive_includes_required_usage_report_and_excludes_secrets(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for required in MODULE.REQUIRED_PATHS:
                path = root / required
                if path.suffix:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("test", encoding="utf-8")
                else:
                    path.mkdir(parents=True, exist_ok=True)
                    (path / "test.py").write_text("test", encoding="utf-8")
            (root / ".env").write_text("secret", encoding="utf-8")
            (root / "log.txt").write_text("history", encoding="utf-8")
            (root / "dataset").mkdir()
            (root / "dataset" / "requests.csv").write_text("request_id", encoding="utf-8")
            archive_path = root / "code.zip"
            names = MODULE.build_archive(root, archive_path)
        self.assertIn("evaluation/usage_report.md", names)
        self.assertNotIn(".env", names)
        self.assertNotIn("log.txt", names)
        self.assertNotIn("dataset/requests.csv", names)


if __name__ == "__main__":
    unittest.main()