from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
from evidence import resolve_image_amounts
from planner import decide_request

bundle = load_dataset(Path('dataset'))
req_06 = [s.request for s in bundle.sample_requests if s.request.request_id == 'request_06'][0]
resolved, _, _ = resolve_image_amounts(bundle.images, Path('dataset/media/images'))

row = decide_request(bundle, req_06, (), resolved)
print("Decided row for request_06:")
print("  status:", row.affordability_status)
print("  method:", row.recommended_payment_method)
print("  safe_to_pay:", row.amount_safe_to_pay)
print("  earliest:", row.earliest_date_for_full_payment)
print("  spending_changes:", row.spending_changes_needed)
print("  plan:", row.payment_plan)
