from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from evidence import resolve_image_amounts, reconcile_events_with_messages
from cashflow import simulate_cashflow
from planner import _payment_entries

bundle = load_dataset(Path('dataset'))
resolved, _, _ = resolve_image_amounts(bundle.images, Path('dataset/media/images'))

for req_id in ['request_12', 'request_17']:
    sample = [s for s in bundle.sample_requests if s.request.request_id == req_id][0]
    req = sample.request
    prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
    evs, extra = reconcile_events_with_messages(bundle.financial_events, bundle.messages, req.user_id, req.request_id, req.request_date)
    options = [o for o in bundle.payment_options if o.request_id == req_id and o.payment_method == 'installments']
    print(f"=== {req_id} ===")
    for opt in options:
        entries = _payment_entries(req, opt)
        res = simulate_cashflow(prof, req, evs, bundle.exchange_rates, additional_entries=(*extra, *entries), resolved_amounts=resolved)
        min_b = min(b for _, b in res.balances)
        min_req = prof.minimum_balance_to_keep
        print(f"  Option {opt.payment_option_id}: min_balance={min_b}, min_required={min_req}, is_safe={res.is_safe}, deficit={min_req - min_b if not res.is_safe else 0}")
