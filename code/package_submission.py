from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    "code/main.py",
    "tests",
    "evaluation/usage_report.md",
    "README.md",
    "requirements.txt",
)
EXCLUDED_PARTS = {
    ".git",
    ".env",
    "__pycache__",
    ".pytest_cache",
    "dataset",
    "log.txt",
    "scratch",
}


def archive_members(root: Path) -> tuple[Path, ...]:
    members: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.name in {"code.zip", "output.csv", "review.csv", "evaluation_report.csv"}:
            continue
        members.append(path)
    return tuple(sorted(members))


def build_archive(root: Path, archive_path: Path) -> tuple[str, ...]:
    missing = [path for path in REQUIRED_PATHS if not (root / path).exists()]
    if missing:
        raise FileNotFoundError("Required submission paths are missing: " + ", ".join(missing))
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        for member in archive_members(root):
            archive.write(member, member.relative_to(root).as_posix())
    with ZipFile(archive_path) as archive:
        names = tuple(archive.namelist())
    missing = [path for path in REQUIRED_PATHS if not any(name == path or name.startswith(path + "/") for name in names)]
    if missing:
        raise RuntimeError("Archive is missing required paths: " + ", ".join(missing))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the HackerRank submission archive")
    parser.add_argument("--output", type=Path, default=ROOT / "code.zip")
    args = parser.parse_args()
    names = build_archive(ROOT, args.output)
    print(f"Wrote {args.output} with {len(names)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())