# integration/regression_check.py
import pandas as pd
from pathlib import Path
import os

RUN = Path(__file__).resolve().parent / "run"

for m, out in [("M1", "M1/outputs/residual_table.csv"), ("M2", "flags_out.csv"), ("M3", "alerts_all.csv")]:
    golden_path = Path(f"golden_{m}.csv")
    new_path = RUN / f"{m}_work" / out
    
    if not golden_path.exists():
        print(f"{m}: Skipped regression check (golden_{m}.csv not found)")
        continue
        
    golden = pd.read_csv(golden_path)
    new = pd.read_csv(new_path)
    try:
        pd.testing.assert_frame_equal(golden, new, check_like=True)
        print(m, "OK: identical to standalone output")
    except AssertionError as e:
        print(m, "DIFFERS (expected if its input now comes from the previous member):", str(e)[:200])
