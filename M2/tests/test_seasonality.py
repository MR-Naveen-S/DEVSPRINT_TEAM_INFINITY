"""
Unit tests for peer-based seasonality and common-market-movement handling.
"""

import pytest
import pandas as pd

from M2.detect import detect_anomalies


def test_common_peer_movement_seasonal_shift():
    """Test 12: Common peer movement (>=40% peers moving >=8%) consistent with seasonal pattern."""
    # 5 campaigns on 2026-03-02 all spike by ~20% (peer share = 100%)
    rows = []
    # Day 1: normal for all 5 campaigns
    for i in range(1, 6):
        cmp = f"CMP-0{i}"
        rows.append({"campaign": cmp, "date": "2026-03-01", "metric": "clicks", "actual": 1000.0, "expected": 1000.0, "mad": 50.0, "noise_floor": 5.0, "robust_z": 0.0, "frozen_flag": False})
    
    # Day 2: all 5 campaigns spike by 20%
    for i in range(1, 6):
        cmp = f"CMP-0{i}"
        rows.append({"campaign": cmp, "date": "2026-03-02", "metric": "clicks", "actual": 1200.0, "expected": 1000.0, "mad": 50.0, "noise_floor": 5.0, "robust_z": 4.0, "frozen_flag": False})

    # Day 3: all 5 campaigns remain at 1200
    for i in range(1, 6):
        cmp = f"CMP-0{i}"
        rows.append({"campaign": cmp, "date": "2026-03-03", "metric": "clicks", "actual": 1200.0, "expected": 1000.0, "mad": 50.0, "noise_floor": 5.0, "robust_z": 4.0, "frozen_flag": False})

    df = pd.DataFrame(rows)
    res = detect_anomalies(df)
    assert not res.empty
    day3_events = res[res["date"] == "2026-03-03"]
    assert not day3_events.empty
    # Every campaign on Day 3 should be classified as seasonal_shift
    assert (day3_events["type"] == "seasonal_shift").all()
    assert (day3_events["seasonal"] == True).all()


def test_single_campaign_anomaly_not_seasonal():
    """Test 13: A single-campaign anomaly where peers do not move must not be classified as seasonal."""
    rows = []
    # 5 campaigns on 2026-03-01 to 2026-03-03
    for d in ["2026-03-01", "2026-03-02", "2026-03-03"]:
        for i in range(1, 6):
            cmp = f"CMP-0{i}"
            if cmp == "CMP-01" and d in ["2026-03-02", "2026-03-03"]:
                # CMP-01 alone spikes
                rows.append({"campaign": cmp, "date": d, "metric": "clicks", "actual": 1500.0, "expected": 1000.0, "mad": 50.0, "noise_floor": 5.0, "robust_z": 5.0, "frozen_flag": False})
            else:
                rows.append({"campaign": cmp, "date": d, "metric": "clicks", "actual": 1000.0, "expected": 1000.0, "mad": 50.0, "noise_floor": 5.0, "robust_z": 0.0, "frozen_flag": False})

    df = pd.DataFrame(rows)
    res = detect_anomalies(df)
    assert not res.empty
    cmp1_day3 = res[(res["campaign"] == "CMP-01") & (res["date"] == "2026-03-03")]
    assert len(cmp1_day3) == 1
    assert cmp1_day3.iloc[0]["type"] == "other_anomaly"
    assert cmp1_day3.iloc[0]["seasonal"] == False
