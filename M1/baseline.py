"""
M1: Data & Baseline Engineer — `baseline.py`
============================================
PS-04: Campaign Anomaly Alerting Without Alert Fatigue

Responsibilities:
1. Load & validate real campaign datasets with flexible column alias mapping.
2. Safe metric derivations (CPA, CTR, CVR, ROAS, CPM) handling division by zero.
3. Causal, leak-free rolling median baselines with day-of-week (DOW) adjustment.
4. Robust scale estimation via MAD (scaled by 1.4826).
5. Statistical uncertainty floors (Poisson for counts, Binomial for rates) and effective bands.
6. Incident freeze feedback hook (M2 flags excluded from baseline training for up to 14 days).
7. Phase 0 contract residual table generation (`residual_table.csv`).
8. Baseline band export for visualization and weekly aggregations for low-volume campaigns.
9. Sensitivity sweeps across baseline windows (21, 28, 35 days).
"""

from __future__ import annotations

import argparse
import os
import re
from typing import Dict, List, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd

try:
    from .config import (
        ALIAS_MAP,
        ALLOWED_WINDOW_DAYS,
        BASELINE_METRICS,
        CANONICAL_COLUMNS,
        DEFAULT_FREEZE_DAYS,
        DEFAULT_T_MULTIPLIER,
        DEFAULT_WINDOW_DAYS,
        FLOOR_DOCUMENTATION,
        MAD_SCALE_FACTOR,
        NON_NEGATIVE_METRICS,
        REQUIRED_CANONICAL_FIELDS,
        SMALL_CAMPAIGN_CONV_THRESHOLD,
        SMALL_CAMPAIGN_DAILY_SPEND_THRESHOLD,
    )
except ImportError:
    from config import (  # type: ignore
        ALIAS_MAP,
        ALLOWED_WINDOW_DAYS,
        BASELINE_METRICS,
        CANONICAL_COLUMNS,
        DEFAULT_FREEZE_DAYS,
        DEFAULT_T_MULTIPLIER,
        DEFAULT_WINDOW_DAYS,
        FLOOR_DOCUMENTATION,
        MAD_SCALE_FACTOR,
        NON_NEGATIVE_METRICS,
        REQUIRED_CANONICAL_FIELDS,
        SMALL_CAMPAIGN_CONV_THRESHOLD,
        SMALL_CAMPAIGN_DAILY_SPEND_THRESHOLD,
    )



# =============================================================================
# PHASE 1: DATA INGESTION, ALIAS MAPPING & VALIDATION
# =============================================================================

def normalize_column_name(col: str) -> str:
    """Strip whitespace, lowercase, and convert separators to underscore."""
    col = str(col).strip().lower()
    col = re.sub(r"[\s\-\.]+", "_", col)
    return col


def resolve_aliases(columns: List[str]) -> Dict[str, str]:
    """
    Map raw column names to canonical fields based on ALIAS_MAP.
    Returns a dictionary mapping original_column_name -> canonical_name.
    """
    mapping: Dict[str, str] = {}
    normalized_to_original: Dict[str, str] = {}

    for col in columns:
        norm = normalize_column_name(col)
        normalized_to_original[norm] = col
        if norm in ALIAS_MAP:
            mapping[col] = ALIAS_MAP[norm]

    # Special handling if 'campaign' is provided and neither campaign_id nor campaign_name exists
    canonical_mapped = set(mapping.values())
    if "campaign_id" not in canonical_mapped and "campaign" in normalized_to_original:
        orig = normalized_to_original["campaign"]
        mapping[orig] = "campaign_id"
    if "campaign_name" not in canonical_mapped and "campaign" in normalized_to_original:
        orig = normalized_to_original["campaign"]
        # If campaign was already mapped to campaign_id, we will duplicate it for campaign_name during load
        pass

    return mapping


