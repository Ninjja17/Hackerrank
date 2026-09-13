from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow, safe_amount_today, earliest_safe_date
from models import FinancialEvent, CashFlowEntry
from datetime import date
from decimal import Decimal

bundle = load_dataset(Path('dataset'))
req_08 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_08'][0]
prof_08 = [p for p in bundle.financial_profiles if p.user_id == req_08.user_id][0]

# Modify the latest salary event or add next salary to 1422.85
events = list(bundle.financial_events)
for i, e in enumerate(events):
    if e.user_id == 'user_08' and e.category == 'salary' and e.event_date == date(2025, 1, 15):
        events[i] = FinancialEvent(
            event_id=e.event_id,
            user_id=e.user_id,
            event_type=e.event_type,
            description=e.description,
            category=e.category,
            direction=e.direction,
            amount=Decimal('1422.85'),
            currency=e.currency,
            event_date=e.event_date,
            settlement_date=e.settlement_date,
            status=e.status,
            linked_event_id=e.linked_event_id,
            flexibility=e.flexibility,
            minimum_allowed_amount=e.minimum_allowed_amount,
        )

res = simulate_cashflow(prof_08, req_08, events, bundle.exchange_rates)
safe = safe_amount_today(res, req_08.requested_amount)
earliest = earliest_safe_date(res, req_08.requested_amount)
print(f"req_08: expected safe=284.57, earliest=2025-04-15")
print(f"req_08 with 1422.85 salary: safe={safe}, earliest={earliest}")
