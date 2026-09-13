from pathlib import Path
import sys
sys.path.insert(0, 'code')
sys.path.insert(0, 'code/evaluation')

import importlib.util
spec = importlib.util.spec_from_file_location("evaluator", "code/evaluation/main.py")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)

print("Running baseline evaluation:")
checked, matched, mismatches, field_mismatches = evaluator.compare_samples(Path("dataset"), Path("evaluation_report.csv"))
print(f"Checked: {checked}, Matched: {matched}, Mismatches: {len(mismatches)}")
print(f"Field mismatches: {field_mismatches}")