def validate_input_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Validates the standardized dataframe:
    - Verifies required canonical columns exist.
    - Checks for null/empty campaign identifiers.
    - Checks for invalid or unparseable dates.
    - Detects duplicate campaign-day entries.
    - Rejects negative numerical values.
    - Rejects invalid numerical values (NaN or Inf in required metrics).
    - Identifies missing reporting days (gaps in daily calendar sequence).

    Returns:
        (validated_dataframe, list_of_gap_warning_messages)
    Raises:
        ValueError: If validation fails on any hard constraint.
    """
    # 1. Required Columns Check
    missing_cols = REQUIRED_CANONICAL_FIELDS - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Input validation failed: Missing required canonical columns: {sorted(missing_cols)}. "
            f"Present columns: {list(df.columns)}"
        )

    # 2. Null/Empty Campaign Identifiers
    null_cid_mask = df["campaign_id"].isna() | (df["campaign_id"].astype(str).str.strip() == "")
    if null_cid_mask.any():
        num_invalid = int(null_cid_mask.sum())
        raise ValueError(f"Input validation failed: {num_invalid} records contain missing or empty campaign_id.")

    # If campaign_name is missing, default to campaign_id
    if "campaign_name" not in df.columns or df["campaign_name"].isna().all():
        df["campaign_name"] = df["campaign_id"].astype(str)
    else:
        df["campaign_name"] = df["campaign_name"].fillna(df["campaign_id"].astype(str))

    # 3. Date Validation
    if df["day"].isna().any():
        num_null_dates = int(df["day"].isna().sum())
        raise ValueError(f"Input validation failed: {num_null_dates} records have null or missing date values.")

    try:
        parsed_dates = pd.to_datetime(df["day"], errors="coerce")
    except Exception as e:
        raise ValueError(f"Input validation failed: Unparseable date format encountered. Details: {e}")

    nat_mask = parsed_dates.isna()
    if nat_mask.any():
        invalid_sample = df.loc[nat_mask, "day"].head(5).tolist()
        raise ValueError(
            f"Input validation failed: Found {int(nat_mask.sum())} invalid or unparseable dates. "
            f"Sample invalid values: {invalid_sample}"
        )

    df["day"] = parsed_dates.dt.strftime("%Y-%m-%d")
    df["date_parsed"] = parsed_dates

    # 4. Duplicate Campaign-Day Records Check
    dup_mask = df.duplicated(subset=["campaign_id", "day"], keep=False)
    if dup_mask.any():
        num_dups = int(dup_mask.sum())
        sample_dups = df.loc[dup_mask, ["campaign_id", "day"]].head(6).to_dict(orient="records")
        raise ValueError(
            f"Input validation failed: Duplicate campaign-day records detected ({num_dups} duplicate rows). "
            f"Sample duplicates: {sample_dups}"
        )

    # 5. Invalid Numerical Values (NaN or Inf in required metrics)
    numeric_cols = [c for c in ["cost", "impressions", "clicks", "conv", "revenue"] if c in df.columns]
    for col in numeric_cols:
        # Check non-numeric dtype or unparseable
        if not pd.api.types.is_numeric_dtype(df[col]):
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                raise ValueError(f"Input validation failed: Column '{col}' contains non-numeric data.")

        nan_count = int(df[col].isna().sum())
        inf_count = int(np.isinf(df[col]).sum())
        if nan_count > 0 or inf_count > 0:
            raise ValueError(
                f"Input validation failed: Column '{col}' contains invalid numerical values "
                f"({nan_count} NaNs, {inf_count} Infs). Metrics must be clean real numbers."
            )

    # 6. Negative Numerical Values Check
    for col in numeric_cols:
        neg_mask = df[col] < 0
        if neg_mask.any():
            min_val = float(df[col].min())
            num_neg = int(neg_mask.sum())
            raise ValueError(
                f"Input validation failed: Negative numerical values detected in column '{col}' "
                f"({num_neg} rows, min value = {min_val}). Metric values cannot be negative."
            )

    # 7. Missing Reporting Days (Date Continuity Analysis)
    gap_warnings: List[str] = []
    for cid, group in df.groupby("campaign_id"):
        min_date = group["date_parsed"].min()
        max_date = group["date_parsed"].max()
        expected_days = (max_date - min_date).days + 1
        actual_days = len(group)
        if actual_days < expected_days:
            missing_count = expected_days - actual_days
            gap_warnings.append(
                f"Campaign '{cid}' has {missing_count} missing reporting days between {min_date.date()} and {max_date.date()}."
            )

    # Sort deterministically
    df = df.sort_values(by=["campaign_id", "date_parsed"]).reset_index(drop=True)
    return df, gap_warnings


def derive_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes derived metrics:
    - CPA = cost / conv (undefined / np.nan if conv == 0)
    - CTR = clicks / impressions (undefined / np.nan if impressions == 0)
    - CVR = conv / clicks (undefined / np.nan if clicks == 0)
    - CPM = (cost / impressions) * 1000 (undefined / np.nan if impressions == 0)
    - ROAS = revenue / cost (undefined / np.nan if cost == 0, if revenue present)
    """
    out = df.copy()

    # CPA
    out["cpa"] = np.where(out["conv"] > 0, out["cost"] / out["conv"], np.nan)

    # CTR
    out["ctr"] = np.where(out["impressions"] > 0, out["clicks"] / out["impressions"], np.nan)

    # CVR
    out["cvr"] = np.where(out["clicks"] > 0, out["conv"] / out["clicks"], np.nan)

    # CPM
    out["cpm"] = np.where(out["impressions"] > 0, (out["cost"] / out["impressions"]) * 1000.0, np.nan)

    # ROAS (if revenue is present)
    if "revenue" in out.columns:
        out["roas"] = np.where(out["cost"] > 0, out["revenue"] / out["cost"], np.nan)
    else:
        out["revenue"] = 0.0
        out["roas"] = np.nan

    # Ensure integer types for discrete count columns
    for col in ["impressions", "clicks", "conv"]:
        if col in out.columns:
            out[col] = out[col].astype(int)

    return out


def load_real(
    source: Union[str, pd.DataFrame],
    sheet_name: Union[str, int] = 0,
) -> pd.DataFrame:
    """
    Loads real campaign data from a CSV file, Excel spreadsheet, or DataFrame,
    normalizes column aliases to canonical names, validates data integrity,
    and derives performance metrics (CPA, CTR, CVR, ROAS).

    Args:
        source: Filepath string (CSV/XLSX) or pandas DataFrame.
        sheet_name: Excel sheet name or index if loading an Excel workbook.

    Returns:
        Cleaned, validated pandas DataFrame with canonical columns and derived metrics.
    """
    if isinstance(source, pd.DataFrame):
        df_raw = source.copy()
    elif isinstance(source, str):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Input file not found at path: {source}")
        if source.endswith(".csv"):
            df_raw = pd.read_csv(source)
        elif source.endswith(".xlsx") or source.endswith(".xls"):
            df_raw = pd.read_excel(source, sheet_name=sheet_name)
        else:
            # Attempt CSV reading as fallback
            df_raw = pd.read_csv(source)
    else:
        raise TypeError(f"Unsupported source type: {type(source)}. Expected str or pd.DataFrame.")

    # 1. Map Column Aliases
    col_map = resolve_aliases(list(df_raw.columns))
    df = df_raw.rename(columns=col_map).copy()

    # If 'campaign' provided name but not id (or vice versa)
    if "campaign_id" not in df.columns and "campaign_name" in df.columns:
        df["campaign_id"] = df["campaign_name"]
    elif "campaign_name" not in df.columns and "campaign_id" in df.columns:
        df["campaign_name"] = df["campaign_id"]

    # 2. Validate Input
    df, gap_warnings = validate_input_dataframe(df)

    # 3. Derive Performance Metrics
    df = derive_metrics(df)

    # Store gap warnings as metadata attribute on dataframe
    df.attrs["gap_warnings"] = gap_warnings
    return df


