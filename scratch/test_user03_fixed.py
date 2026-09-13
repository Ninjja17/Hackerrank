from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow, safe_amount_today, earliest_safe_date
from models import FinancialEvent
from datetime import date
from decimal import Decimal

bundle = load_dataset(Path('dataset'))
req_03 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_03'][0]
prof_03 = [p for p in bundle.financial_profiles if p.user_id == req_03.user_id][0]

events = []
for e in bundle.financial_events:
    if e.event_id == 'event_253':
        events.append(FinancialEvent(
            event_id=e.event_id,
            user_id=e.user_id,
            event_type=e.event_type,
            description=e.description,
            category=e.category,
            direction=e.direction,
            amount=Decimal('4365000'),
            currency=e.currency,
            event_date=date(2019, 8, 15),
            settlement_date=date(2019, 8, 15),
            status=e.status,
            linked_event_id=e.linked_event_id,
            flexibility=e.flexibility,
            minimum_allowed_amount=e.minimum_allowed_amount,
        ))
    elif e.event_id == 'event_211':
        # ignore arrears as salary recurrence
        continue
    else:
        events.append(e)

res = simulate_cashflow(
    prof_03,
    req_03,
    events,
    bundle.exchange_rates,
)
print(f"req_03 expected safe: 873000, earliest: 2019-11-15")
safe = safe_amount_today(res, req_03.requested_amount)
earliest = earliest_safe_date(res, req_03.requested_amount)
print(f"req_03 actual: safe={safe}, earliest={earliest}")
