from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow
from decimal import Decimal

bundle = load_dataset(Path('dataset'))
req_03 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_03'][0]
prof_03 = [p for p in bundle.financial_profiles if p.user_id == req_03.user_id][0]

res = simulate_cashflow(
    prof_03,
    req_03,
    bundle.financial_events,
    bundle.exchange_rates,
    resolved_amounts={'event_253': Decimal('4365000')},
)
print("Entries in simulation:")
for e in res.entries:
    print(f"  {e.date} | {e.amount} | {e.source_id} | {e.description}")
