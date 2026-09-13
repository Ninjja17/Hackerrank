from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset
bundle = load_dataset(Path('dataset'))

p12 = [p for p in bundle.financial_profiles if p.user_id == 'user_12'][0]
print("user_12 reduce:", p12.expense_categories_user_is_willing_to_reduce)
print("user_12 stop:", p12.expense_categories_user_is_willing_to_stop)

p17 = [p for p in bundle.financial_profiles if p.user_id == 'user_17'][0]
print("user_17 reduce:", p17.expense_categories_user_is_willing_to_reduce)
print("user_17 stop:", p17.expense_categories_user_is_willing_to_stop)

p11 = [p for p in bundle.financial_profiles if p.user_id == 'user_11'][0]
print("user_11 reduce:", p11.expense_categories_user_is_willing_to_reduce)
print("user_11 stop:", p11.expense_categories_user_is_willing_to_stop)
