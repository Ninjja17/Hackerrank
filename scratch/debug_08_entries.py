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
print("Entries in simulation for user_08:")
for e in res.entries:
    print(f"  {e.date} | {e.amount} | {e.source_id} | {e.description}")

print("Balances in simulation for user_08 (around 2025-04-15):")
for d, b in res.balances:
    if d.month == 4 and d.day in {13, 14, 15, 16, 17}:
        print(f"  {d}: bal={b}, headroom={b - prof.minimum_balance_to_keep}")
