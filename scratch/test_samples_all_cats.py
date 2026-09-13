from pathlib import Path
import sys
sys.path.insert(0, 'code')
from collections import defaultdict
from statistics import median
from datetime import date, timedelta
from decimal import Decimal
from loader import load_dataset
from evidence import resolve_image_amounts, reconcile_events_with_messages
from cashflow import (
    CurrencyConverter,
    _canonical_events,
    _event_date,
    _is_usable_event,
    _cash_effect,
    _add_months,
    _recurrence_entries,
    Recurrence,
    SimulationResult,
    safe_amount_today,
    earliest_safe_date,
)
from planner import _payment_entries, _safe_plan, _candidate

bundle = load_dataset(Path('dataset'))
resolved, _, _ = resolve_image_amounts(bundle.images, Path('dataset/media/images'))

RECURRING_EVENT_TYPES = frozenset({"subscription", "debt_payment"})
RECURRING_EXPENSE_CATEGORIES = frozenset(
    {"rent", "housing", "utilities", "insurance", "education"}
)
VARIABLE_EXPENSE_CATEGORIES = frozenset(
    {"groceries", "transport", "dining", "shopping", "entertainment", "healthcare", "family_support", "gym"}
)

def test_detect_recurrences(events, user_id, before_date, profile):
    grouped = defaultdict(list)
    for event in events:
        if (
            event.user_id == user_id
            and event.event_date < before_date
            and event.amount is not None
            and event.status == "settled"
            and event.direction == "debit"
            and event.event_type != "investment_valuation"
        ):
            is_explicit = event.event_type in RECURRING_EVENT_TYPES or event.category in RECURRING_EXPENSE_CATEGORIES
            is_flexible_sub = (
                event.event_type in RECURRING_EVENT_TYPES
                and event.flexibility in {"stoppable", "reducible", "reducible_or_stoppable"}
            )
            # Only flexible expenses in categories user wants to change
            is_permitted_flexible = (
                event.flexibility in {"stoppable", "reducible", "reducible_or_stoppable"}
                and (
                    event.category in profile.expense_categories_user_is_willing_to_stop
                    or event.category in profile.expense_categories_user_is_willing_to_reduce
                )
            )
            is_variable = (
                event.category in VARIABLE_EXPENSE_CATEGORIES
                or event.category in profile.expense_categories_to_protect
            )
            if not (is_explicit or is_permitted_flexible or is_variable):
                continue

            if is_explicit or is_permitted_flexible:
                # Keep distinct by description
                key = (event.category, event.direction, event.currency, " ".join(event.description.lower().split()), True)
            else:
                key = (event.category, event.direction, event.currency, "", False)
            grouped[key].append(event)

    recurrences = []
    for (category, direction, currency, desc_key, is_individual), group in grouped.items():
        ordered = sorted(group, key=lambda e: e.event_date)
        minimum_obs = 2 if is_individual else 3
        if len(ordered) < minimum_obs:
            continue
        intervals = [(right.event_date - left.event_date).days for left, right in zip(ordered, ordered[1:])]
        if not intervals:
            continue
        typical_interval = int(median(intervals))
        if typical_interval < 4 or typical_interval > 45:
            continue
        amount = median(e.amount for e in ordered if e.amount is not None)
        latest = ordered[-1]
        is_monthly = (
            28 <= typical_interval <= 31
            and len(set(e.event_date.day for e in ordered)) <= 2
            and (ordered[-1].event_date.day == ordered[0].event_date.day or len(ordered) >= 3)
        )
        desc = latest.description if is_individual else f"Regular {category}"
        recurrences.append(
            Recurrence(
                user_id=user_id,
                category=latest.category,
                direction=latest.direction,
                amount=amount,
                currency=latest.currency,
                interval_days=typical_interval,
                next_date=latest.event_date + timedelta(days=typical_interval),
                description=desc,
                source_event_id=latest.event_id,
                is_monthly=is_monthly,
                latest_event_date=latest.event_date,
            )
        )
    return recurrences

print("Testing on request_12 and request_17:")
for req_id, opt_id in [('request_12', 'payment_option_33'), ('request_17', 'payment_option_47')]:
    sample = [s for s in bundle.sample_requests if s.request.request_id == req_id][0]
    req = sample.request
    prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
    opt = [o for o in bundle.payment_options if o.payment_option_id == opt_id][0]
    entries = _payment_entries(req, opt)
    recs = test_detect_recurrences(bundle.financial_events, req.user_id, req.request_date, prof)
    print(f"{req_id} recurrences detected ({len(recs)}):")
    for r in recs:
        print(f"  {r.category}: {r.amount} every {r.interval_days}d ({r.description})")
