"""
Unit Tests for M1 Data & Baseline Engineering
==============================================
Validates all Phase 1-4 requirements and fixes:
1. Today's observation is never included in today's baseline (1-day shift).
2. Frozen observations are excluded from baseline training.
3. Small-campaign uncertainty floors widen the band appropriately.
4. Column aliases are mapped correctly.
5. Invalid dates and missing columns produce clear, actionable errors.
6. Duplicate campaign-day records are detected.
7. Negative values are rejected.
8. Division-by-zero handling works safely (assigns NaN, not 0).
9. Future observations do not influence historical baselines (causal lookback).
10. The 21-, 28-, and 35-day baseline windows work accurately.
11. Baseline window validation strictly rejects windows not in ALLOWED_WINDOW_DAYS (0, -1, 22).
12. Incident flag normalization supports DataFrames (day & range), tuples, and dicts.
13. Incident flag validation rejects malformed dates and reversed ranges.
14. Missing incident flags file raises FileNotFoundError in run_m1_pipeline.
15. Sensitivity sweep propagates incident flags, freeze_days, and t_multiplier across all windows.
16. Warm-up baselines produce NaN (not artificial zero residuals) when history is insufficient.
"""

import os
import pytest
import numpy as np
import pandas as pd

from M1.baseline import (
    load_real,
    validate_input_dataframe,
    derive_metrics,
    compute_baseline_residuals,
    calculate_mad,
    get_noise_floor,
    generate_synthetic_stub_data,
    generate_weekly_small_campaign_aggregates,
    run_window_sensitivity_sweep,
    run_m1_pipeline,
    normalize_incident_flags,
    resolve_aliases,
)
from M1.config import (
    MAD_SCALE_FACTOR,
    ALLOWED_WINDOW_DAYS,
    DEFAULT_WINDOW_DAYS,
    DEFAULT_FREEZE_DAYS,
    DEFAULT_T_MULTIPLIER,
)


@pytest.fixture
def synthetic_sample_df() -> pd.DataFrame:
    """Creates a deterministic 35-day single-campaign dataset for baseline testing."""
    dates = pd.date_range("2026-01-01", periods=35, freq="D")
    records = []
    for i, d in enumerate(dates):
        # Base conversion pattern: 10 conv normally, but spike to 100 on day index 20
        conv_val = 100 if i == 20 else 10
        records.append({
            "day": d.strftime("%Y-%m-%d"),
            "campaign_id": "C_TEST",
            "campaign_name": "Test Campaign",
            "cost": 100.0,
            "impressions": 1000,
            "clicks": 100,
            "conv": conv_val,
            "revenue": 500.0,
        })
    df = pd.DataFrame(records)
    return derive_metrics(df)


# -----------------------------------------------------------------------------
# Test 1: Today's observation is never in its own baseline
# -----------------------------------------------------------------------------
def test_today_never_in_own_baseline(synthetic_sample_df):
    """
    On day 20 (where conv spikes from 10 to 100), the baseline for day 20
    must remain 10, because day 20 itself cannot contaminate its own baseline.
    """
    res_df, _ = compute_baseline_residuals(synthetic_sample_df, window_days=28)
    day_20_res = res_df[(res_df["date"] == "2026-01-21") & (res_df["metric"] == "conv")]
    assert not day_20_res.empty
    expected_conv = day_20_res["expected"].iloc[0]
    actual_conv = day_20_res["actual"].iloc[0]
    # Actual is 100, expected should be ~10 (unaffected by 100)
    assert actual_conv == 100
    assert expected_conv == pytest.approx(10.0, abs=1.0)