# =============================================================================
# PHASE 2: BASELINE TUNING, ROBUST MAD, UNCERTAINTY FLOORS & INCIDENT FREEZE
# =============================================================================

def calculate_mad(values: np.ndarray) -> Tuple[float, float]:
    """
    Calculates the Median and Median Absolute Deviation (MAD) of a 1D array.
    Robust Sigma = 1.4826 * MAD.
    """
    clean_vals = values[~np.isnan(values)]
    if len(clean_vals) == 0:
        return np.nan, 0.0

    med = float(np.median(clean_vals))
    abs_deviations = np.abs(clean_vals - med)
    mad = float(np.median(abs_deviations))
    robust_sigma = float(MAD_SCALE_FACTOR * mad)
    return med, robust_sigma


def get_noise_floor(
    metric: str,
    expected_val: float,
    expected_clicks: float = 100.0,
    expected_imp: float = 5000.0,
) -> float:
    """
    Returns the statistical uncertainty noise floor for a given metric.

    Statistical Foundations:
    - Counts (conv, clicks, impressions): Poisson process where variance = lambda -> std_err = sqrt(lambda).
    - Rates (cvr, ctr): Binomial proportion standard error sqrt(p*(1-p)/N).
    - Cost / Revenue: Fractional baseline variance floor preventing alerts on small monetary jitter.
    - CPA: Ratio spread floor avoiding instability when conversions are low.
    """
    if np.isnan(expected_val) or expected_val < 0:
        expected_val = 0.0

    if metric == "conv":
        # Poisson standard error: sqrt(lambda)
        return max(float(np.sqrt(max(expected_val, 1.0))), 1.0)

    elif metric == "clicks":
        # Poisson standard error: sqrt(lambda)
        return max(float(np.sqrt(max(expected_val, 1.0))), 2.0)

    elif metric == "impressions":
        # Poisson standard error: sqrt(lambda)
        return max(float(np.sqrt(max(expected_val, 100.0))), 10.0)

    elif metric == "cvr":
        # Binomial proportion standard error
        p = np.clip(expected_val, 0.001, 0.999)
        n = max(expected_clicks, 5.0)
        binom_se = float(np.sqrt((p * (1.0 - p)) / n))
        return max(binom_se, 0.005)  # Minimum 0.5% CVR uncertainty floor

    elif metric == "ctr":
        # Binomial proportion standard error
        p = np.clip(expected_val, 0.0001, 0.999)
        n = max(expected_imp, 50.0)
        binom_se = float(np.sqrt((p * (1.0 - p)) / n))
        return max(binom_se, 0.002)  # Minimum 0.2% CTR uncertainty floor

    elif metric == "cost":
        # $5 floor or 5% of spend
        return max(0.05 * expected_val, 5.0)

    elif metric == "revenue":
        # $10 floor or 8% of revenue
        return max(0.08 * expected_val, 10.0)

    elif metric == "cpa":
        # CPA noise floor: 12% of CPA or $3
        return max(0.12 * expected_val, 3.0)

    elif metric == "cpm":
        return max(0.10 * expected_val, 0.50)

    elif metric == "roas":
        return max(0.15 * expected_val, 0.20)

    # Generic default floor
    return max(0.10 * expected_val, 1.0)


def _parse_valid_incident_date(d_val: Any, field_name: str, cid: str) -> pd.Timestamp:
    """Parses and validates an incident date string or timestamp."""
    if d_val is None or (isinstance(d_val, float) and np.isnan(d_val)):
        raise ValueError(f"Null or missing {field_name} in incident flags for campaign '{cid}'.")
    try:
        ts = pd.to_datetime(d_val, errors="raise")
        if pd.isna(ts):
            raise ValueError(f"Malformed {field_name} in incident flags for campaign '{cid}': {d_val}")
        return ts
    except Exception as e:
        raise ValueError(f"Malformed {field_name} in incident flags for campaign '{cid}': '{d_val}'. Details: {e}")


def _expand_incident_range(cid: str, start_val: Any, end_val: Any) -> List[Tuple[str, str]]:
    """Inclusively expands every calendar date between start_date and end_date."""
    s_ts = _parse_valid_incident_date(start_val, "start_date", cid)
    e_ts = _parse_valid_incident_date(end_val, "end_date", cid)
    if s_ts > e_ts:
        raise ValueError(
            f"Invalid incident range: start_date '{s_ts.strftime('%Y-%m-%d')}' is after end_date '{e_ts.strftime('%Y-%m-%d')}' for campaign '{cid}'."
        )
    return [(cid, d.strftime("%Y-%m-%d")) for d in pd.date_range(s_ts, e_ts, freq="D")]


