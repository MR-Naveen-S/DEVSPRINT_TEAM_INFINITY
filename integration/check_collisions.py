# integration/check_collisions.py
import hashlib, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
seen = collections.defaultdict(list)
for m in ["M1", "M2", "M3", "M4"]:
    for p in (ROOT / m).rglob("*"):
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
            seen[p.name].append((m, hashlib.md5(p.read_bytes()).hexdigest()[:8]))
for name, items in seen.items():
    if len({m for m, _ in items}) > 1:
        same = len({h for _, h in items}) == 1
        print(f"{name:30} {items}  {'(identical)' if same else '(DIFFERENT CONTENT)'}")
