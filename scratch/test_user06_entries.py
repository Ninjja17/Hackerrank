from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow

bundle = load_dataset(Path('dataset'))
req_06 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_06'][0]
prof_06 = [p for p in bundle.financial_profiles if p.user_id == req_06.user_id][0]

res = simulate_cashflow(prof_06, req_06, bundle.financial_events, bundle.exchange_rates)
print("Entries between Jan 3 and Jan 15 for user_06:")
for e in res.entries:
    if e.date < req_06.request_date.replace(day=15):
        print(f"  {e.date} | {e.amount} | {e.source_id} | {e.description}")