def normalize_incident_flags(
    incident_flags: Optional[Union[pd.DataFrame, Set[Tuple], List[Union[Tuple, Dict[str, Any]]]]]
) -> Set[Tuple[str, str]]:
    """
    Normalizes incident flags from M2 into a standardized set of (campaign_id, date_str) tuples.
    Accepts:
    - DataFrame with ['campaign_id'|'campaign', 'day'|'date']
    - DataFrame with ['campaign_id'|'campaign', 'start_date', 'end_date']
    - Set or List of (campaign_id, date_str) or (campaign_id, start_date, end_date) tuples
    - List of dictionaries with campaign and day/date or start_date/end_date
    """
    if incident_flags is None:
        return set()

    flag_set: Set[Tuple[str, str]] = set()

    if isinstance(incident_flags, pd.DataFrame):
        df_flags = incident_flags.copy()
        col_map = resolve_aliases(list(df_flags.columns))
        df_flags = df_flags.rename(columns=col_map)
        cid_col = "campaign_id" if "campaign_id" in df_flags.columns else ("campaign" if "campaign" in df_flags.columns else None)
        if not cid_col:
            raise ValueError("Incident flags DataFrame must contain a 'campaign_id' or 'campaign' column.")

        has_range = "start_date" in df_flags.columns and "end_date" in df_flags.columns
        date_col = "day" if "day" in df_flags.columns else ("date" if "date" in df_flags.columns else None)

        if not has_range and not date_col:
            raise ValueError("Incident flags DataFrame must contain 'day'/'date' or 'start_date'/'end_date' columns.")

        for _, row in df_flags.iterrows():
            cid = str(row[cid_col]).strip()
            if not cid or cid.lower() == "nan":
                raise ValueError("Missing campaign identifier in incident flags record.")
            if has_range:
                for pair in _expand_incident_range(cid, row["start_date"], row["end_date"]):
                    flag_set.add(pair)
            else:
                ts = _parse_valid_incident_date(row[date_col], date_col, cid)
                flag_set.add((cid, ts.strftime("%Y-%m-%d")))
        return flag_set

    if isinstance(incident_flags, (set, tuple, list)):
        for item in incident_flags:
            if isinstance(item, (tuple, list)):
                if len(item) == 2:
                    cid = str(item[0]).strip()
                    ts = _parse_valid_incident_date(item[1], "date", cid)
                    flag_set.add((cid, ts.strftime("%Y-%m-%d")))
                elif len(item) >= 3:
                    cid = str(item[0]).strip()
                    for pair in _expand_incident_range(cid, item[1], item[2]):
                        flag_set.add(pair)
                else:
                    raise ValueError(f"Invalid incident tuple: expected 2 or 3 elements, got {item}")
            elif isinstance(item, dict):
                cid = str(item.get("campaign_id", item.get("campaign", item.get("cid", "")))).strip()
                if not cid or cid.lower() == "nan":
                    raise ValueError(f"Missing campaign identifier in incident flag dict: {item}")
                if "start_date" in item and "end_date" in item:
                    for pair in _expand_incident_range(cid, item["start_date"], item["end_date"]):
                        flag_set.add(pair)
                else:
                    d_val = item.get("day", item.get("date", item.get("day_date", None)))
                    ts = _parse_valid_incident_date(d_val, "date", cid)
                    flag_set.add((cid, ts.strftime("%Y-%m-%d")))
            else:
                raise ValueError(f"Unsupported incident flag entry type: {type(item)}")
        return flag_set

    raise TypeError(f"Unsupported incident flags type: {type(incident_flags)}")




