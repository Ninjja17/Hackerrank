from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from evidence import resolve_image_amounts, reconcile_events_with_messages
from cashflow import simulate_cashflow
from planner import _payment_entries

bundle = load_dataset(Path('dataset'))
resolved, _, _ = resolve_image_amounts(bundle.images, Path('dataset/media/images'))

for req_id, opt_id in [('request_12', 'payment_option_33'), ('request_17', 'payment_option_47')]:
    sample = [s for s in bundle.sample_requests if s.request.request_id == req_id][0]
    req = sample.request
    prof = [p for p in bundle.financial_profiles if p.user_id == req.user_id][0]
    opt = [o for o in bundle.payment_options if o.payment_option_id == opt_id][0]
    entries = _payment_entries(req, opt)
    evs, extra = reconcile_events_with_messages(bundle.financial_events, bundle.messages, req.user_id, req.request_id, req.request_date)
    res = simulate_cashflow(prof, req, evs, bundle.exchange_rates, additional_entries=(*extra, *entries), resolved_amounts=resolved)
    print(f"=== {req_id} ({prof.user_id}) Entries ===")
    for e in res.entries:
        print(f"  {e.date} | {e.amount} | {e.source_id} | {e.description}")
