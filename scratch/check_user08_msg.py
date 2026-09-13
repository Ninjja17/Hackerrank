from pathlib import Path
import sys
sys.path.insert(0, 'code')
from loader import load_dataset

bundle = load_dataset(Path('dataset'))
m08 = [m for m in bundle.messages if m.user_id == 'user_08']
for m in m08:
    print(f"Message: {m.sent_at} | {m.related_event_id} | {m.message_text}")