# -----------------------------------------------------------------------------
# Test 2: Frozen observations are excluded from baseline training
# -----------------------------------------------------------------------------
def test_frozen_observations_excluded():
    """
    If day 15 is flagged and frozen, day 20's baseline should still be 10,
    ignoring the 100 spike from day 15.
    """
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    records = []
    for i, d in enumerate(dates):
        conv_val = 100 if i == 15 else 10
        records.append({
            "day": d.strftime("%Y-%m-%d"),
            "campaign_id": "C_FREEZE",
            "campaign_name": "Freeze Campaign",
            "cost": 50.0,
            "impressions": 500,
            "clicks": 50,
            "conv": conv_val,
            "revenue": 200.0,
        })
    df = derive_metrics(pd.DataFrame(records))

    # Flag day 15
    flag_date = dates[15].strftime("%Y-%m-%d")
    flags = [("C_FREEZE", flag_date)]

    # Compute with and without flags
    res_frozen, _ = compute_baseline_residuals(df, window_days=28, freeze_days=14, incident_flags=flags)
    
    # Check baseline on day 20 (which looks back including day 15)
    day_20_date = dates[20].strftime("%Y-%m-%d")
    res_day_20 = res_frozen[(res_frozen["date"] == day_20_date) & (res_frozen["metric"] == "conv")]
    assert res_day_20["expected"].iloc[0] == pytest.approx(10.0, abs=0.5)


# -----------------------------------------------------------------------------
# Test 3: Small-campaign uncertainty floors widen the band appropriately
# -----------------------------------------------------------------------------
def test_small_campaign_floor_widens_band():
    """
    For a small campaign with 0 MAD (e.g. constant 1 conversion per day),
    the effective band must NOT collapse to 0. It must be at least the Poisson floor (>= 1.0).
    """
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    records = [{
        "day": d.strftime("%Y-%m-%d"),
        "campaign_id": "C_SMALL",
        "campaign_name": "Small Niche",
        "cost": 10.0,
        "impressions": 100,
        "clicks": 10,
        "conv": 1,
        "revenue": 20.0,
    } for d in dates]
    df = derive_metrics(pd.DataFrame(records))

    res_df, bands_df = compute_baseline_residuals(df, window_days=28, t_multiplier=3.0)
    conv_bands = bands_df[bands_df["metric"] == "conv"].dropna(subset=["expected"])
    
    # Check MAD is 0 (constant stream of 1s), but effective_band is >= Poisson floor (1.0)
    assert (conv_bands["robust_sigma"] == 0.0).any()
    assert (conv_bands["effective_band"] >= 1.0).all()
    # Check lower band never drops below 0
    assert (conv_bands["lower_band"] >= 0.0).all()


# -----------------------------------------------------------------------------
# Test 4: Column aliases are mapped correctly
# -----------------------------------------------------------------------------
def test_column_alias_mapping():
    """Verifies that diverse column names (spend, conversions, date, cid) map to canonical schema."""
    raw_df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "CID": ["C01", "C01"],
        "CampaignName": ["Brand Search", "Brand Search"],
        "Spend": [100.5, 120.0],
        "Imprs": [5000, 6000],
        "Clicks": [200, 250],
        "Conversions": [10, 12],
        "Sales": [500.0, 600.0],
    })
    loaded = load_real(raw_df)
    assert "day" in loaded.columns
    assert "campaign_id" in loaded.columns
    assert "campaign_name" in loaded.columns
    assert "cost" in loaded.columns
    assert "conv" in loaded.columns
    assert "impressions" in loaded.columns
    assert "clicks" in loaded.columns
    assert "revenue" in loaded.columns
    assert loaded["cost"].iloc[0] == 100.5
    assert loaded["conv"].iloc[0] == 10


# -----------------------------------------------------------------------------
# Test 5: Invalid dates and missing columns produce clear errors
# -----------------------------------------------------------------------------
def test_invalid_dates_and_missing_columns():
    # Missing required column 'clicks'
    bad_df1 = pd.DataFrame({
        "day": ["2026-01-01"],
        "campaign_id": ["C01"],
        "cost": [100.0],
        "conv": [5],
        "impressions": [1000],
    })
    with pytest.raises(ValueError, match="Missing required canonical columns"):
        load_real(bad_df1)

    # Invalid date string
    bad_df2 = pd.DataFrame({
        "day": ["not-a-date"],
        "campaign_id": ["C01"],
        "cost": [100.0],
        "conv": [5],
        "impressions": [1000],
        "clicks": [50],
    })
    with pytest.raises(ValueError, match="invalid or unparseable dates"):
        load_real(bad_df2)


