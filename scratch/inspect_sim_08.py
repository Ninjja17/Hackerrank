from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow

bundle = load_dataset(Path('dataset'))
req_08 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_08'][0]
prof_08 = [p for p in bundle.financial_profiles if p.user_id == req_08.user_id][0]

res = simulate_cashflow(prof_08, req_08, bundle.financial_events, bundle.exchange_rates)
print(f"Profile balance: {prof_08.current_available_balance}, min: {prof_08.minimum_balance_to_keep}")
print("Daily entries in simulation:")
for e in res.entries:
    print(f"  {e.date} | {e.amount} | {e.source_id} | {e.description}")

print("Daily balances (first 20 days):")
for d, bal in res.balances[:20]:
    print(f"  {d}: bal={bal}, headroom={bal - prof_08.minimum_balance_to_keep}")
