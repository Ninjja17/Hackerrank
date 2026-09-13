from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from cashflow import simulate_cashflow, earliest_safe_date, safe_amount_today

bundle = load_dataset(Path('dataset'))
req_13 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_13'][0]
prof_13 = [p for p in bundle.financial_profiles if p.user_id == req_13.user_id][0]

# Let's inspect the actual groceries for user_13
user_13_groceries = [e for e in bundle.financial_events if e.user_id == 'user_13' and e.category == 'groceries' and e.status == 'settled']
user_13_groceries.sort(key=lambda x: x.event_date)
print(f"User 13 total groceries events: {len(user_13_groceries)}")
for g in user_13_groceries[-10:]:
    print(g.event_date, g.amount, g.description)