# -----------------------------------------------------------------------------
# Test 6: Duplicate campaign-day records are detected
# -----------------------------------------------------------------------------
def test_duplicate_campaign_days():
    dup_df = pd.DataFrame({
        "day": ["2026-01-01", "2026-01-01"],
        "campaign_id": ["C01", "C01"],
        "cost": [100.0, 120.0],
        "conv": [5, 6],
        "impressions": [1000, 1200],
        "clicks": [50, 60],
    })
    with pytest.raises(ValueError, match="Duplicate campaign-day records detected"):
        load_real(dup_df)


# -----------------------------------------------------------------------------
# Test 7: Negative numerical values are rejected
# -----------------------------------------------------------------------------
def test_negative_values_rejected():
    neg_df = pd.DataFrame({
        "day": ["2026-01-01"],
        "campaign_id": ["C01"],
        "cost": [-50.0],
        "conv": [5],
        "impressions": [1000],
        "clicks": [50],
    })
    with pytest.raises(ValueError, match="Negative numerical values detected"):
        load_real(neg_df)


# -----------------------------------------------------------------------------
# Test 8: Division-by-zero handling in derived metrics
# -----------------------------------------------------------------------------
def test_divide_by_zero_handling():
    zero_df = pd.DataFrame({
        "day": ["2026-01-01"],
        "campaign_id": ["C01"],
        "campaign_name": ["C01"],
        "cost": [100.0],
        "conv": [0],  # 0 conversions -> CPA should be NaN, not 0 or error
        "impressions": [0],  # 0 impressions -> CTR, CPM should be NaN
        "clicks": [0],  # 0 clicks -> CVR should be NaN
        "revenue": [0.0],
    })
    derived = derive_metrics(zero_df)
    assert np.isnan(derived["cpa"].iloc[0])
    assert np.isnan(derived["ctr"].iloc[0])
    assert np.isnan(derived["cvr"].iloc[0])
    assert np.isnan(derived["cpm"].iloc[0])


# -----------------------------------------------------------------------------
# Test 9: Future observations do not influence historical baselines
# -----------------------------------------------------------------------------
def test_future_observations_do_not_leak():
    """
    Baseline on day 15 must be IDENTICAL whether days 20-30 exist or are modified.
    """
    dates_full = pd.date_range("2026-01-01", periods=30, freq="D")
    records_1 = []
    records_2 = []
    for i, d in enumerate(dates_full):
        d_str = d.strftime("%Y-%m-%d")
        records_1.append({
            "day": d_str, "campaign_id": "C_CAUSAL", "cost": 100.0,
            "impressions": 1000, "clicks": 100, "conv": 10, "revenue": 500.0,
        })
        # records_2 has massive anomalies in the future (days 20-29)
        conv_val = 500 if i >= 20 else 10
        records_2.append({
            "day": d_str, "campaign_id": "C_CAUSAL", "cost": 100.0,
            "impressions": 1000, "clicks": 100, "conv": conv_val, "revenue": 500.0,
        })

    df1 = derive_metrics(pd.DataFrame(records_1))
    df2 = derive_metrics(pd.DataFrame(records_2))

    res1, _ = compute_baseline_residuals(df1, window_days=28)
    res2, _ = compute_baseline_residuals(df2, window_days=28)

    # Compare baseline on day 15 (before the future alteration)
    day_15_res1 = res1[res1["date"] == "2026-01-15"].sort_values("metric")
    day_15_res2 = res2[res2["date"] == "2026-01-15"].sort_values("metric")

    np.testing.assert_array_almost_equal(
        day_15_res1["expected"].values,
        day_15_res2["expected"].values,
        decimal=4,
    )


