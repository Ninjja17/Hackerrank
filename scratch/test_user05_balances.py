from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, '.')
from loader import load_dataset
from scratch.test_prototype_accuracy import prototype_simulate_cashflow, prototype_detect_recurrences, safe_amount_today, earliest_safe_date

bundle = load_dataset(Path('dataset'))
req_05 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_05'][0]
prof_05 = [p for p in bundle.financial_profiles if p.user_id == req_05.user_id][0]

res = prototype_simulate_cashflow(prof_05, req_05, bundle.financial_events, bundle.exchange_rates)
print("Entries count:", len(res.entries))
for e in res.entries[:15]:
    print(f"  {e.date} | {e.amount} | {e.description}")

min_bal = min(b for _, b in res.balances)
print("Minimum balance in 90 days:", min_bal)
print("Min balance required:", prof_05.minimum_balance_to_keep)
print("Safe headroom:", min_bal - prof_05.minimum_balance_to_keep)
print("Requested amount:", req_05.requested_amount)
print("Earliest safe date:", earliest_safe_date(res, req_05.requested_amount))
