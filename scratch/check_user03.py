from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset

bundle = load_dataset(Path('dataset'))
m03 = [m for m in bundle.messages if m.user_id == 'user_03']
for m in m03:
    print(f"Message: {m.sent_at} | {m.related_event_id} | {m.message_text}")

e03 = [e for e in bundle.financial_events if e.user_id == 'user_03' and e.category == 'salary']
for e in e03:
    print(f"Salary: {e.event_date} | {e.amount} {e.currency} | {e.status} | {e.description}")
