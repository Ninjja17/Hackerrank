from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, '.')
from datetime import timedelta
from loader import load_dataset
from scratch.test_prototype_accuracy import custom_reconcile, prototype_simulate_cashflow, safe_amount_today

bundle = load_dataset(Path('dataset'))

def cycle_safe_date(result, amount, horizon_days=35):
    balance_by_date = dict(result.balances)
    dates = sorted(balance_by_date)
    for i, current in enumerate(dates):
        sub_dates = [d for d in dates if current <= d <= current + timedelta(days=horizon_days)]
        if all(balance_by_date[d] - amount >= result.minimum_balance for d in sub_dates):
            return current
    return None

print("Testing cycle_safe_date on all samples:")
for sample in bundle.sample_requests:
    req = sample.request
    expected = sample.output
    prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
    evs, extra = custom_reconcile(bundle.financial_events, bundle.messages, req.user_id, req.request_id, req.request_date)
    res = prototype_simulate_cashflow(prof, req, evs, bundle.exchange_rates, additional_entries=extra)
    c_earliest = cycle_safe_date(res, req.requested_amount, horizon_days=35)
    match = (c_earliest == expected.earliest_date_for_full_payment)
    print(f"{req.request_id}: exp={expected.earliest_date_for_full_payment}, cycle={c_earliest} {'[MATCH]' if match else '[DIFF]'}")
