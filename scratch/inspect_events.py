import csv

def load_csv(path):
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

events = load_csv('dataset/financial_events.csv')
requests = {r['request_id']: r for r in load_csv('dataset/sample_requests.csv')}
profiles = {r['user_id']: r for r in load_csv('dataset/financial_profiles.csv')}

for req_id in ['request_06', 'request_08']:
    req = requests[req_id]
    u = req['user_id']
    prof = profiles[u]
    print(f"================== {req_id} ({u}) ==================")
    print(f"Request Date: {req['request_date']}, Requested: {req['requested_amount']}, Safe: {req['amount_safe_to_pay']}")
    print(f"Balance: {prof['current_available_balance']}, Min: {prof['minimum_balance_to_keep']}")
    u_events = [e for e in events if e['user_id'] == u]
    for e in sorted(u_events, key=lambda x: x['event_date']):
        print(f"{e['event_date']} | {e['event_id']} | {e['direction']} | {e['amount']} {e['currency']} | {e['category']} | {e['status']} | {e['event_type']} | {e['description']}")