# -----------------------------------------------------------------------------
# Test 10: The 21, 28, and 35-day baseline windows work
# -----------------------------------------------------------------------------
def test_baseline_window_sensitivity_sweep(tmp_path):
    stub_path, _ = generate_synthetic_stub_data(str(tmp_path))
    loaded = load_real(stub_path)
    
    for w in [21, 28, 35]:
        res_df, bands_df = compute_baseline_residuals(loaded, window_days=w)
        assert not res_df.empty
        assert (res_df["window_days"] == w).all()
        assert not bands_df.empty

    sweep_df = run_window_sensitivity_sweep(loaded, windows=[21, 28, 35], out_dir=str(tmp_path))
    assert set(sweep_df["window_days"].unique()) == {21, 28, 35}


# -----------------------------------------------------------------------------
# Test 11: Weekly small campaign aggregation
# -----------------------------------------------------------------------------
def test_weekly_small_campaign_aggregates(tmp_path):
    stub_path, _ = generate_synthetic_stub_data(str(tmp_path))
    loaded = load_real(stub_path)
    weekly_agg, md_report = generate_weekly_small_campaign_aggregates(
        loaded, spend_threshold=500.0, out_dir=str(tmp_path)
    )
    assert not weekly_agg.empty
    assert "year_week" in weekly_agg.columns
    assert "observed_days" in weekly_agg.columns
    assert "cpa" in weekly_agg.columns
    assert os.path.exists(os.path.join(str(tmp_path), "weekly_aggregate_small_campaigns.csv"))
    assert os.path.exists(os.path.join(str(tmp_path), "weekly_aggregate_small_campaigns.md"))


# -----------------------------------------------------------------------------
# Test 12: Baseline window validation strictly rejects unconfigured windows
# -----------------------------------------------------------------------------
def test_baseline_window_validation(synthetic_sample_df):
    """
    Validates that compute_baseline_residuals strictly rejects window_days values
    not present in ALLOWED_WINDOW_DAYS (e.g. 0, -1, 22).
    """
    for invalid_w in [0, -1, 22, 14, 30]:
        with pytest.raises(ValueError, match="Invalid window_days"):
            compute_baseline_residuals(synthetic_sample_df, window_days=invalid_w)

    for valid_w in ALLOWED_WINDOW_DAYS:
        res_df, _ = compute_baseline_residuals(synthetic_sample_df, window_days=valid_w)
        assert not res_df.empty


# -----------------------------------------------------------------------------
# Test 13: Incident flag normalization supports multiple input formats
# -----------------------------------------------------------------------------
def test_incident_flag_normalization_formats():
    """Verifies DataFrames (single day and date ranges), tuples, and dicts."""
    # 1. DataFrame with day
    df_single = pd.DataFrame({
        "campaign_id": ["C01", "C02"],
        "date": ["2026-02-10", "2026-02-11"],
    })
    flags_1 = normalize_incident_flags(df_single)
    assert ("C01", "2026-02-10") in flags_1
    assert ("C02", "2026-02-11") in flags_1

    # 2. DataFrame with start_date and end_date (inclusively expanded)
    df_range = pd.DataFrame({
        "campaign_id": ["C01"],
        "start_date": ["2026-02-10"],
        "end_date": ["2026-02-13"],
    })
    flags_2 = normalize_incident_flags(df_range)
    assert len(flags_2) == 4
    for d in ["2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13"]:
        assert ("C01", d) in flags_2

    # 3. List of tuples (2-tuple and 3-tuple)
    tuple_list = [("C03", "2026-03-01"), ("C04", "2026-03-10", "2026-03-12")]
    flags_3 = normalize_incident_flags(tuple_list)
    assert ("C03", "2026-03-01") in flags_3
    assert ("C04", "2026-03-10") in flags_3
    assert ("C04", "2026-03-11") in flags_3
    assert ("C04", "2026-03-12") in flags_3

    # 4. List of dicts
    dict_list = [
        {"campaign_id": "C05", "date": "2026-04-01"},
        {"campaign": "C06", "start_date": "2026-04-05", "end_date": "2026-04-06"},
    ]
    flags_4 = normalize_incident_flags(dict_list)
    assert ("C05", "2026-04-01") in flags_4
    assert ("C06", "2026-04-05") in flags_4
    assert ("C06", "2026-04-06") in flags_4


