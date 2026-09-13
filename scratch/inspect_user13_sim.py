from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow, earliest_safe_date, safe_amount_today

bundle = load_dataset(Path('dataset'))
req_13 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_13'][0]
prof_13 = [p for p in bundle.financial_profiles if p.user_id == req_13.user_id][0]

res = simulate_cashflow(prof_13, req_13, bundle.financial_events, bundle.exchange_rates)
print("Entries in simulation:")
for e in res.entries:
    print(f"  {e.date} | {e.amount} | {e.source_id} | {e.description}")

print("\nEarliest safe date for 941.60:")
print(earliest_safe_date(res, req_13.requested_amount))
print("Desired completion date:", req_13.desired_completion_date)
