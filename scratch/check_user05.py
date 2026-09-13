from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow

bundle = load_dataset(Path('dataset'))
req_05 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_05'][0]
prof_05 = [p for p in bundle.financial_profiles if p.user_id == req_05.user_id][0]

print(f"req_05: req_date={req_05.request_date}, amount={req_05.requested_amount}")
print(f"prof_05: bal={prof_05.current_available_balance}, min={prof_05.minimum_balance_to_keep}")

m05 = [m for m in bundle.messages if m.user_id == 'user_05']
for m in m05:
    print(f"Message: {m.sent_at} | {m.related_event_id} | {m.message_text}")

e05 = [e for e in bundle.financial_events if e.user_id == 'user_05']
for e in sorted(e05, key=lambda x: x.event_date)[-20:]:
    print(f"{e.event_date} | {e.event_id} | {e.direction} | {e.amount} {e.currency} | {e.category} | {e.status} | {e.description}")
