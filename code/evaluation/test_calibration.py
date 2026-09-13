import sys
from pathlib import Path
from decimal import Decimal
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

from loader import load_dataset
from evaluation.main import compare_samples

def run():
    bundle = load_dataset(ROOT / "dataset")
    checked, matched, mismatches, field_mismatches = compare_samples(ROOT / "dataset")
    print(f"checked={checked}, matched={matched}")
    print("field_mismatches:", json.dumps(field_mismatches, indent=2))
    for m in mismatches[:10]:
        print(m)

if __name__ == "__main__":
    run()
