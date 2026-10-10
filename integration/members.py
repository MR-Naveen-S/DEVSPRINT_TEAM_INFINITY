# integration/members.py
# Member metadata for pipeline

MEMBERS = {
    "M1": {
        "entry": "python baseline.py --input data.csv",
        "in": "data.csv",
        "out": "M1/outputs/residual_table.csv",
        "output_cols": ["campaign", "date", "metric", "actual", "expected", "mad", "noise_floor", "robust_z", "frozen_flag"]
    },
    "M2": {
        "entry": "from detect import detect_anomalies",
        "in": "residuals.csv",
        "out": "flags_out.csv",
        "output_cols": ["campaign", "date", "type", "metric", "actual", "expected", "delta_pct", "hard_rule", "seasonal"]
    },
    "M3": {
        "entry": "from route_explain import run_routing",
        "in": "flags.csv",
        "out": "alerts_all.csv",
        "output_cols": ["campaign", "date", "type", "severity", "route", "metric", "actual", "expected", "delta_pct", "explanation", "first_step"]
    },
    "M4": {
        "entry": "from evaluate import evaluate_pipeline",
        "in": "alerts.csv",
        "out": "None",
        "output_cols": []
    }
}