# -----------------------------------------------------------------------------
# Test 14: Incident flag validation rejects malformed & reversed dates
# -----------------------------------------------------------------------------
def test_incident_flag_malformed_and_reversed_dates():
    # Reversed date range in DataFrame
    bad_df_rev = pd.DataFrame({
        "campaign_id": ["C01"],
        "start_date": ["2026-03-15"],
        "end_date": ["2026-03-10"],  # start after end
    })
    with pytest.raises(ValueError, match="is after end_date"):
        normalize_incident_flags(bad_df_rev)

    # Malformed date in tuple
    bad_tuple = [("C01", "not-a-valid-date")]
    with pytest.raises(ValueError, match="Malformed date in incident flags"):
        normalize_incident_flags(bad_tuple)

    # Missing campaign in dict
    bad_dict = [{"date": "2026-01-01"}]
    with pytest.raises(ValueError, match="Missing campaign identifier"):
        normalize_incident_flags(bad_dict)


# -----------------------------------------------------------------------------
# Test 15: Missing incident flags file raises FileNotFoundError
# -----------------------------------------------------------------------------
def test_missing_flags_file_raises_filenotfound(tmp_path):
    stub_path, _ = generate_synthetic_stub_data(str(tmp_path))
    
    # Non-existent flags file must fail loudly
    with pytest.raises(FileNotFoundError, match="Incident flags file not found"):
        run_m1_pipeline(
            input_source=stub_path,
            incident_flags_path=os.path.join(str(tmp_path), "non_existent_flags.csv"),
            output_dir=str(tmp_path / "out"),
            reports_dir=str(tmp_path / "rep"),
        )

    # None path proceeds without error
    res = run_m1_pipeline(
        input_source=stub_path,
        incident_flags_path=None,
        output_dir=str(tmp_path / "out"),
        reports_dir=str(tmp_path / "rep"),
    )
    assert os.path.exists(res["residual_table"])


# -----------------------------------------------------------------------------
# Test 16: Sensitivity sweep propagates incident flags and parameters
# -----------------------------------------------------------------------------
def test_sensitivity_sweep_with_flags_and_params(tmp_path):
    stub_path, _ = generate_synthetic_stub_data(str(tmp_path))
    loaded = load_real(stub_path)

    flags = [("C01", "2026-01-10", "2026-01-15")]
    sweep_df = run_window_sensitivity_sweep(
        df=loaded,
        windows=[21, 28, 35],
        freeze_days=14,
        t_multiplier=3.5,
        incident_flags=flags,
        out_dir=str(tmp_path),
    )
    assert not sweep_df.empty
    assert set(sweep_df["window_days"].unique()) == {21, 28, 35}
    assert (sweep_df["total_evaluations"] > 0).all()


# -----------------------------------------------------------------------------
# Test 17: Warm-up baselines are NaN, never artificial zero residuals
# -----------------------------------------------------------------------------
def test_warmup_baselines_are_nan_not_zero_residual():
    """
    On early campaign days (day 1, day 2) where history < 3, expected baseline
    and residual must be NaN, preventing artificial zero-residual bias.
    """
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    records = [{
        "day": d.strftime("%Y-%m-%d"),
        "campaign_id": "C_WARM",
        "campaign_name": "Warmup Campaign",
        "cost": 100.0,
        "impressions": 1000,
        "clicks": 100,
        "conv": 10,
        "revenue": 500.0,
    } for d in dates]
    df = derive_metrics(pd.DataFrame(records))

    res_df, _ = compute_baseline_residuals(df, window_days=28)
    
    # Day 1 (index 0) and Day 2 (index 1) have history < 3 -> expected must be NaN
    day1_res = res_df[res_df["date"] == "2026-01-01"]
    assert day1_res["expected"].isna().all()
    assert day1_res["residual"].isna().all()
    assert day1_res["robust_z"].isna().all()

    # Day 5 (index 4) has 4 days of history (>= 3) -> expected must be valid numeric
    day5_res = res_df[res_df["date"] == "2026-01-05"]
    assert not day5_res["expected"].isna().any()
    assert not day5_res["residual"].isna().any()
