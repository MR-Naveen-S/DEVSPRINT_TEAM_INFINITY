"""
Unit tests for core statistical anomaly detection, input validation, and immutability.
"""

import pytest
import pandas as pd
import numpy as np

from M2.detect import detect_anomalies, get_freeze_feedback
from M2.config import M2Config


def create_sample_residuals(
    campaign="CMP-01",
    date="2026-03-01",
    metric="conversions",
    actual=10.0,
    expected=10.0,
    robust_z=0.0,
    frozen_flag=False,
    mad=1.5,
    noise_floor=0.5
):
    return pd.DataFrame([{
        "campaign": campaign,
        "date": date,
        "metric": metric,
        "actual": actual,
        "expected": expected,
        "mad": mad,
        "noise_floor": noise_floor,
        "robust_z": robust_z,
        "frozen_flag": frozen_flag
    }])


def test_high_positive_robust_z():
    """Test 1: Clear high positive robust-Z anomaly."""
    # Build 3 days so persistence confirms
    rows = []
    for d, z in [("2026-03-01", 0.0), ("2026-03-02", 4.5), ("2026-03-03", 5.0)]:
        rows.append({
            "campaign": "CMP-01",
            "date": d,
            "metric": "spend",
            "actual": 500.0 if z > 0 else 100.0,
            "expected": 100.0,
            "mad": 10.0,
            "noise_floor": 1.0,
            "robust_z": z,
            "frozen_flag": False
        })
    df = pd.DataFrame(rows)
    res = detect_anomalies(df)
    assert not res.empty
    assert (res["type"] == "other_anomaly").any()
    assert (res["delta_pct"] > 0).any()


def test_high_negative_robust_z():
    """Test 2: Clear high negative robust-Z anomaly."""
    rows = []
    for d, z in [("2026-03-01", 0.0), ("2026-03-02", -4.5), ("2026-03-03", -5.0)]:
        rows.append({
            "campaign": "CMP-01",
            "date": d,
            "metric": "clicks",
            "actual": 10.0 if z < 0 else 100.0,
            "expected": 100.0,
            "mad": 10.0,
            "noise_floor": 1.0,
            "robust_z": z,
            "frozen_flag": False
        })
    df = pd.DataFrame(rows)
    res = detect_anomalies(df)
    assert not res.empty
    assert (res["type"] == "other_anomaly").any()
    assert (res["delta_pct"] < 0).any()


def test_values_within_threshold():
    """Test 3: Values within threshold do not trigger alerts."""
    df = create_sample_residuals(robust_z=2.1)  # Threshold default is 3.5
    res = detect_anomalies(df)
    assert res.empty


def test_frozen_observation():
    """Test 4: Frozen observation must not trigger statistical alert."""
    df = create_sample_residuals(robust_z=6.0, frozen_flag=True)
    res = detect_anomalies(df)
    assert res.empty


def test_empty_input():
    """Test 14: Empty input returns empty DataFrame with expected contract columns."""
    df = pd.DataFrame(columns=[
        "campaign", "date", "metric", "actual", "expected", "mad", "noise_floor", "robust_z", "frozen_flag"
    ])
    res = detect_anomalies(df)
    assert isinstance(res, pd.DataFrame)
    assert res.empty
    expected_cols = ["campaign", "date", "type", "metric", "actual", "expected", "delta_pct", "hard_rule", "seasonal"]
    assert list(res.columns) == expected_cols


def test_missing_required_columns():
    """Test 15: Missing required columns raises ValueError."""
    df = pd.DataFrame([{"campaign": "CMP-01", "date": "2026-03-01"}])
    with pytest.raises(ValueError, match="Missing required columns"):
        detect_anomalies(df)


def test_null_values_and_zero_baselines():
    """Test 16: Null values raise error; zero baselines handled safely without zero division."""
    # Test zero baseline safe division with a metric not blocked by volume count guards (e.g. cpa)
    df_pers = pd.concat([
        create_sample_residuals(date="2026-03-01", metric="cpa", actual=0.0, expected=0.0, robust_z=0.0),
        create_sample_residuals(date="2026-03-02", metric="cpa", actual=5.0, expected=0.0, robust_z=4.0),
        create_sample_residuals(date="2026-03-03", metric="cpa", actual=5.0, expected=0.0, robust_z=4.0)
    ], ignore_index=True)
    res = detect_anomalies(df_pers)
    assert not res.empty
    assert (res["delta_pct"] == 0.0).any()

    # Null values in campaign
    null_df = create_sample_residuals()
    null_df.loc[0, "campaign"] = None
    with pytest.raises(ValueError):
        detect_anomalies(null_df)


def test_multiple_anomalous_metrics_single_event():
    """Test 17: Multiple anomalous metrics on same campaign-day produce one primary event."""
    # Campaign CMP-01 on 2026-03-03 has anomalies on both clicks and spend
    df = pd.DataFrame([
        # Day 1
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "clicks", "actual": 100, "expected": 100, "mad": 10, "noise_floor": 1, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 100, "expected": 100, "mad": 10, "noise_floor": 1, "robust_z": 0.0, "frozen_flag": False},
        # Day 2
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "clicks", "actual": 300, "expected": 100, "mad": 10, "noise_floor": 1, "robust_z": 4.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "spend", "actual": 500, "expected": 100, "mad": 10, "noise_floor": 1, "robust_z": 6.0, "frozen_flag": False},
        # Day 3
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "clicks", "actual": 320, "expected": 100, "mad": 10, "noise_floor": 1, "robust_z": 4.5, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "spend", "actual": 550, "expected": 100, "mad": 10, "noise_floor": 1, "robust_z": 6.5, "frozen_flag": False},
    ])
    res = detect_anomalies(df)
    # Should produce 1 row per campaign-day for Day 2 and Day 3
    day3_events = res[res["date"] == "2026-03-03"]
    assert len(day3_events) == 1
    # Primary metric selected should be spend (highest z-score = 6.5)
    assert day3_events.iloc[0]["metric"] == "spend"


def test_input_dataframe_unmodified():
    """Test 18: Ensuring input DataFrames remain unchanged."""
    df = create_sample_residuals(robust_z=5.0)
    df_copy = df.copy()
    
    metrics = pd.DataFrame([{"campaign": "CMP-01", "date": "2026-03-01", "bid_strategy": "Manual"}])
    metrics_copy = metrics.copy()

    detect_anomalies(df, metrics=metrics)

    pd.testing.assert_frame_equal(df, df_copy)
    pd.testing.assert_frame_equal(metrics, metrics_copy)


def test_freeze_feedback_interface():
    """Test freeze feedback interface."""
    flag_df = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-02", "type": "other_anomaly", "metric": "spend", "actual": 500, "expected": 100, "delta_pct": 400.0, "hard_rule": False, "seasonal": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "type": "other_anomaly", "metric": "clicks", "actual": 300, "expected": 100, "delta_pct": 200.0, "hard_rule": False, "seasonal": False},
    ])
    feedback = get_freeze_feedback(flag_df)
    assert isinstance(feedback, pd.DataFrame)
    assert list(feedback.columns) == ["campaign", "date"]
    assert len(feedback) == 1
    assert feedback.iloc[0]["campaign"] == "CMP-01"
    assert feedback.iloc[0]["date"] == "2026-03-02"
