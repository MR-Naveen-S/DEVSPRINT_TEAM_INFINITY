# PS-04: Connecting the M1 to M4 Folders Without Merging

## Core idea

**Never edit, move, or merge the member folders.** Leave `M1/` to `M4/` exactly as they are and add one new folder beside them, `integration/`, that *runs* each member's code in isolation and passes data between them through files. Because nothing is merged:

- duplicate file names (`utils.py`, `config.py`, `main.py`) cannot clash;
- different implementation styles do not matter;
- every member's original features keep working, because their code is never touched.

```
project/
  M1/            <- untouched
  M2/            <- untouched
  M3/            <- untouched
  M4/            <- untouched
  integration/
    members.py        # where each member's entry point and outputs are
    adapters.py       # column renaming between member outputs and inputs
    contracts.py      # required columns for each hand-off
    run_pipeline.py   # chains M1 -> M2 -> M3 -> M4
    check_collisions.py
    regression_check.py
    run/              # all generated files go here (safe to delete)
```

## Step 0: Make a safety copy (5 min)

1. Commit each folder, or zip it: `zip -r backup_M1.zip M1` (repeat for M2 to M4). If you use git: `git tag pre-integration`.
2. Tell everyone: **from now on member code is frozen**. Bug fixes go through the owner, and only as small additive changes.

## Step 1: Inventory each member (10 min, each member fills this in)

Every member answers these for their own folder, then pastes the answers into `integration/members.py`:

| Question | Example |
|---|---|
| Entry command (run from inside their folder) | `python main.py data.csv` |
| Input they read and where (path or argument) | `data.csv` in the folder, or `argv[1]` |
| Outputs they write and where | `baseline_out.csv` |
| Output columns | `campaign, date, metric, expected, mad` |
| Libraries needed | `pandas, numpy, scikit-learn` |
| Hardcoded values (T, window, paths) | `T = 4`, `WINDOW = 28` |

## Step 2: Check for name collisions (5 min)

Run this once from `project/`. It is only informational; it fixes nothing because nothing needs fixing in this approach.

```python
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
```

Files marked DIFFERENT CONTENT are exactly why merging is risky; the method below is safe regardless.

## Step 3: Define the hand-off contracts (10 min)

Each member's output is converted by an adapter into the shape the next member needs. Agree these columns (from the team split plan):

| Hand-off | Required columns |
|---|---|
| Raw data -> M1 | `date, campaign, spend, clicks, conversions` (optional `bid_strategy`) |
| M1 -> M2 (residuals) | `campaign, date, metric, actual, expected, mad, noise_floor, robust_z` |
| M2 -> M3 (flags) | `campaign, date, type, metric, actual, expected, delta_pct, hard_rule, seasonal` |
| M3 -> M4 (alerts) | `campaign, date, type, severity, route, metric, actual, expected, delta_pct, explanation, first_step` |

```python
# integration/contracts.py
CONTRACTS = {
    "residuals": ["campaign","date","metric","actual","expected","mad","noise_floor","robust_z"],
    "flags": ["campaign","date","type","metric","actual","expected","delta_pct","hard_rule","seasonal"],
    "alerts": ["campaign","date","type","severity","route","metric","actual","expected",
               "delta_pct","explanation","first_step"],
}

def validate(df, name):
    missing = [c for c in CONTRACTS[name] if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")
    return df
```

## Step 4: Write adapters (15 min, owner of the *receiving* member leads)

An adapter only renames, reorders, or derives columns on a **copy** of the data. It never modifies the member's own output file.

```python
# integration/adapters.py
import pandas as pd

# Fill in per member, e.g. M1 calls the expected value "baseline" and z-score "z".
RENAMES = {
    "M1_to_M2": {"baseline": "expected", "z": "robust_z"},
    "M2_to_M3": {"flag_type": "type"},
    "M3_to_M4": {"msg": "explanation", "next_step": "first_step"},
}

def adapt(df, key, defaults=None):
    out = df.rename(columns=RENAMES.get(key, {})).copy()
    for col, val in (defaults or {}).items():   # fill columns a member does not produce
        if col not in out.columns:
            out[col] = val
    return out
```

If a member lacks a required column (e.g. `noise_floor`), add it in the adapter via `defaults` or a derived formula, and write down what you assumed.

## Step 5: Build the orchestrator (20 min)

Key safety rule: **each member runs inside a temporary copy of its own folder**, so even if its code writes files with fixed names or relative paths, the original folder is never changed and duplicate file names never collide.

