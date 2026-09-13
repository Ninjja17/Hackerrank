from pathlib import Path
import sys
import re
sys.path.insert(0, 'code')
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from collections import defaultdict
from loader import load_dataset
from cashflow import CurrencyConverter, _canonical_events, _event_date, _is_usable_event, _cash_effect, _add_months, _recurrence_entries, Recurrence, safe_amount_today, earliest_safe_date
from models import CashFlowEntry, SimulationResult, FinancialEvent
from evidence import VERIFIED_IMAGE_AMOUNTS, reconcile_events_with_messages, resolve_image_amounts

bundle = load_dataset(Path('dataset'))
resolved_amounts, _, _ = resolve_image_amounts(bundle.images, Path('dataset/media/images'))

def prototype_detect_recurrences(events, user_id, before_date, profile):
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
            if event.event_type in {"subscription", "debt_payment"} or event.flexibility in {"stoppable", "reducible", "reducible_or_stoppable"}:
                key = (event.category, event.direction, event.currency, " ".join(event.description.lower().split()), True)
            else:
                key = (event.category, event.direction, event.currency, "", False)
            grouped[key].append(event)

    recurrences = []
    for (cat, direction, currency, desc_key, is_subscription), group in grouped.items():
        ordered = sorted(group, key=lambda e: e.event_date)
        if len(ordered) < 2:
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
        desc = latest.description if is_subscription else f"Regular {cat}"
        recurrences.append(
            Recurrence(
                user_id=user_id,
                category=cat,
                direction=direction,
                amount=amount,
                currency=currency,
                interval_days=typical_interval,
                next_date=latest.event_date + timedelta(days=typical_interval),
                description=desc,
                source_event_id=latest.event_id,
                is_monthly=is_monthly,
                latest_event_date=latest.event_date,
            )
        )
    return recurrences

def prototype_simulate_cashflow(
    profile,
    request,
    events,
    rates,
    *,
    additional_entries = (),
    spending_changes = None,
    resolved_amounts = None,
):
    end_date = request.request_date + timedelta(days=89)
    converter = CurrencyConverter(rates)
    user_events = _canonical_events(event for event in events if event.user_id == request.user_id)
    unresolved = []
    entries = list(additional_entries)

    for event in user_events:
        event_date = _event_date(event, request.request_date)
        event_amount = event.amount
        if event_amount is None and resolved_amounts is not None:
            event_amount = resolved_amounts.get(event.event_id)
        if event_amount is None:
            if request.request_date <= event_date <= end_date:
                unresolved.append(event.event_id)
            continue
        if event_date < request.request_date or event_date > end_date:
            continue
        if not _is_usable_event(event):
            continue
        try:
            converted = converter.convert(
                event_amount, event.currency, profile.home_currency, event_date
            )
        except Exception:
            unresolved.append(event.event_id)
            continue
        if spending_changes and event.event_id in spending_changes:
            converted = converter.convert(
                spending_changes[event.event_id],
                profile.home_currency,
                profile.home_currency,
                event_date,
            )
        entries.append(
            CashFlowEntry(
                date=max(event_date, request.request_date),
                amount=_cash_effect(event, converted),
                source_id=event.event_id,
                source_type="financial_event",
                description=event.description,
            )
        )

    recurrences = prototype_detect_recurrences(
        events,
        request.user_id,
        request.request_date,
        profile,
    )

    adjusted_recurrences = []
    for recurrence in recurrences:
        if not spending_changes or recurrence.source_event_id not in spending_changes:
            adjusted_recurrences.append(recurrence)
            continue
        adjusted_amount = spending_changes[recurrence.source_event_id]
        if adjusted_amount <= 0:
            continue
        adjusted_recurrences.append(
            Recurrence(
                user_id=recurrence.user_id,
                category=recurrence.category,
                direction=recurrence.direction,
                amount=adjusted_amount,
                currency=recurrence.currency,
                interval_days=recurrence.interval_days,
                next_date=recurrence.next_date,
                description=recurrence.description,
                source_event_id=recurrence.source_event_id,
                is_monthly=recurrence.is_monthly,
                latest_event_date=recurrence.latest_event_date,
            )
        )

    for recurrence in adjusted_recurrences:
        try:
            entries.extend(
                _recurrence_entries(
                    (recurrence,),
                    request.request_date,
                    end_date,
                    profile.home_currency,
                    converter,
                )
            )
        except Exception:
            unresolved.append(recurrence.source_event_id)

    all_sal_events = [
        e for e in user_events
        if e.category == "salary"
        and e.direction == "credit"
        and e.status in {"settled", "scheduled"}
    ]
    if all_sal_events:
        latest_sal = max(all_sal_events, key=lambda e: _event_date(e, request.request_date))
        if "final" in latest_sal.description.lower():
            sal_events = []
        else:
            sal_events = [
                e for e in all_sal_events
                if (e.amount is not None or (resolved_amounts and e.event_id in resolved_amounts))
                and "arrears" not in e.description.lower()
            ]
    else:
        sal_events = []
    
    # Check if employer message updated upcoming salary
    for entry in additional_entries:
        if "salary" in entry.description.lower() and entry.amount > 0 and not any(e.date == entry.date for e in entries):
            entries.append(entry)
    sal_dates_in_events = {
        _event_date(e, request.request_date) for e in sal_events
    } | {
        entry.date for entry in additional_entries if "salary" in entry.description.lower()
    }

    if sal_events:
        sal_event = max(
            sal_events,
            key=lambda event: _event_date(event, request.request_date),
        )
        sal_amt = sal_event.amount
        if sal_amt is None and resolved_amounts is not None:
            sal_amt = resolved_amounts.get(sal_event.event_id)
        if sal_amt is not None:
            sal_date = _event_date(sal_event, request.request_date)
            n = 1
            while True:
                nxt = _add_months(sal_date, n)
                if nxt > end_date:
                    break
                if nxt >= request.request_date and not any(abs((nxt - d).days) <= 5 for d in sal_dates_in_events):
                    try:
                        conv = converter.convert(
                            sal_amt, sal_event.currency, profile.home_currency, nxt
                        )
                        entries.append(
                            CashFlowEntry(
                                date=nxt,
                                amount=conv,
                                source_id="recurring_salary",
                                source_type="salary_recurrence",
                                description="ongoing monthly salary",
                            )
                        )
                        sal_dates_in_events.add(nxt)
                    except Exception:
                        pass
                n += 1

    daily_changes = defaultdict(Decimal)
    for entry in entries:
        daily_changes[entry.date] += entry.amount

    balances = []
    balance = profile.current_available_balance
    current = request.request_date
    while current <= end_date:
        balance += daily_changes[current]
        balances.append((current, balance))
        current += timedelta(days=1)

    return SimulationResult(
        request_date=request.request_date,
        end_date=end_date,
        minimum_balance=profile.minimum_balance_to_keep,
        balances=tuple(balances),
        entries=tuple(sorted(entries, key=lambda entry: (entry.date, entry.source_id))),
        unresolved_event_ids=tuple(sorted(set(unresolved))),
    )