def is_day_frozen(
    target_date: pd.Timestamp,
    campaign_id: str,
    flagged_set: Set[Tuple[str, str]],
    freeze_days: int = DEFAULT_FREEZE_DAYS,
) -> bool:
    """
    Checks if a target date for a campaign falls within an active incident freeze window
    (i.e., within freeze_days [0, freeze_days - 1] after an incident flag).
    """
    if not flagged_set:
        return False

    for offset in range(freeze_days):
        check_date = (target_date - pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
        if (campaign_id, check_date) in flagged_set:
            return True
    return False


def compute_baseline_residuals(
    df: pd.DataFrame,
    window_days: int = DEFAULT_WINDOW_DAYS,
    freeze_days: int = DEFAULT_FREEZE_DAYS,
    t_multiplier: float = DEFAULT_T_MULTIPLIER,
    incident_flags: Optional[Union[pd.DataFrame, Set[Tuple], List[Union[Tuple, Dict[str, Any]]]]] = None,
    metrics: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Computes rolling baseline, MAD, uncertainty floors, effective bands, and residuals.

    Strict Causal & Integrity Invariants:
    1. 1-Day Lag Shift: Day t's baseline is estimated STRICTLY from past observations [t - window_days, t - 1].
       Observation t is NEVER in its own baseline. Future observations are NEVER accessed.
    2. Incident Freeze: Past observations falling in a flagged incident window (up to freeze_days)
       are excluded from the baseline training pool.
    3. Day-of-Week Adjustment: Historical observations matching the target day-of-week are weighted / used
       to capture weekday/weekend traffic patterns.
    4. Effective Band: effective_band = max(T * (1.4826 * MAD), metric_specific_noise_floor).
    5. Phase 0 Contract Output: returns residual table conforming to shared team interface.
    6. Warm-up Integrity: Sets NaN baselines until sufficient historical data exists (>= 3 obs or >= 2 matching DOWs).

    Returns:
        (residual_table_df, baseline_bands_df)
    """
    if window_days not in ALLOWED_WINDOW_DAYS:
        raise ValueError(
            f"Invalid window_days: {window_days}. Supported benchmark windows are {ALLOWED_WINDOW_DAYS}."
        )

    if metrics is None:
        metrics = [m for m in BASELINE_METRICS if m in df.columns]

    flagged_set = normalize_incident_flags(incident_flags)

    # Ensure sorted by campaign and date
    df_sorted = df.copy()
    if "date_parsed" not in df_sorted.columns:
        df_sorted["date_parsed"] = pd.to_datetime(df_sorted["day"])
    df_sorted = df_sorted.sort_values(by=["campaign_id", "date_parsed"]).reset_index(drop=True)
    df_sorted["dow"] = df_sorted["date_parsed"].dt.dayofweek

    residual_rows: List[Dict] = []
    band_rows: List[Dict] = []

    # Process per campaign
    for cid, camp_df in df_sorted.groupby("campaign_id", sort=False):
        camp_name = camp_df["campaign_name"].iloc[0] if "campaign_name" in camp_df.columns else str(cid)
        dates = camp_df["date_parsed"].values
        days_str = camp_df["day"].values
        dow_arr = camp_df["dow"].values
        n_obs = len(camp_df)

        # Pre-extract metric arrays for fast vector lookups
        metric_arrays = {m: camp_df[m].to_numpy(dtype=float) for m in metrics}
        clicks_arr = camp_df["clicks"].to_numpy(dtype=float) if "clicks" in camp_df.columns else None
        imp_arr = camp_df["impressions"].to_numpy(dtype=float) if "impressions" in camp_df.columns else None

        # Pre-calculate frozen mask for historical filtering
        frozen_history_mask = np.zeros(n_obs, dtype=bool)
        for i in range(n_obs):
            d_ts = pd.Timestamp(dates[i])
            frozen_history_mask[i] = is_day_frozen(d_ts, cid, flagged_set, freeze_days)

        # Rolling evaluation across time
        for i in range(n_obs):
            cur_date_ts = pd.Timestamp(dates[i])
            cur_day_str = days_str[i]
            cur_dow = dow_arr[i]
            is_cur_day_frozen = bool(frozen_history_mask[i])

            # Historical slice: strictly [t - window_days, t - 1]
            # Find indices where date is in range and < current date
            hist_mask = np.zeros(i, dtype=bool)
            for j in range(i):
                diff_days = (cur_date_ts - pd.Timestamp(dates[j])).days
                if 1 <= diff_days <= window_days:
                    # Exclude if the historical day itself was in a frozen incident period
                    if not frozen_history_mask[j]:
                        hist_mask[j] = True

            hist_indices = np.where(hist_mask)[0]
            dow_hist_indices = [idx for idx in hist_indices if dow_arr[idx] == cur_dow]

            # Pre-estimate baseline expected clicks and impressions for noise floor calculations
            exp_clicks = 100.0
            if clicks_arr is not None and len(hist_indices) > 0:
                exp_clicks = float(np.median(clicks_arr[hist_indices]))
            exp_imp = 5000.0
            if imp_arr is not None and len(hist_indices) > 0:
                exp_imp = float(np.median(imp_arr[hist_indices]))

            for m in metrics:
                actual_val = float(metric_arrays[m][i])
                hist_vals = metric_arrays[m][hist_indices]
                dow_hist_vals = metric_arrays[m][dow_hist_indices]

                # Drop NaNs from historical pool (e.g. CPA on 0-conversion days)
                clean_hist = hist_vals[~np.isnan(hist_vals)]
                clean_dow_hist = dow_hist_vals[~np.isnan(dow_hist_vals)]

                # DOW Adjusted Median Calculation with strict warm-up validation
                if len(clean_dow_hist) >= 2:
                    expected_val = float(np.median(clean_dow_hist))
                elif len(clean_hist) >= 3:
                    expected_val = float(np.median(clean_hist))
                else:
                    # Warm-up / initial period: insufficient historical data -> set to NaN
                    expected_val = np.nan

                if np.isnan(expected_val):
                    mad_val = np.nan
                    robust_sigma = np.nan
                    noise_floor = np.nan
                    effective_band = np.nan
                    lower_band = np.nan
                    upper_band = np.nan
                    residual = np.nan
                    robust_z = np.nan
                else:
                    # MAD and Robust Sigma (1.4826 * MAD)
                    if len(clean_hist) >= 3:
                        _, robust_sigma = calculate_mad(clean_hist)
                        mad_val = robust_sigma / MAD_SCALE_FACTOR
                    else:
                        mad_val = 0.0
                        robust_sigma = 0.0

                    # Noise Floor
                    noise_floor = get_noise_floor(
                        metric=m,
                        expected_val=expected_val,
                        expected_clicks=exp_clicks,
                        expected_imp=exp_imp,
                    )

                    # Effective Band = max(T * Robust_Sigma, Noise_Floor)
                    effective_band = max(float(t_multiplier * robust_sigma), float(noise_floor))

                    # Bounds
                    if m in ["ctr", "cvr"]:
                        lower_band = float(np.clip(expected_val - effective_band, 0.0, 1.0))
                        upper_band = float(np.clip(expected_val + effective_band, 0.0, 1.0))
                    elif m in NON_NEGATIVE_METRICS or m in ["cpa", "cpm", "roas"]:
                        lower_band = float(max(0.0, expected_val - effective_band))
                        upper_band = float(expected_val + effective_band)
                    else:
                        lower_band = float(expected_val - effective_band)
                        upper_band = float(expected_val + effective_band)

                    # Residual and Standardized Robust Z-score
                    if np.isnan(actual_val):
                        residual = np.nan
                        robust_z = np.nan
                    else:
                        residual = actual_val - expected_val
                        robust_z = float(residual / effective_band) if effective_band > 1e-9 else 0.0

                # Append to Phase 0 Residual Table
                residual_rows.append({
                    "campaign_id": cid,
                    "date": cur_day_str,
                    "metric": m,
                    "actual": round(actual_val, 5) if not np.isnan(actual_val) else np.nan,
                    "expected": round(expected_val, 5) if not np.isnan(expected_val) else np.nan,
                    "mad": round(mad_val, 5) if not np.isnan(mad_val) else np.nan,
                    "noise_floor": round(noise_floor, 5) if not np.isnan(noise_floor) else np.nan,
                    "robust_z": round(robust_z, 4) if not np.isnan(robust_z) else np.nan,
                    "frozen_flag": is_cur_day_frozen,
                    "residual": round(residual, 5) if not np.isnan(residual) else np.nan,
                    "effective_band": round(effective_band, 5) if not np.isnan(effective_band) else np.nan,
                    "window_days": window_days,
                    "campaign_name": camp_name,
                })

                # Append to Baseline Bands Export
                band_rows.append({
                    "campaign_id": cid,
                    "campaign_name": camp_name,
                    "date": cur_day_str,
                    "metric": m,
                    "actual": round(actual_val, 5) if not np.isnan(actual_val) else np.nan,
                    "expected": round(expected_val, 5) if not np.isnan(expected_val) else np.nan,
                    "lower_band": round(lower_band, 5) if not np.isnan(lower_band) else np.nan,
                    "upper_band": round(upper_band, 5) if not np.isnan(upper_band) else np.nan,
                    "robust_sigma": round(robust_sigma, 5) if not np.isnan(robust_sigma) else np.nan,
                    "noise_floor": round(noise_floor, 5) if not np.isnan(noise_floor) else np.nan,
                    "effective_band": round(effective_band, 5) if not np.isnan(effective_band) else np.nan,
                    "robust_z": round(robust_z, 4) if not np.isnan(robust_z) else np.nan,
                    "is_frozen": is_cur_day_frozen,
                    "window_days": window_days,
                })

    residual_df = pd.DataFrame(residual_rows)
    bands_df = pd.DataFrame(band_rows)
    return residual_df, bands_df


# =============================================================================
# PHASE 3: SENSITIVITY SWEEPS & STUB DATA GENERATOR
# =============================================================================

def run_window_sensitivity_sweep(
    df: pd.DataFrame,
    windows: List[int] = ALLOWED_WINDOW_DAYS,
    freeze_days: int = DEFAULT_FREEZE_DAYS,
    t_multiplier: float = DEFAULT_T_MULTIPLIER,
    incident_flags: Optional[Union[pd.DataFrame, Set[Tuple], List[Union[Tuple, Dict[str, Any]]]]] = None,
    out_dir: Optional[str] = None,
) -> pd.DataFrame:
    """
    Executes baseline sensitivity analysis across different rolling window sizes (21, 28, 35 days).
    Accepts incident flags and passes them consistently to compute_baseline_residuals().
    Computes dispersion, mean band width, and residual stability.
    """
    summary_records: List[Dict] = []

    for w in windows:
        res_df, _ = compute_baseline_residuals(
            df,
            window_days=w,
            freeze_days=freeze_days,
            t_multiplier=t_multiplier,
            incident_flags=incident_flags,
        )
        for m in res_df["metric"].unique():
            m_sub = res_df[res_df["metric"] == m].dropna(subset=["actual", "expected", "residual", "robust_z"])
            abs_z = m_sub["robust_z"].abs()
            summary_records.append({
                "window_days": w,
                "metric": m,
                "mean_effective_band": round(float(m_sub["effective_band"].mean()), 4) if len(m_sub) > 0 else np.nan,
                "median_effective_band": round(float(m_sub["effective_band"].median()), 4) if len(m_sub) > 0 else np.nan,
                "mean_absolute_residual": round(float(m_sub["residual"].abs().mean()), 4) if len(m_sub) > 0 else np.nan,
                "pct_z_gt_3": round(float((abs_z > 3.0).mean() * 100.0), 2) if len(m_sub) > 0 else 0.0,
                "pct_z_gt_4": round(float((abs_z > 4.0).mean() * 100.0), 2) if len(m_sub) > 0 else 0.0,
                "total_evaluations": len(m_sub),
            })

    summary_df = pd.DataFrame(summary_records)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        summary_df.to_csv(os.path.join(out_dir, "baseline_sensitivity_summary.csv"), index=False)
    return summary_df


def generate_synthetic_stub_data(out_dir: str = "M1/data") -> Tuple[str, str]:
    """
    Generates synthetic stub datasets for pipeline testing:
    1. `synthetic_campaign_stub.csv`: Minimal 3-campaign x 30-day stub.
    2. `synthetic_campaign_metrics.csv`: Full 20-campaign x 180-day benchmark.
    """
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(42)

    # 1. Generate 3-campaign x 30-day stub
    stub_campaigns = [
        ("C01", "Search - Brand Core (Stub Large)", 1500.0, 30000, 1200, 45, 3500.0),
        ("C02", "Display - Retargeting (Stub Med)", 450.0, 12000, 350, 12, 900.0),
        ("C03", "Search - Niche Longtail (Stub Small)", 45.0, 1200, 35, 2, 80.0),
    ]
    stub_dates = pd.date_range("2026-01-01", periods=30, freq="D")
    stub_rows = []

    for d in stub_dates:
        d_str = d.strftime("%Y-%m-%d")
        dow_factor = 0.85 if d.dayofweek in [5, 6] else 1.05
        for cid, name, b_cost, b_imp, b_clk, b_conv, b_rev in stub_campaigns:
            imp = max(int(b_imp * dow_factor * rng.lognormal(0, 0.05)), 10)
            clk = max(int(b_clk * dow_factor * rng.lognormal(0, 0.05)), 1)
            conv = max(int(b_conv * dow_factor * rng.lognormal(0, 0.10)), 0)
            cost = round(float(b_cost * dow_factor * rng.lognormal(0, 0.04)), 2)
            rev = round(float(conv * (b_rev / max(b_conv, 1)) * rng.lognormal(0, 0.08)), 2)

            # Seed an obvious broken tracking anomaly on day 15 for C01
            if cid == "C01" and d_str == "2026-01-15":
                conv = 0
                rev = 0.0

            stub_rows.append({
                "date": d_str,
                "campaign_id": cid,
                "campaign_name": name,
                "spend": cost,
                "impressions": imp,
                "clicks": clk,
                "conversions": conv,
                "revenue": rev,
                "bid_strategy": "target_cpa",
            })

    stub_df = pd.DataFrame(stub_rows)
    stub_path = os.path.join(out_dir, "synthetic_campaign_stub.csv")
    stub_df.to_csv(stub_path, index=False)

    # 2. Generate full synthetic dataset (20 campaigns x 180 days)
    campaign_catalog = [
        ("C01", "Google | Brand Search", "large", 1500.0, 35000, 1400, 60, 4800.0),
        ("C02", "Google | Generic Search", "large", 3000.0, 20000, 1100, 30, 3200.0),
        ("C03", "Google | Competitor Search", "large", 900.0, 5000, 250, 6, 600.0),
        ("C04", "Google | Shopping Bestsellers", "large", 5500.0, 450000, 5500, 140, 11000.0),
        ("C05", "Google | Performance Max", "large", 6000.0, 300000, 4500, 120, 12000.0),
        ("C06", "Meta | Prospecting Broad", "large", 5800.0, 500000, 6200, 90, 8800.0),
        ("C07", "Shopping - Seasonal Collections", "medium", 850.0, 38000, 1100, 30, 2400.0),
        ("C08", "Search - Long Tail Products", "medium", 1300.0, 50000, 1500, 45, 3300.0),
        ("C09", "Display - Lookalike Audiences", "medium", 600.0, 36000, 1200, 40, 2800.0),
        ("C10", "Social - Prospecting Broad", "medium", 900.0, 48000, 1600, 50, 3400.0),
        ("C11", "Search - Local Intent", "medium", 1400.0, 35000, 1200, 15, 750.0),
        ("C12", "Social - Retargeting Cart", "medium", 700.0, 22000, 550, 20, 1200.0),
        ("C13", "Shopping - Clearance", "medium", 800.0, 50000, 1100, 30, 1600.0),
        ("C14", "Video - Product Demos", "medium", 950.0, 36000, 1200, 20, 800.0),
        ("C15", "Search - Niche Accessories", "small", 60.0, 3500, 70, 2, 90.0),
        ("C16", "Display - Newsletter Signup", "small", 70.0, 2900, 70, 2, 100.0),
        ("C17", "Search - B2B Enquiries", "small", 150.0, 6000, 180, 3, 90.0),
        ("C18", "Social - Event Promo", "small", 55.0, 3700, 115, 3, 150.0),
        ("C19", "Shopping - Premium Line", "small", 65.0, 4200, 105, 1, 35.0),
        ("C20", "Search - Regional Test Market", "small", 45.0, 2500, 55, 1, 40.0),
    ]

    dates_180 = pd.date_range("2026-01-01", periods=180, freq="D")
    full_rows = []
    for d in dates_180:
        d_str = d.strftime("%Y-%m-%d")
        dow_factor = 0.85 if d.dayofweek in [5, 6] else 1.03
        for cid, name, tier, b_cost, b_imp, b_clk, b_conv, b_rev in campaign_catalog:
            noise_sigma = 0.04 if tier == "large" else (0.07 if tier == "medium" else 0.10)
            imp = max(int(b_imp * dow_factor * rng.lognormal(0, noise_sigma)), 5)
            clk = max(int(b_clk * dow_factor * rng.lognormal(0, noise_sigma)), 1)
            conv = max(int(b_conv * dow_factor * rng.lognormal(0, noise_sigma * 1.5)), 0)
            cost = round(float(b_cost * dow_factor * rng.lognormal(0, noise_sigma)), 2)
            rev = round(float(conv * (b_rev / max(b_conv, 1)) * rng.lognormal(0, 0.08)), 2)

            full_rows.append({
                "date": d_str,
                "campaign_id": cid,
                "campaign_name": name,
                "spend": cost,
                "impressions": imp,
                "clicks": clk,
                "conversions": conv,
                "revenue": rev,
                "bid_strategy": "target_cpa" if tier == "large" else "manual_cpc",
            })

    full_df = pd.DataFrame(full_rows)
    full_path = os.path.join(out_dir, "synthetic_campaign_metrics.csv")
    full_df.to_csv(full_path, index=False)

    return stub_path, full_path


# =============================================================================
# PHASE 4: POLISH — WEEKLY AGGREGATES & EXPORTS
# =============================================================================

def generate_weekly_small_campaign_aggregates(
    df: pd.DataFrame,
    spend_threshold: float = SMALL_CAMPAIGN_DAILY_SPEND_THRESHOLD,
    conv_threshold: float = SMALL_CAMPAIGN_CONV_THRESHOLD,
    out_dir: Optional[str] = None,
) -> Tuple[pd.DataFrame, str]:
    """
    Creates a weekly aggregate report for small, high-volatility campaigns.
    Aggregates numerators and denominators first before computing ratios (CPA, CTR, CVR, ROAS).
    """
    df_work = df.copy()
    if "date_parsed" not in df_work.columns:
        df_work["date_parsed"] = pd.to_datetime(df_work["day"])

    # Identify small campaigns based on average daily spend or conversions
    camp_stats = df_work.groupby("campaign_id").agg({
        "cost": "mean",
        "conv": "mean",
    })
    small_cids = camp_stats[
        (camp_stats["cost"] <= spend_threshold) | (camp_stats["conv"] <= conv_threshold)
    ].index.tolist()

    if not small_cids:
        # Fallback to bottom 30% by spend
        small_cids = camp_stats.sort_values(by="cost").head(6).index.tolist()

    small_df = df_work[df_work["campaign_id"].isin(small_cids)].copy()
    small_df["year_week"] = small_df["date_parsed"].dt.strftime("%Y-W%W")

    # Group by campaign and ISO week
    weekly_agg = small_df.groupby(["campaign_id", "campaign_name", "year_week"]).agg(
        total_cost=("cost", "sum"),
        total_impressions=("impressions", "sum"),
        total_clicks=("clicks", "sum"),
        total_conv=("conv", "sum"),
        total_revenue=("revenue", "sum"),
        observed_days=("day", "count"),
    ).reset_index()

    # Calculate true aggregate ratios
    weekly_agg["cpa"] = np.where(
        weekly_agg["total_conv"] > 0,
        np.round(weekly_agg["total_cost"] / weekly_agg["total_conv"], 2),
        np.nan,
    )
    weekly_agg["ctr"] = np.where(
        weekly_agg["total_impressions"] > 0,
        np.round(weekly_agg["total_clicks"] / weekly_agg["total_impressions"], 5),
        np.nan,
    )
    weekly_agg["cvr"] = np.where(
        weekly_agg["total_clicks"] > 0,
        np.round(weekly_agg["total_conv"] / weekly_agg["total_clicks"], 5),
        np.nan,
    )
    weekly_agg["roas"] = np.where(
        weekly_agg["total_cost"] > 0,
        np.round(weekly_agg["total_revenue"] / weekly_agg["total_cost"], 4),
        np.nan,
    )

    weekly_agg = weekly_agg.sort_values(by=["campaign_id", "year_week"]).reset_index(drop=True)

    # Generate Markdown summary table
    md_lines = [
        "# Weekly Performance Aggregates: Low-Volume & Small Campaigns",
        "",
        "Aggregated weekly view for high-variance small campaigns to stabilize small-sample ratios.",
        "**Methodology:** Ratios (CPA, CTR, CVR, ROAS) are calculated from weekly sums rather than averaging daily ratios.",
        "",
        "| Campaign ID | Campaign Name | Year-Week | Days | Total Cost ($) | Total Conv | Weekly CPA ($) | Weekly CVR (%) | Weekly CTR (%) |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for _, row in weekly_agg.head(30).iterrows():
        cpa_str = f"${row['cpa']:.2f}" if not np.isnan(row["cpa"]) else "N/A"
        cvr_str = f"{row['cvr'] * 100.0:.2f}%" if not np.isnan(row["cvr"]) else "N/A"
        ctr_str = f"{row['ctr'] * 100.0:.2f}%" if not np.isnan(row["ctr"]) else "N/A"
        md_lines.append(
            f"| {row['campaign_id']} | {row['campaign_name']} | {row['year_week']} | {row['observed_days']} | "
            f"${row['total_cost']:,.2f} | {int(row['total_conv'])} | {cpa_str} | {cvr_str} | {ctr_str} |"
        )

    md_report = "\n".join(md_lines)

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        weekly_agg.to_csv(os.path.join(out_dir, "weekly_aggregate_small_campaigns.csv"), index=False)
        with open(os.path.join(out_dir, "weekly_aggregate_small_campaigns.md"), "w") as f:
            f.write(md_report)

    return weekly_agg, md_report


# =============================================================================
# MAIN CLI PIPELINE EXECUTION
# =============================================================================

def run_m1_pipeline(
    input_source: Union[str, pd.DataFrame],
    window_days: int = DEFAULT_WINDOW_DAYS,
    freeze_days: int = DEFAULT_FREEZE_DAYS,
    t_multiplier: float = DEFAULT_T_MULTIPLIER,
    incident_flags_path: Optional[str] = None,
    output_dir: str = "M1/outputs",
    reports_dir: str = "M1/reports",
) -> Dict[str, str]:
    """
    Executes the complete M1 end-to-end data and baseline pipeline.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    print(f"--> [M1] Loading & validating data from: {input_source}")
    df = load_real(input_source)
    print(f"--> [M1] Ingestion complete: {len(df)} rows, {df['campaign_id'].nunique()} campaigns.")

    # Load incident flags if provided (raise FileNotFoundError if path given but missing)
    incident_flags = None
    if incident_flags_path is not None:
        if not os.path.exists(incident_flags_path):
            raise FileNotFoundError(f"Incident flags file not found at path: {incident_flags_path}")
        print(f"--> [M1] Ingesting incident freeze flags from: {incident_flags_path}")
        incident_flags = pd.read_csv(incident_flags_path)

    # Compute Rolling Baselines and Residuals
    print(f"--> [M1] Computing rolling baselines (Window={window_days}d, Freeze={freeze_days}d, T={t_multiplier})...")
    res_df, bands_df = compute_baseline_residuals(
        df=df,
        window_days=window_days,
        freeze_days=freeze_days,
        t_multiplier=t_multiplier,
        incident_flags=incident_flags,
    )

    # Export Phase 0 Residual Table
    res_path = os.path.join(output_dir, "residual_table.csv")
    res_df.to_csv(res_path, index=False)
    print(f"--> [M1] Phase 0 Residual Table exported: {res_path} ({len(res_df)} metric evaluations)")

    # Export Baseline Bands
    bands_path = os.path.join(output_dir, "baseline_bands_export.csv")
    bands_df.to_csv(bands_path, index=False)
    print(f"--> [M1] Baseline Bands Exported: {bands_path}")

    # Generate Weekly Aggregates
    print("--> [M1] Generating weekly aggregates for small campaigns...")
    weekly_df, _ = generate_weekly_small_campaign_aggregates(df, out_dir=reports_dir)
    print(f"--> [M1] Weekly aggregates exported ({len(weekly_df)} campaign-weeks).")

    # Run Sensitivity Sweep with loaded incident flags
    print(f"--> [M1] Running baseline window sensitivity sweep ({ALLOWED_WINDOW_DAYS})...")
    run_window_sensitivity_sweep(
        df,
        windows=ALLOWED_WINDOW_DAYS,
        freeze_days=freeze_days,
        t_multiplier=t_multiplier,
        incident_flags=incident_flags,
        out_dir=output_dir,
    )

    return {
        "residual_table": res_path,
        "baseline_bands": bands_path,
        "weekly_aggregates": os.path.join(reports_dir, "weekly_aggregate_small_campaigns.csv"),
        "sensitivity_summary": os.path.join(output_dir, "baseline_sensitivity_summary.csv"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M1 Data & Baseline Pipeline")
    parser.add_argument("--input", type=str, default="M1/data/synthetic_campaign_stub.csv", help="Input dataset path")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_DAYS, help="Rolling window size in days (21, 28, 35)")
    parser.add_argument("--freeze-days", type=int, default=DEFAULT_FREEZE_DAYS, help="Incident freeze duration in days")
    parser.add_argument("--t", type=float, default=DEFAULT_T_MULTIPLIER, help="Robust threshold multiplier T")
    parser.add_argument("--flags", type=str, default=None, help="Path to M2 incident flags CSV")
    parser.add_argument("--generate-stub", action="store_true", help="Generate synthetic stub data before running")
    args = parser.parse_args()

    if args.generate_stub or not os.path.exists(args.input):
        generate_synthetic_stub_data("M1/data")
        if not os.path.exists(args.input):
            args.input = "M1/data/synthetic_campaign_stub.csv"

    run_m1_pipeline(
        input_source=args.input,
        window_days=args.window,
        freeze_days=args.freeze_days,
        t_multiplier=args.t,
        incident_flags_path=args.flags,
    )

