from __future__ import annotations

import argparse
import csv
import os
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from loader import dataset_summary, load_dataset
from evidence import resolve_image_amounts
from gemini_provider import GeminiEvidenceProvider, configured_provider
from llm_agent import (
	deterministic_message_entries_by_request,
	extract_optional_evidence,
	income_entries_by_request,
)
from models import OUTPUT_COLUMNS, OutputRow
from planner import decide_all
from validator import (
	OutputValidationError,
	validate_decision_rows,
	validate_output_file,
	validate_output_rows,
)


def format_decimal(value: Decimal) -> str:
	return format(value, "f")


def build_baseline_rows(requests: Sequence[object]) -> tuple[OutputRow, ...]:
	rows: list[OutputRow] = []
	for request in requests:
		request_id = getattr(request, "request_id")
		rows.append(
			OutputRow(
				request_id=request_id,
				amount_safe_to_pay=Decimal("0"),
				affordability_status="not_affordable",
				recommended_payment_method="not_recommended",
				payment_plan="none",
				earliest_date_for_full_payment=None,
				spending_changes_needed="none",
				decision_explanation=(
					"Baseline placeholder: no financial decision has been computed."
				),
			)
		)
	return tuple(rows)


def write_output(path: Path, rows: Sequence[OutputRow]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8", newline="") as csv_file:
		writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
		writer.writeheader()
		for row in rows:
			writer.writerow(
				{
					"request_id": row.request_id,
					"amount_safe_to_pay": format_decimal(row.amount_safe_to_pay),
					"affordability_status": row.affordability_status,
					"recommended_payment_method": row.recommended_payment_method,
					"payment_plan": row.payment_plan,
					"earliest_date_for_full_payment": (
						row.earliest_date_for_full_payment.isoformat()
						if row.earliest_date_for_full_payment
						else ""
					),
					"spending_changes_needed": row.spending_changes_needed,
					"decision_explanation": row.decision_explanation,
				}
			)


def write_review(path: Path, rows: Sequence[dict[str, str]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8", newline="") as csv_file:
		writer = csv.DictWriter(csv_file, fieldnames=("request_id", "reason", "details"))
		writer.writeheader()
		writer.writerows(rows)


def write_usage_report(
	path: Path,
	*,
	request_count: int,
	output_path: Path,
	provider: GeminiEvidenceProvider | None,
) -> None:
	usage = provider.usage() if provider else None
	model = usage.model if usage else "none (deterministic mode)"
	calls = usage.calls if usage else 0
	input_tokens = usage.input_tokens if usage else 0
	output_tokens = usage.output_tokens if usage else 0
	input_rate = Decimal(os.getenv("GEMINI_INPUT_COST_PER_MILLION_USD", "0.10"))
	output_rate = Decimal(os.getenv("GEMINI_OUTPUT_COST_PER_MILLION_USD", "0.40"))
	estimated_cost = (
		Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
	) / Decimal("1000000")
	average_tokens = Decimal(input_tokens + output_tokens) / Decimal(request_count)
	average_cost = estimated_cost / Decimal(request_count)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(
		"# Final Run Usage Report\n\n"
		f"Output: `{output_path.as_posix()}`\n\n"
		"| Metric | Value |\n"
		"| --- | ---: |\n"
		f"| Requests | {request_count} |\n"
		f"| Model provider | {'Gemini' if provider else 'none'} |\n"
		f"| Model name | {model} |\n"
		f"| Model calls | {calls} |\n"
		f"| Input tokens | {input_tokens} |\n"
		f"| Output tokens | {output_tokens} |\n"
		f"| Total tokens | {input_tokens + output_tokens} |\n"
		f"| Average tokens per request | {average_tokens:.2f} |\n"
		f"| Estimated total cost (USD) | ${estimated_cost:.6f} |\n"
		f"| Estimated cost per request (USD) | ${average_cost:.6f} |\n\n"
		"Cost estimate uses `GEMINI_INPUT_COST_PER_MILLION_USD` and "
		"`GEMINI_OUTPUT_COST_PER_MILLION_USD` (defaults: $0.10 and $0.40). "
		"No API keys or credentials are recorded.\n",
		encoding="utf-8",
	)


def _print_summary(summary: dict[str, object]) -> None:
	print("Dataset summary")
	print("---------------")
	for key, value in summary.items():
		if key == "request_date_range":
			start, end = value
			print(f"request_date_range: {start} to {end}")
		elif key == "currencies":
			print(f"currencies: {', '.join(value)}")
		else:
			print(f"{key}: {value}")


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Buy or Wait? dataset foundation")
	parser.add_argument(
		"command",
		nargs="?",
		choices=("run", "summary", "baseline", "validate"),
		default="run",
		help="action to run; defaults to the full deterministic pipeline",
	)
	parser.add_argument(
		"--dataset", type=Path, default=Path("dataset"), help="dataset directory"
	)
	parser.add_argument(
		"--output", type=Path, default=Path("output.csv"), help="output CSV path"
	)
	parser.add_argument(
		"--review-output", type=Path, default=Path("review.csv"),
		help="human-review queue path for optional LLM runs",
	)
	parser.add_argument(
		"--usage-report", type=Path, default=Path("evaluation") / "usage_report.md",
		help="final-run model usage and cost report path",
	)
	return parser


def main(argv: Sequence[str] | None = None) -> int:
	args = build_parser().parse_args(argv)
	bundle = load_dataset(args.dataset)
	llm_provider: GeminiEvidenceProvider | None = configured_provider()

	if args.command == "summary":
		_print_summary(dataset_summary(bundle))
		return 0
	if args.command == "run":
		agent_run = extract_optional_evidence(bundle, llm_provider)
		write_review(args.review_output, agent_run.review_rows())
		evidence_entries = deterministic_message_entries_by_request(bundle)
		for request_id, entries in income_entries_by_request(bundle, agent_run).items():
			evidence_entries[request_id] = (*evidence_entries.get(request_id, ()), *entries)
		usage = llm_provider.usage() if llm_provider else None
		print(
			f"Routing: {sum(route == 'deterministic_only' for route in agent_run.routes.values())} deterministic, "
			f"{sum(route != 'deterministic_only' for route in agent_run.routes.values())} LLM/review; "
			f"Gemini calls: {usage.calls if usage else 0}, facts: {agent_run.fact_count}, "
			f"provider errors: {len(agent_run.provider_errors)}, "
			f"tokens: {(usage.input_tokens + usage.output_tokens) if usage else 0}"
		)
		resolved_amounts, _, _ = resolve_image_amounts(
			bundle.images, args.dataset / "media" / "images"
		)
		rows = decide_all(bundle, evidence_entries, resolved_amounts)
		issues = validate_decision_rows(rows, bundle, evidence_entries)
		if issues:
			raise OutputValidationError(issues)
		write_output(args.output, rows)
		write_usage_report(
			args.usage_report,
			request_count=len(rows),
			output_path=args.output,
			provider=llm_provider,
		)
		print(f"Wrote {len(rows)} deterministic decisions to {args.output}")
		print(f"Wrote final-run usage report to {args.usage_report}")
		return 0
	if args.command == "baseline":
		rows = build_baseline_rows(bundle.requests)
		issues = validate_output_rows(rows, bundle.requests)
		if issues:
			raise OutputValidationError(issues)
		write_output(args.output, rows)
		print(f"Wrote {len(rows)} structurally valid baseline rows to {args.output}")
		return 0

	validate_output_file(
		args.output,
		bundle.requests,
		bundle,
		deterministic_message_entries_by_request(bundle),
	)
	print(f"Validated {args.output}: structure and row coverage are valid")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
