# integration/adapters.py
import pandas as pd

RENAMES = {
    "M1_to_M2": {"campaign_id": "campaign"},
    "M2_to_M3": {},
    "M3_to_M4": {},
}

def adapt(df, key, defaults=None):
    if key == "M1_to_M2":
        df = df.dropna(subset=['actual', 'expected', 'mad', 'noise_floor', 'robust_z'])
    out = df.rename(columns=RENAMES.get(key, {})).copy()
    for col, val in (defaults or {}).items():
        if col not in out.columns:
            out[col] = val
    return out
