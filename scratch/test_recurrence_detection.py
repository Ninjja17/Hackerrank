import sys
sys.path.insert(0, 'code')
from pathlib import Path
from datetime import date
from loader import load_dataset
from cashflow import detect_recurrences

bundle = load_dataset(Path('dataset'))
events = bundle.financial_events

print("=== USER_08 recurrences detected ===")
rec_08 = detect_recurrences(events, 'user_08', date(2025, 2, 7))
for r in rec_08:
    print(r.category, r.amount, r.interval_days, r.is_monthly, r.description)

print("=== USER_06 recurrences detected ===")
rec_06 = detect_recurrences(events, 'user_06', date(2026, 1, 3))
for r in rec_06:
    print(r.category, r.amount, r.interval_days, r.is_monthly, r.description)
