from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow, safe_amount_today, earliest_safe_date
from collections import defaultdict
from statistics import median
from datetime import timedelta, date
from decimal import Decimal

bundle = load_dataset(Path('dataset'))
print("Testing baseline sample safe amounts:")
for sample in bundle.sample_requests:
    req = sample.request
    expected = sample.output
    prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
    res = simulate_cashflow(prof, req, bundle.financial_events, bundle.exchange_rates)
    safe = safe_amount_today(res, req.requested_amount)
    print(f"{req.request_id}: expected={expected.amount_safe_to_pay}, actual={safe}, diff={expected.amount_safe_to_pay - safe}")

