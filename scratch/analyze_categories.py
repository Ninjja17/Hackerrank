from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from collections import defaultdict
from statistics import median

bundle = load_dataset(Path('dataset'))

for user_id in ['user_01', 'user_02', 'user_03', 'user_04', 'user_05', 'user_06', 'user_07', 'user_08']:
    user_events = [e for e in bundle.financial_events if e.user_id == user_id and e.status == 'settled' and e.direction == 'debit']
    by_cat = defaultdict(list)
    for e in user_events:
        by_cat[e.category].append(e)
    
    print(f"\n=== {user_id} ===")
    for cat, evs in sorted(by_cat.items()):
        if len(evs) >= 3:
            evs.sort(key=lambda x: x.event_date)
            intervals = [(r.event_date - l.event_date).days for l, r in zip(evs, evs[1:])]
            med_int = median(intervals)
            amounts = [e.amount for e in evs if e.amount is not None]
            med_amt = median(amounts)
            print(f"  {cat:20s}: count={len(evs):2d}, med_interval={med_int:4.1f} days, med_amt={med_amt}")
