from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from evidence import reconcile_events_with_messages
from cashflow import _event_date

bundle = load_dataset(Path('dataset'))
req = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_08'][0]

ev_reconciled, extra = reconcile_events_with_messages(
    bundle.financial_events,
    bundle.messages,
    req.user_id,
    req.request_id,
    req.request_date,
)

print("extra from reconcile_events_with_messages:", extra)
for e in ev_reconciled:
    if e.user_id == req.user_id and e.category == 'salary':
        print("Salary event date:", _event_date(e, req.request_date), ">= req_date?", _event_date(e, req.request_date) >= req.request_date)
