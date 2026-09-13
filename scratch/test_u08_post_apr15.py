from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, '.')
from loader import load_dataset
from scratch.test_prototype_accuracy import custom_reconcile, prototype_simulate_cashflow

bundle = load_dataset(Path('dataset'))
req = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_08'][0]
prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
evs, extra = custom_reconcile(bundle.financial_events, bundle.messages, req.user_id, req.request_id, req.request_date)
res = prototype_simulate_cashflow(prof, req, evs, bundle.exchange_rates, additional_entries=extra)

print("Balances from 2025-04-15 onwards:")
for d, b in res.balances:
    if d >= req.request_date.replace(month=4, day=15):
        headroom = b - prof.minimum_balance_to_keep
        print(f"  {d}: bal={b}, headroom={headroom}, safe_for_996.60? {headroom >= 996.6}")
