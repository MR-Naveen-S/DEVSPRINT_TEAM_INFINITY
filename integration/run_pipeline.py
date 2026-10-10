# integration/run_pipeline.py
import shutil, subprocess, sys
from pathlib import Path
import pandas as pd
from adapters import adapt
from contracts import validate

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "integration" / "run"

MEMBERS = {
    "M1": {
        "cmd": [sys.executable, "baseline.py", "--input", "data.csv"],
        "in": "data.csv",
        "out": "M1/outputs/residual_table.csv"
    },
    "M2": {
        "cmd": [sys.executable, "-c", "import sys, pandas as pd; sys.path.insert(0, '.'); import detect; df = pd.read_csv('residuals.csv'); flags = detect.detect_anomalies(df); flags.to_csv('flags_out.csv', index=False)"],
        "in": "residuals.csv",
        "out": "flags_out.csv"
    },
    "M3": {
        "cmd": [sys.executable, "-c", "import sys, pandas as pd; sys.path.insert(0, '.'); import route_explain; df = pd.read_csv('flags.csv'); route_explain.process_flags(df.to_dict(orient='records'), output_dir='.')"],
        "in": "flags.csv",
        "out": "alerts_all.csv"
    },
    "M4": {
        "cmd": [sys.executable, "-c", "import sys, pandas as pd; sys.path.insert(0, '.'); import evaluate; alerts = pd.read_csv('alerts.csv'); evaluate.evaluate_pipeline(alerts, sys.argv[1]); evaluate.generate_phase3_report(sys.argv[2], sys.argv[1], 'M4_PHASE3_SUBMISSION_REPORT.md')", "incidents.csv", "synthetic_campaign_stub.csv"],
        "in": "alerts.csv",
        "out": None
    },
}

def run_member(name, input_df, extra_files=()):
    cfg = MEMBERS[name]
    work = RUN / f"{name}_work"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(ROOT / name, work)
    if input_df is not None:
        input_df.to_csv(work / cfg["in"], index=False)
    for f in extra_files:
        shutil.copy(f, work / Path(f).name)
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run(cfg["cmd"], cwd=work, capture_output=True, text=True, env=env)
    (RUN / f"{name}_log.txt").write_text(r.stdout + "\n" + r.stderr)
    if r.returncode != 0:
        print(f"STDOUT:\n{r.stdout}")
        print(f"STDERR:\n{r.stderr}")
        raise RuntimeError(f"{name} failed, see integration/run/{name}_log.txt")
    return work

if __name__ == "__main__":
    RUN.mkdir(parents=True, exist_ok=True)
    
    raw_path = ROOT / "M1" / "data" / "synthetic_campaign_stub.csv"
    incidents_path = ROOT / "M4" / "incidents.csv"
        
    raw = pd.read_csv(raw_path)

    print("Running M1...")
    w1 = run_member("M1", raw)
    res = validate(adapt(pd.read_csv(w1 / MEMBERS["M1"]["out"]), "M1_to_M2"), "residuals")

    print("Running M2...")
    w2 = run_member("M2", res)
    flags = validate(adapt(pd.read_csv(w2 / MEMBERS["M2"]["out"]), "M2_to_M3"), "flags")

    print("Running M3...")
    w3 = run_member("M3", flags)
    alerts = validate(adapt(pd.read_csv(w3 / MEMBERS["M3"]["out"]), "M3_to_M4"), "alerts")

    print("Running M4...")
    w4 = run_member("M4", alerts, extra_files=[incidents_path, raw_path])
    print("Pipeline complete. Member outputs are in integration/run/*_work/")
