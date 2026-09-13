from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

from loader import load_dataset
from llm_agent import deterministic_message_entries_by_request
from planner import decide_request
from cashflow import simulate_cashflow, safe_amount_today, earliest_safe_date
from evidence import resolve_image_amounts

def analyze():
    bundle = load_dataset(ROOT / "dataset")
    evidence_entries = deterministic_message_entries_by_request(bundle)
    requests = {request.request_id: request for request in bundle.requests}
    resolved_amounts, _, _ = resolve_image_amounts(
        bundle.images, ROOT / "dataset" / "media" / "images"
    )

    for sample in bundle.sample_requests:
        req = requests.get(sample.request.request_id, sample.request)
        profile = next(p for p in bundle.financial_profiles if p.user_id == req.user_id)
        user_events = tuple(e for e in bundle.financial_events if e.user_id == req.user_id)
        
        sim = simulate_cashflow(
            profile,
            req,
            user_events,
            bundle.exchange_rates,
            additional_entries=evidence_entries.get(req.request_id, ()),
            resolved_amounts=resolved_amounts,
        )
        
        actual = decide_request(bundle, req, evidence_entries.get(req.request_id, ()))
        
        print(f"=== {req.request_id} ({req.user_id}) ===")
        print(f"  Req Date: {req.request_date}, Amount: {req.requested_amount}, Desired Date: {req.desired_completion_date}, Partial: {req.allows_partial_payment}")
        print(f"  Profile: Balance={profile.current_available_balance}, Min={profile.minimum_balance_to_keep}, Methods={profile.payment_methods_user_will_consider}")
        print(f"  Sim min headroom: {min(b - sim.minimum_balance for _, b in sim.balances)}")
        print(f"  Sim balance on req_date: {dict(sim.balances)[req.request_date]}")
        print(f"  Actual: safe={actual.amount_safe_to_pay}, status={actual.affordability_status}, method={actual.recommended_payment_method}, plan={actual.payment_plan}, earliest={actual.earliest_date_for_full_payment}, changes={actual.spending_changes_needed}")
        print(f"  Expect: safe={sample.output.amount_safe_to_pay}, status={sample.output.affordability_status}, method={sample.output.recommended_payment_method}, plan={sample.output.payment_plan}, earliest={sample.output.earliest_date_for_full_payment}, changes={sample.output.spending_changes_needed}")
        print()

if __name__ == "__main__":
    analyze()
