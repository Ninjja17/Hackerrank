from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow

bundle = load_dataset(Path('dataset'))
req_13 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_13'][0]
prof_13 = [p for p in bundle.financial_profiles if p.user_id == req_13.user_id][0]

print(f"req_13: req_date={req_13.request_date}, amount={req_13.requested_amount}")
print(f"prof_13: bal={prof_13.current_available_balance}, min={prof_13.minimum_balance_to_keep}")

m13 = [m for m in bundle.messages if m.user_id == 'user_13']
for m in m13:
    print(f"Message: {m.sent_at} | {m.related_event_id} | {m.message_text}")

e13 = [e for e in bundle.financial_events if e.user_id == 'user_13' and e.category == 'salary']
for e in e13:
    print(f"Salary: {e.event_date} | {e.amount} {e.currency} | {e.status} | {e.description}")
