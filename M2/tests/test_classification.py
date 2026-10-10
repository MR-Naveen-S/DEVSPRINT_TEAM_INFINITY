"""
Unit tests for hard-rule detection and incident classification:
tracking_break, budget_exhausted, and bid_strategy_change.
"""

import pytest
import pandas as pd

from M2.detect import detect_anomalies


def test_tracking_break_two_consecutive_days():
    """Test 7: Tracking break with zero conversions for 2+ consecutive days while clicks/spend remain stable."""
    df = pd.DataFrame([
        # Day 1
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "conversions", "actual": 10.0, "expected": 10.0, "mad": 1.0, "noise_floor": 0.5, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "clicks", "actual": 200.0, "expected": 200.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 300.0, "expected": 300.0, "mad": 15.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        # Day 2
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "conversions", "actual": 0.0, "expected": 10.0, "mad": 1.0, "noise_floor": 0.5, "robust_z": -6.7, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "clicks", "actual": 205.0, "expected": 200.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.3, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "spend", "actual": 298.0, "expected": 300.0, "mad": 15.0, "noise_floor": 1.0, "robust_z": -0.1, "frozen_flag": False},
        # Day 3
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "conversions", "actual": 0.0, "expected": 10.0, "mad": 1.0, "noise_floor": 0.5, "robust_z": -6.7, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "clicks", "actual": 198.0, "expected": 200.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": -0.1, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "spend", "actual": 302.0, "expected": 300.0, "mad": 15.0, "noise_floor": 1.0, "robust_z": 0.1, "frozen_flag": False},
    ])
    
    res = detect_anomalies(df)
    assert not res.empty
    day3_events = res[res["date"] == "2026-03-03"]
    assert len(day3_events) == 1
    event = day3_events.iloc[0]
    assert event["type"] == "tracking_break"
    assert event["metric"] == "conversions"
    assert bool(event["hard_rule"]) is True


def test_single_zero_conversion_day_not_tracking_break():
    """Test 8: A single zero-conversion day should not be treated as a confirmed tracking break."""
    df = pd.DataFrame([
        # Day 1: normal
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "conversions", "actual": 10.0, "expected": 10.0, "mad": 1.0, "noise_floor": 0.5, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "clicks", "actual": 200.0, "expected": 200.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        # Day 2: single 0 conversion day
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "conversions", "actual": 0.0, "expected": 10.0, "mad": 1.0, "noise_floor": 0.5, "robust_z": -6.7, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "clicks", "actual": 200.0, "expected": 200.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        # Day 3: normal
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "conversions", "actual": 10.0, "expected": 10.0, "mad": 1.0, "noise_floor": 0.5, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "clicks", "actual": 200.0, "expected": 200.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
    ])
    
    res = detect_anomalies(df)
    # Day 2 should NOT be classified as tracking_break (requires 2 consecutive days)
    if not res.empty:
        day2_events = res[res["date"] == "2026-03-02"]
        if not day2_events.empty:
            assert day2_events.iloc[0]["type"] != "tracking_break"


def test_budget_exhaustion_with_cap():
    """Test 9: Budget exhaustion with a known budget cap."""
    df = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 1000.0, "expected": 500.0, "mad": 50.0, "noise_floor": 5.0, "robust_z": 6.7, "frozen_flag": False},
    ])
    metrics = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "spend": 1000.0, "budget_cap": 1000.0}
    ])
    
    res = detect_anomalies(df, metrics=metrics)
    assert not res.empty
    event = res.iloc[0]
    assert event["type"] == "budget_exhausted"
    assert bool(event["hard_rule"]) is True


def test_bid_strategy_change_with_metadata():
    """Test 10: Bid-strategy change with available strategy metadata."""
    df = pd.DataFrame([
        # Day 1
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 100.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        # Day 2: bid strategy changed and metric anomaly occurs
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "spend", "actual": 400.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 4.5, "frozen_flag": False},
    ])
    metrics = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "bid_strategy": "Manual CPC"},
        {"campaign": "CMP-01", "date": "2026-03-02", "bid_strategy": "Target CPA"},
    ])
    
    res = detect_anomalies(df, metrics=metrics)
    assert not res.empty
    event = res[res["date"] == "2026-03-02"].iloc[0]
    assert event["type"] == "bid_strategy_change"
    assert bool(event["hard_rule"]) is True


def test_missing_bid_strategy_metadata():
    """Test 11: Missing bid-strategy metadata gracefully falls back without error."""
    df = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 100.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 0.0, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-02", "metric": "spend", "actual": 400.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 4.5, "frozen_flag": False},
        {"campaign": "CMP-01", "date": "2026-03-03", "metric": "spend", "actual": 420.0, "expected": 100.0, "mad": 10.0, "noise_floor": 1.0, "robust_z": 4.8, "frozen_flag": False},
    ])
    
    # No metrics table passed
    res = detect_anomalies(df, metrics=None)
    assert not res.empty
    # Day 3 confirmed via persistence, classified as other_anomaly, not bid_strategy_change
    day3_event = res[res["date"] == "2026-03-03"].iloc[0]
    assert day3_event["type"] == "other_anomaly"
    assert bool(day3_event["hard_rule"]) is False


def test_budget_exhaustion_independent_of_bid_strategy_setting():
    """Verify budget exhaustion detection runs when enable_bid_strategy_detection is False."""
    df = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "metric": "spend", "actual": 1000.0, "expected": 500.0, "mad": 50.0, "noise_floor": 5.0, "robust_z": 6.7, "frozen_flag": False},
    ])
    metrics = pd.DataFrame([
        {"campaign": "CMP-01", "date": "2026-03-01", "spend": 1000.0, "budget_cap": 1000.0}
    ])
    
    config = {"enable_bid_strategy_detection": False}
    res = detect_anomalies(df, metrics=metrics, config=config)
    assert not res.empty
    event = res.iloc[0]
    assert event["type"] == "budget_exhausted"
    assert bool(event["hard_rule"]) is True

