from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow, safe_amount_today, earliest_safe_date
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
safe = safe_amount_today(res, req_03.requested_amount)
earliest = earliest_safe_date(res, req_03.requested_amount)
print(f"req_03: expected safe=873000, earliest=2019-11-15")
print(f"req_03 with resolved event_253: safe={safe}, earliest={earliest}")
