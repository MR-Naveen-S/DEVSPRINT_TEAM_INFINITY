"""
Unit tests for persistence filtering (2 of last 3 valid observations).
"""

import pytest
import pandas as pd

from M2.detect import detect_anomalies


def test_one_day_spike_rejected_by_persistence():
    """Test 5: A single-day spike is rejected by persistence."""
    # 3 consecutive days for spend: day 1 normal, day 2 spike (robust_z=5.0), day 3 normal
    df = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 100.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "spend", "actual": 500.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 5.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "spend", "actual": 100.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
    ])
    
    res = detect_anomalies(df)
    # Day 2 has robust_z=5.0 but only 1 of last 3 days was flagged -> persistence fails!
    assert res.empty


def test_anomaly_persisting_2_of_3_days():
    """Test 6: An anomaly persisting for two of three valid observations triggers alert."""
    df = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 100.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "spend", "actual": 450.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 4.5, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "spend", "actual": 480.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 4.8, "frozen_flag": False},
    ])
    
    res = detect_anomalies(df)
    # Day 3 has 2 flagged observations out of last 3 days (Day 2 and Day 3) -> confirmed!
    assert not res.empty
    day3_res = res[res["date"] == "2026-03-03"]
    assert len(day3_res) == 1
    assert day3_res.iloc[0]["type"] == "other_anomaly"
    assert bool(day3_res.iloc[0]["hard_rule"]) is False
