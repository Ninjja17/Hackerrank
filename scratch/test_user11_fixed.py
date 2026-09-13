from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, '.')
from decimal import Decimal
from loader import load_dataset
from scratch.test_prototype_accuracy import prototype_simulate_cashflow, safe_amount_today, earliest_safe_date
from models import FinancialEvent

bundle = load_dataset(Path('dataset'))
req = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_11'][0]
prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]

# Replace salary with confirmed 38,760,000 IDR
events = []
for e in bundle.financial_events:
    if e.user_id == 'user_11' and e.category == 'salary':
        if 'commission' in e.description.lower():
            continue
        events.append(FinancialEvent(
            event_id=e.event_id,
            user_id=e.user_id,
            event_type=e.event_type,
            description=e.description,
            category=e.category,
            direction=e.direction,
            amount=Decimal('38760000'),
            currency=e.currency,
            event_date=e.event_date,
            settlement_date=e.settlement_date,
            status=e.status,
            linked_event_id=e.linked_event_id,
            flexibility=e.flexibility,
            minimum_allowed_amount=e.minimum_allowed_amount,
        ))
    else:
        events.append(e)

res = prototype_simulate_cashflow(prof, req, events, bundle.exchange_rates)
safe = safe_amount_today(res, req.requested_amount)
earliest = earliest_safe_date(res, req.requested_amount)

print(f"request_11: expected safe=12510645, earliest=2025-07-15")
print(f"request_11 with confirmed 38.76M base salary: safe={safe}, earliest={earliest}")
