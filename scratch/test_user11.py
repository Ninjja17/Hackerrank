from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, '.')
from loader import load_dataset
from scratch.test_prototype_accuracy import prototype_simulate_cashflow

bundle = load_dataset(Path('dataset'))
req = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_11'][0]
prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]

print(f"user_11: bal={prof.current_available_balance}, min={prof.minimum_balance_to_keep}")
print(f"protect: {prof.expense_categories_to_protect}")
print(f"reduce: {prof.expense_categories_user_is_willing_to_reduce}")
print(f"stop: {prof.expense_categories_user_is_willing_to_stop}")

res = prototype_simulate_cashflow(prof, req, bundle.financial_events, bundle.exchange_rates)
for e in res.entries[:15]:
    print(f"  {e.date} | {e.amount} | {e.source_id} | {e.description}")

min_bal = min(b for _, b in res.balances)
print("Min balance in simulation:", min_bal)
print("Headroom:", min_bal - prof.minimum_balance_to_keep)
print("Requested amount:", req.requested_amount)
