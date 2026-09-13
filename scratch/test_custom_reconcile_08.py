from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, '.')
from loader import load_dataset
from scratch.test_prototype_accuracy import custom_reconcile

bundle = load_dataset(Path('dataset'))
req = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_08'][0]

evs, extra = custom_reconcile(bundle.financial_events, bundle.messages, req.user_id, req.request_id, req.request_date)
print("Extra count:", len(extra))
for ex in extra:
    print("Extra:", ex)

for e in evs:
    if e.user_id == 'user_08' and e.category == 'salary':
        print("Salary:", e.event_date, e.amount, e.description)