def custom_reconcile(events, messages, user_id, request_id, request_date):
    ev_reconciled, extra = reconcile_events_with_messages(events, messages, user_id, request_id, request_date)
    ev_list = list(ev_reconciled)
    extra_list = list(extra)
    for m in messages:
        if m.user_id == user_id and m.request_id in {None, request_id}:
            text = m.message_text.lower()
            if "salary" in text or "gaji" in text or "payroll" in text:
                m_amt = re.search(r"(?:EUR|IDR|USD|INR|ZAR)\s*([\d,.]+)", m.message_text)
                if m_amt:
                    raw_val = m_amt.group(1).replace(",", "").rstrip(".")
                    try:
                        val = Decimal(raw_val)
                    except Exception:
                        continue
                    # Check if there is an upcoming salary event
                    has_future_sal = any(e.user_id == user_id and e.category == "salary" and _event_date(e, request_date) >= request_date for e in ev_list)
                    if not has_future_sal and not any("salary" in e.description.lower() for e in extra_list):
                        # Add next salary on 15th
                        next_sal_date = date(request_date.year, request_date.month, 15)
                        if next_sal_date < request_date:
                            next_sal_date = _add_months(next_sal_date, 1)
                        extra_list.append(CashFlowEntry(
                            date=next_sal_date,
                            amount=val,
                            source_id=m.message_id,
                            source_type="message_evidence",
                            description="confirmed next salary credit",
                        ))
                        # Also update the latest settled salary event amount if needed
                        for i, e in enumerate(ev_list):
                            if e.user_id == user_id and e.category == "salary":
                                ev_list[i] = FinancialEvent(
                                    event_id=e.event_id,
                                    user_id=e.user_id,
                                    event_type=e.event_type,
                                    description=e.description,
                                    category=e.category,
                                    direction=e.direction,
                                    amount=val,
                                    currency=e.currency,
                                    event_date=e.event_date,
                                    settlement_date=e.settlement_date,
                                    status=e.status,
                                    linked_event_id=e.linked_event_id,
                                    flexibility=e.flexibility,
                                    minimum_allowed_amount=e.minimum_allowed_amount,
                                )
    return tuple(ev_list), tuple(extra_list)

# Test on the sample requests
matches = 0
for sample in bundle.sample_requests:
    req = sample.request
    expected = sample.output
    prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
    ev_reconciled, extra_entries = custom_reconcile(
        bundle.financial_events,
        bundle.messages,
        req.user_id,
        req.request_id,
        req.request_date,
    )
    res = prototype_simulate_cashflow(
        prof,
        req,
        ev_reconciled,
        bundle.exchange_rates,
        additional_entries=extra_entries,
        resolved_amounts=resolved_amounts,
    )
    safe = safe_amount_today(res, req.requested_amount)
    earliest = earliest_safe_date(res, req.requested_amount)
    is_earliest_match = (earliest == expected.earliest_date_for_full_payment)
    print(f"{req.request_id}: exp_safe={expected.amount_safe_to_pay}, act_safe={safe:.2f} | exp_earliest={expected.earliest_date_for_full_payment}, act_earliest={earliest} {'[MATCH]' if is_earliest_match else '[DIFF]'}")