```python
# integration/run_pipeline.py
import shutil, subprocess, sys
from pathlib import Path
import pandas as pd
from adapters import adapt
from contracts import validate

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "integration" / "run"

# Fill from the Step 1 inventory. 'cmd' runs from inside the member's copied folder.
MEMBERS = {
    "M1": {"cmd": [sys.executable, "main.py"], "in": "data.csv",      "out": "baseline_out.csv"},
    "M2": {"cmd": [sys.executable, "detect.py"], "in": "residuals.csv", "out": "flags_out.csv"},
    "M3": {"cmd": [sys.executable, "route.py"],  "in": "flags.csv",     "out": "alerts_all.csv"},
    "M4": {"cmd": [sys.executable, "evaluate.py"], "in": "alerts.csv",  "out": None},
}

def run_member(name, input_df, extra_files=()):
    cfg = MEMBERS[name]
    work = RUN / f"{name}_work"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(ROOT / name, work)                 # original stays untouched
    input_df.to_csv(work / cfg["in"], index=False)     # place input where member expects it
    for f in extra_files:                              # e.g. incidents.csv for M4
        shutil.copy(f, work / Path(f).name)
    r = subprocess.run(cfg["cmd"], cwd=work, capture_output=True, text=True)
    (RUN / f"{name}_log.txt").write_text(r.stdout + "\n" + r.stderr)
    if r.returncode != 0:
        raise RuntimeError(f"{name} failed, see integration/run/{name}_log.txt")
    return work

if __name__ == "__main__":
    RUN.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(sys.argv[1])
    incidents = sys.argv[2]

    w1 = run_member("M1", raw)
    res = validate(adapt(pd.read_csv(w1 / MEMBERS["M1"]["out"]), "M1_to_M2"), "residuals")

    w2 = run_member("M2", res)
    flags = validate(adapt(pd.read_csv(w2 / MEMBERS["M2"]["out"]), "M2_to_M3"), "flags")

    w3 = run_member("M3", flags)
    alerts = validate(adapt(pd.read_csv(w3 / MEMBERS["M3"]["out"]), "M3_to_M4"), "alerts")

    w4 = run_member("M4", alerts, extra_files=[incidents])
    print("Pipeline complete. Member outputs are in integration/run/*_work/")
```

If a member's script takes the input path as an argument instead of reading a fixed file name, append it to `cmd` (for example `["python","main.py","data.csv"]`). Adjust the `MEMBERS` table only; never edit member code.

### Handling the M1 <-> M2 freeze loop

The incident freeze needs M2's flags to feed back into M1's baseline. Safest, simplest option with no code changes:

1. **Pass 1:** M1 runs without freeze -> M2 produces flags.
2. **Pass 2:** save the flagged `campaign, date` pairs as `freeze_days.csv`, copy it into M1's work copy, and re-run M1 (only if M1 reads such a file). Then re-run M2.

If M1's code has no way to accept freeze days, skip the loop for now, run single-pass, and record it as a limitation in the write-up. Do not rewrite M1 under time pressure.

## Step 6: Prove nothing was lost (15 min)

**A. Original folders unchanged.** Compare against the Step 0 backup (`diff -r M1 backup_M1/` or `git status`). It must report no differences.

**B. Each member still works standalone.** Before integration, each member runs their own code once on the same input and keeps the output as `golden_Mx.csv`. After integration compare:

```python
# integration/regression_check.py
import pandas as pd
from pathlib import Path
RUN = Path(__file__).resolve().parent / "run"

for m, out in [("M1","baseline_out.csv"),("M2","flags_out.csv"),("M3","alerts_all.csv")]:
    golden = pd.read_csv(Path(f"golden_{m}.csv"))
    new = pd.read_csv(RUN / f"{m}_work" / out)
    try:
        pd.testing.assert_frame_equal(golden, new, check_like=True)
        print(m, "OK: identical to standalone output")
    except AssertionError as e:
        print(m, "DIFFERS (expected if its input now comes from the previous member):", str(e)[:200])
```

M1 should match exactly (same raw input). M2 to M4 will legitimately differ if their standalone test input differed from the real upstream output, so treat a difference as "check it", not as a failure.

**C. Feature checklist.** Each member lists their features (for example M3: tracking template, budget template, bid template, seasonal digest) and ticks each in the integrated output. Use the checklist in section 5 of the final plan for the overall submission.

## Step 7: Dependencies and environment (5 min)

- Merge all four `requirements` lists into one install command (pandas, numpy, scikit-learn if any member uses it).
- If two members need conflicting versions, give that member its own virtual environment and put its interpreter path in `MEMBERS[...]["cmd"]` in place of `sys.executable`.
- Use the same Python version for all.

## Step 8: Rules to keep everything safe

| Rule | Why |
|---|---|
| Never edit files inside `M1` to `M4` during integration | Guarantees no feature loss |
| Run each member in a temp copy | No file-name collisions, no overwritten outputs |
| Adapters work on copies, never on member outputs | Native outputs stay available for audit |
| Validate every hand-off with `contracts.py` | Fails early with a clear message instead of silently wrong data |
| Keep `integration/run/` disposable | Re-running always starts clean |
| If a member must change something, make it additive (new optional argument whose default equals the old behavior) and have the owner do it | Existing behavior cannot change |
| Keep the four members' logs in `integration/run/*_log.txt` | Fast debugging |

## Suggested order and time (about 70 min)

| Time | Who | Task |
|---|---|---|
| 0:00 | All | Step 0 backups, freeze member code |
| 0:05 | Each member | Step 1 inventory into `members.py` |
| 0:15 | One person | Step 2 collision check |
| 0:20 | All | Step 3 contracts |
| 0:30 | Receiving member of each hand-off | Step 4 adapters |
| 0:45 | M4 | Step 5 orchestrator, first end-to-end run |
| 1:05 | All | Step 6 regression and feature checks |
| 1:10 | M4 | Final run, submission write-up |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `missing columns [...]` | Add the rename or default in `adapters.py` |
| Member script cannot find its input | Check the `"in"` file name in `MEMBERS` against what the member's code expects |
| Member fails on import | Install missing library, or use its own venv (Step 7) |
| Output file not found | Confirm the `"out"` name in `MEMBERS`; check `integration/run/Mx_log.txt` |
| Numbers differ from standalone run | Expected if input differs; verify M1 matches exactly and compare M2 to M4 using the same upstream data |
