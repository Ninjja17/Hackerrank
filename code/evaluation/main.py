from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

from loader import load_dataset  # noqa: E402
from evidence import resolve_image_amounts  # noqa: E402
from llm_agent import deterministic_message_entries_by_request  # noqa: E402
from planner import decide_request  # noqa: E402


STRUCTURED_FIELDS = (
	"amount_safe_to_pay",
	"affordability_status",
	"recommended_payment_method",
	"payment_plan",
	"earliest_date_for_full_payment",
	"spending_changes_needed",
)


REPORT_COLUMNS = (
	"request_id",
	"user_id",
	"requested_amount",
	"expected_amount_safe_to_pay",
	"actual_amount_safe_to_pay",
	"expected_affordability_status",
	"actual_affordability_status",
	"expected_recommended_payment_method",
	"actual_recommended_payment_method",
	"expected_payment_plan",
	"actual_payment_plan",
	"expected_earliest_date_for_full_payment",
	"actual_earliest_date_for_full_payment",
	"expected_spending_changes_needed",
	"actual_spending_changes_needed",
	"mismatched_fields",
)


def _format_value(value: object) -> str:
	return value.isoformat() if hasattr(value, "isoformat") else str(value)


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8", newline="") as report_file:
		writer = csv.DictWriter(report_file, fieldnames=REPORT_COLUMNS)
		writer.writeheader()
		writer.writerows(rows)


def compare_samples(
	dataset_dir: Path,
	report_path: Path | None = None,
) -> tuple[int, int, list[str], dict[str, int]]:
	bundle = load_dataset(dataset_dir)
	evidence_entries = deterministic_message_entries_by_request(bundle)
	resolved_amounts, _, _ = resolve_image_amounts(
		bundle.images, dataset_dir / "media" / "images"
	)
	requests = {request.request_id: request for request in bundle.requests}
	mismatches: list[str] = []
	report_rows: list[dict[str, str]] = []
	field_mismatches: dict[str, int] = {field: 0 for field in STRUCTURED_FIELDS}
	checked = 0
	matched = 0
	for sample in bundle.sample_requests:
		request = requests.get(sample.request.request_id, sample.request)
		actual = decide_request(
			bundle,
			request,
			evidence_entries.get(request.request_id, ()),
			resolved_amounts,
		)
		checked += 1
		fields_match = True
		mismatched_fields: list[str] = []
		for field in STRUCTURED_FIELDS:
			expected_value = getattr(sample.output, field)
			actual_value = getattr(actual, field)
			if actual_value != expected_value:
				fields_match = False
				mismatched_fields.append(field)
				field_mismatches[field] += 1
				mismatches.append(
					f"{request.request_id} {field}: expected={expected_value!r} actual={actual_value!r}"
				)
		if fields_match:
			matched += 1
		report_rows.append(
			{
				"request_id": request.request_id,
				"user_id": request.user_id,
				"requested_amount": _format_value(request.requested_amount),
				**{
					f"expected_{field}": _format_value(getattr(sample.output, field))
					for field in STRUCTURED_FIELDS
				},
				**{
					f"actual_{field}": _format_value(getattr(actual, field))
					for field in STRUCTURED_FIELDS
				},
				"mismatched_fields": "|".join(mismatched_fields) or "none",
			}
		)
	if report_path is not None:
		write_report(report_path, report_rows)
	return checked, matched, mismatches, field_mismatches


def main() -> int:
	parser = argparse.ArgumentParser(description="Compare structured outputs with public samples")
	parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
	parser.add_argument(
		"--report",
		type=Path,
		default=ROOT / "evaluation_report.csv",
		help="CSV table of expected and actual public-sample decisions",
	)
	args = parser.parse_args()
	checked, matched, mismatches, field_mismatches = compare_samples(
		args.dataset, args.report
	)
	print(f"samples_checked={checked}")
	print(f"structured_matches={matched}")
	print(f"structured_mismatches={checked - matched}")
	print("field_mismatches=" + json.dumps(field_mismatches, sort_keys=True))
	print(f"report={args.report}")
	for mismatch in mismatches:
		print(mismatch)
	return 0 if not mismatches else 1


if __name__ == "__main__":
	raise SystemExit(main())
