from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, '.')
from loader import load_dataset
from scratch.test_prototype_accuracy import custom_reconcile, prototype_simulate_cashflow, earliest_safe_date

bundle = load_dataset(Path('dataset'))
req = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_08'][0]
prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
evs, extra = custom_reconcile(bundle.financial_events, bundle.messages, req.user_id, req.request_id, req.request_date)
res = prototype_simulate_cashflow(prof, req, evs, bundle.exchange_rates, additional_entries=extra)

print("Balances in April 2025:")
for d, b in res.balances:
    if d.month in {4, 5}:
        headroom = b - prof.minimum_balance_to_keep
        if d.day in {1, 14, 15, 16, 30}:
            print(f"  {d}: bal={b}, headroom={headroom}")
