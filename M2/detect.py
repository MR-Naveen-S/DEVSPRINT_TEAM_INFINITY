"""
M2 Anomaly Detection and Classification Core Implementation.
"""

from typing import Optional, Union, Dict, Any, List, Set, Tuple
import pandas as pd
import numpy as np

from M2.config import M2Config, DEFAULT_CONFIG


def detect_anomalies(
    residuals: pd.DataFrame,
    metrics: Optional[pd.DataFrame] = None,
    config: Optional[Union[M2Config, Dict[str, Any]]] = None,
    incident_feedback: Optional[Any] = None
) -> pd.DataFrame:
    """
    Detect and classify campaign-day anomalies.

    Parameters:
        residuals: M1 residual DataFrame.
            Required columns: ['campaign', 'date', 'metric', 'actual', 'expected',
                              'mad', 'noise_floor', 'robust_z', 'frozen_flag']
        metrics: Optional campaign-day metric DataFrame (containing optional columns
            like spend, clicks, conversions, impressions, bid_strategy, budget_cap).
        config: Optional M2 settings or dictionary of configuration options.
        incident_feedback: Optional flags or frozen-day feedback.

    Returns:
        DataFrame with one row per classified flagged campaign-day event,
        following the agreed M2-to-M3 contract:
        ['campaign', 'date', 'type', 'metric', 'actual', 'expected', 'delta_pct', 'hard_rule', 'seasonal']
    """
    # 1. Setup Configuration
    if config is None:
        cfg = DEFAULT_CONFIG
    elif isinstance(config, dict):
        cfg = M2Config.from_dict(config)
    elif isinstance(config, M2Config):
        cfg = config
    else:
        cfg = DEFAULT_CONFIG

    # Define contract output columns
    output_columns = [
        "campaign",
        "date",
        "type",
        "metric",
        "actual",
        "expected",
        "delta_pct",
        "hard_rule",
        "seasonal",
    ]

    # 2. Input Validation
    if not isinstance(residuals, pd.DataFrame):
        raise TypeError("residuals must be a pandas DataFrame")

    if residuals.empty:
        return pd.DataFrame(columns=output_columns)

    required_cols = [
        "campaign",
        "date",
        "metric",
        "actual",
        "expected",
        "mad",
        "noise_floor",
        "robust_z",
        "frozen_flag",
    ]
    missing_cols = [col for col in required_cols if col not in residuals.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in residuals DataFrame: {missing_cols}")

    # Ensure caller DataFrame is not mutated
    res_df = residuals.copy()
    
    # Check for nulls in critical identifiers
    if res_df["campaign"].isnull().any() or res_df["date"].isnull().any() or res_df["metric"].isnull().any():
        raise ValueError("residuals DataFrame contains null values in campaign, date, or metric columns")

    # Validate numeric types
    numeric_cols = ["actual", "expected", "mad", "noise_floor", "robust_z"]
    for col in numeric_cols:
        if not pd.api.types.is_numeric_dtype(res_df[col]):
            try:
                res_df[col] = pd.to_numeric(res_df[col])
            except Exception as e:
                raise ValueError(f"Column '{col}' must be numeric: {e}")
        if res_df[col].isnull().any():
            raise ValueError(f"residuals DataFrame contains null values in numeric column '{col}'")

    # Parse dates internally for sorting
    res_df["_date_dt"] = pd.to_datetime(res_df["date"])

    # Prepare optional metrics DataFrame if supplied
    metrics_df = None
    if metrics is not None:
        if not isinstance(metrics, pd.DataFrame):
            raise TypeError("metrics must be a pandas DataFrame if provided")
        if not metrics.empty:
            metrics_df = metrics.copy()
            if "_date_dt" not in metrics_df.columns and "date" in metrics_df.columns:
                metrics_df["_date_dt"] = pd.to_datetime(metrics_df["date"])

    # 3. Statistical Anomaly Candidates & Volume Guard Check
    res_df["is_stat_candidate"] = False
    
    # Check threshold condition |robust_z| > T and not frozen
    non_frozen_mask = ~res_df["frozen_flag"].astype(bool)
    z_mask = res_df["robust_z"].abs() > cfg.robust_threshold
    
    candidates_mask = non_frozen_mask & z_mask

    # Volume guard filter for count-based / volume metrics
    for idx, row in res_df[candidates_mask].iterrows():
        metric = str(row["metric"]).lower()
        expected_val = float(row["expected"])
        passes_guard = True
        
        if "conversion" in metric and expected_val < cfg.min_volume_conversions:
            passes_guard = False
        elif "click" in metric and expected_val < cfg.min_volume_clicks:
            passes_guard = False
        elif "spend" in metric and expected_val < cfg.min_volume_spend:
            passes_guard = False
            
        if passes_guard:
            res_df.loc[idx, "is_stat_candidate"] = True

    # 4. Persistence Filtering
    # Rule: Flagged on at least min_flagged out of lookback_days valid observations for same (campaign, metric)
    res_df["stat_confirmed"] = False

    if cfg.enable_persistence:
        res_df = res_df.sort_values(by=["campaign", "metric", "_date_dt"]).reset_index(drop=True)
        
        # Process persistence per (campaign, metric)
        for (cmp, mtr), group in res_df.groupby(["campaign", "metric"]):
            group_indices = group.index.tolist()
            # Only consider valid observations (non-frozen)
            valid_group = group[~group["frozen_flag"].astype(bool)]
            valid_indices = valid_group.index.tolist()
            
            for idx in valid_indices:
                if not res_df.loc[idx, "is_stat_candidate"]:
                    continue
                # Look at position of idx in valid_indices
                pos = valid_indices.index(idx)
                start_pos = max(0, pos - cfg.persistence_lookback_days + 1)
                window_indices = valid_indices[start_pos : pos + 1]
                
                # Count candidates in lookback window
                candidate_count = sum(res_df.loc[w_idx, "is_stat_candidate"] for w_idx in window_indices)
                if candidate_count >= cfg.persistence_min_flagged:
                    res_df.loc[idx, "stat_confirmed"] = True
    else:
        res_df["stat_confirmed"] = res_df["is_stat_candidate"]

    # 5. Multi-Metric Pivot for Campaign-Day Level Reasoning
    # Build campaign-day lookup dictionary for metrics
    cmp_day_metrics: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    for _, row in res_df.iterrows():
        key = (str(row["campaign"]), str(row["date"]))
        m_name = str(row["metric"]).lower()
        if key not in cmp_day_metrics:
            cmp_day_metrics[key] = {}
        cmp_day_metrics[key][m_name] = {
            "actual": float(row["actual"]),
            "expected": float(row["expected"]),
            "robust_z": float(row["robust_z"]),
            "mad": float(row["mad"]),
            "frozen_flag": bool(row["frozen_flag"]),
            "is_stat_candidate": bool(row["is_stat_candidate"]),
            "stat_confirmed": bool(row["stat_confirmed"]),
            "original_metric": str(row["metric"]),
        }

    # Integrate metrics_df extra columns if provided
    extra_metrics: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if metrics_df is not None:
        for _, row in metrics_df.iterrows():
            if "campaign" in row and "date" in row:
                key = (str(row["campaign"]), str(row["date"]))
                extra_metrics[key] = row.to_dict()

    # 6. Hard-Rule Detection per Campaign
    # A. Tracking Break Detection
    # Conversions == 0 for >= min_consec_zeros consecutive valid days while clicks & spend are stable,
    # and expected conversions >= min_expected_conversions.
    hard_rule_events: Dict[Tuple[str, str], Dict[str, Any]] = {}

    all_campaigns = res_df["campaign"].unique()
    all_dates_sorted = sorted(res_df["_date_dt"].unique())
    date_to_str = {d: pd.to_datetime(d).strftime("%Y-%m-%d") for d in all_dates_sorted}

    for cmp in all_campaigns:
        cmp_rows = res_df[res_df["campaign"] == cmp].sort_values(by="_date_dt")
        unique_dates = cmp_rows["_date_dt"].unique()
        
        # Track consecutive zero conversion days
        consec_zeros = 0
        for d in unique_dates:
            d_str = date_to_str[d]
            key = (cmp, d_str)
            m_dict = cmp_day_metrics.get(key, {})
            conv_data = m_dict.get("conversions") or m_dict.get("conversion")
            
            # Check if metrics_df has conversions
            extra_data = extra_metrics.get(key, {})
            conv_act = conv_data["actual"] if conv_data else extra_data.get("conversions", None)
            conv_exp = conv_data["expected"] if conv_data else extra_data.get("expected_conversions", None)
            
            if conv_act is not None and float(conv_act) == 0.0:
                consec_zeros += 1
            else:
                consec_zeros = 0
                
            if consec_zeros >= cfg.tracking_break_min_consec_zeros and conv_exp is not None:
                conv_exp_val = float(conv_exp)
                if conv_exp_val >= cfg.tracking_break_min_expected_conversions:
                    # Check clicks & spend stability
                    clicks_data = m_dict.get("clicks") or m_dict.get("click")
                    spend_data = m_dict.get("spend") or m_dict.get("cost")
                    
                    clicks_stable = True
                    if clicks_data:
                        clicks_z = clicks_data["robust_z"]
                        clicks_act = clicks_data["actual"]
                        clicks_exp = clicks_data["expected"]
                        if clicks_z < -3.5 and (clicks_exp > 0 and clicks_act / clicks_exp < 0.2):
                            clicks_stable = False
                            
                    spend_stable = True
                    if spend_data:
                        spend_z = spend_data["robust_z"]
                        spend_act = spend_data["actual"]
                        spend_exp = spend_data["expected"]
                        if spend_z < -3.5 and (spend_exp > 0 and spend_act / spend_exp < 0.2):
                            spend_stable = False
                            
                    if clicks_stable and spend_stable:
                        actual_val = conv_act
                        expected_val = conv_exp_val
                        hard_rule_events[key] = {
                            "type": "tracking_break",
                            "metric": conv_data["original_metric"] if conv_data else "conversions",
                            "actual": actual_val,
                            "expected": expected_val,
                            "hard_rule": True,
                        }

    # B. Budget Exhaustion Detection
    # Look for spend reaching budget cap or sharp drop in spend/clicks late in cycle with high expected volume
    for key, extra_data in extra_metrics.items():
        cmp, d_str = key
        budget_cap = extra_data.get("budget_cap", None)
        spend_act = extra_data.get("spend", None)
        
        if budget_cap is not None and spend_act is not None:
            try:
                b_cap = float(budget_cap)
                s_act = float(spend_act)
                if b_cap > 0 and s_act >= 0.98 * b_cap:
                    m_dict = cmp_day_metrics.get(key, {})
                    spend_data = m_dict.get("spend") or m_dict.get("cost")
                    hard_rule_events[key] = {
                        "type": "budget_exhausted",
                        "metric": spend_data["original_metric"] if spend_data else "spend",
                        "actual": s_act,
                        "expected": spend_data["expected"] if spend_data else b_cap,
                        "hard_rule": True,
                    }
            except (ValueError, TypeError):
                pass

    # Budget exhaustion fallback if spend/clicks severely drop under high expected volume
    for key, m_dict in cmp_day_metrics.items():
        if key in hard_rule_events:
            continue
        spend_data = m_dict.get("spend") or m_dict.get("cost")
        clicks_data = m_dict.get("clicks") or m_dict.get("click")
        
        if spend_data and clicks_data:
            s_z = spend_data["robust_z"]
            c_z = clicks_data["robust_z"]
            s_exp = spend_data["expected"]
            c_exp = clicks_data["expected"]
            s_act = spend_data["actual"]
            c_act = clicks_data["actual"]
            
            # Check for joint severe collapse in spend & clicks with high expected baseline
            if (s_z < -cfg.robust_threshold and c_z < -cfg.robust_threshold and 
                s_exp >= cfg.min_volume_spend and c_exp >= cfg.min_volume_clicks and
                (s_act / max(s_exp, 1e-6) < 0.1) and (c_act / max(c_exp, 1e-6) < 0.1)):
                
                # If budget cap is present or joint drop indicates budget/delivery exhaustion
                extra_data = extra_metrics.get(key, {})
                if "budget_cap" in extra_data or "budget" in extra_data:
                    hard_rule_events[key] = {
                        "type": "budget_exhausted",
                        "metric": spend_data["original_metric"],
                        "actual": s_act,
                        "expected": s_exp,
                        "hard_rule": True,
                    }

    # C. Bid Strategy Change Detection
    if cfg.enable_bid_strategy_detection:
        # Check if bid_strategy is present in metrics_df or res_df
        bid_strat_present = False
        if metrics_df is not None and "bid_strategy" in metrics_df.columns:
            bid_strat_present = True
        elif "bid_strategy" in res_df.columns:
            bid_strat_present = True
            
        if bid_strat_present:
            for cmp in all_campaigns:
                cmp_rows = res_df[res_df["campaign"] == cmp].sort_values(by="_date_dt")
                unique_dates = cmp_rows["_date_dt"].unique()
                
                prev_strat = None
                for d in unique_dates:
                    d_str = date_to_str[d]
                    key = (cmp, d_str)
                    extra_data = extra_metrics.get(key, {})
                    curr_strat = extra_data.get("bid_strategy", None)
                    
                    if prev_strat is not None and curr_strat is not None and curr_strat != prev_strat:
                        # Check if any metric on this campaign-day is anomalous
                        m_dict = cmp_day_metrics.get(key, {})
                        has_anomaly = any(m["is_stat_candidate"] for m in m_dict.values())
                        if has_anomaly and key not in hard_rule_events:
                            # Pick metric with highest z-score
                            best_m = max(m_dict.values(), key=lambda x: abs(x["robust_z"]))
                            hard_rule_events[key] = {
                                "type": "bid_strategy_change",
                                "metric": best_m["original_metric"],
                                "actual": best_m["actual"],
                                "expected": best_m["expected"],
                                "hard_rule": True,
                            }
                    if curr_strat is not None:
                        prev_strat = curr_strat

    # 7. Seasonality & Peer-Based Movement Handling
    # Check if a statistical candidate anomaly across campaigns on a given date is shared peer movement
    seasonal_keys: Set[Tuple[str, str, str]] = set()

    if cfg.enable_seasonality:
        for (date_val, metric_val), group in res_df.groupby(["date", "metric"]):
            if len(group) < 2:
                continue
            
            # Compute relative deviation from expected for each campaign
            # dev = (actual - expected) / expected
            group_eligible = group[group["expected"] > 0].copy()
            if len(group_eligible) < 2:
                continue
                
            group_eligible["rel_dev"] = (group_eligible["actual"] - group_eligible["expected"]) / group_eligible["expected"]
            
            # For candidate anomalies in this group
            candidates_in_group = group_eligible[group_eligible["is_stat_candidate"]]
            
            for _, cand in candidates_in_group.iterrows():
                cand_cmp = cand["campaign"]
                cand_dev = cand["rel_dev"]
                cand_sign = np.sign(cand_dev)
                
                if cand_sign == 0:
                    continue
                    
                # Peers excluding current candidate
                peers = group_eligible[group_eligible["campaign"] != cand_cmp]
                if len(peers) == 0:
                    continue
                    
                # Find peers moving in SAME direction by at least peer_dev_threshold (8%)
                matching_peers = peers[
                    (np.sign(peers["rel_dev"]) == cand_sign) & 
                    (peers["rel_dev"].abs() >= cfg.peer_dev_threshold)
                ]
                
                peer_share = len(matching_peers) / len(peers)
                
                if peer_share >= cfg.peer_share_threshold:
                    # Estimate peer movement (median relative dev of matching peers)
                    peer_move_median = matching_peers["rel_dev"].median()
                    
                    # Remaining deviation after removing peer movement
                    adj_dev = cand_dev - peer_move_median
                    
                    # If remaining deviation is within peer_dev_threshold or significantly reduced
                    if abs(adj_dev) < cfg.peer_dev_threshold or (abs(adj_dev) < 0.5 * abs(cand_dev)):
                        seasonal_keys.add((str(cand_cmp), str(date_val), str(cand["metric"])))

    # 8. Event Aggregation and Classification Output Generation
    events: List[Dict[str, Any]] = []
    
    # Process all campaign-days
    all_cmp_days = set(cmp_day_metrics.keys()).union(set(hard_rule_events.keys()))
    
    for (cmp, d_str) in sorted(all_cmp_days):
        m_dict = cmp_day_metrics.get((cmp, d_str), {})
        hard_rule_info = hard_rule_events.get((cmp, d_str), None)
        
        selected_event = None
        
        # Priority 1: Hard Rules
        if hard_rule_info is not None:
            act_v = float(hard_rule_info["actual"])
            exp_v = float(hard_rule_info["expected"])
            delta_pct = ((act_v - exp_v) / exp_v * 100.0) if exp_v != 0.0 else 0.0
            
            # Check if seasonality applies to hard rule (usually false for hard rules)
            is_seasonal = (cmp, d_str, hard_rule_info["metric"]) in seasonal_keys
            
            selected_event = {
                "campaign": cmp,
                "date": d_str,
                "type": hard_rule_info["type"],
                "metric": hard_rule_info["metric"],
                "actual": act_v,
                "expected": exp_v,
                "delta_pct": round(delta_pct, 4),
                "hard_rule": True,
                "seasonal": is_seasonal,
            }
        else:
            # Priority 2: Statistical Confirmed Anomalies (or Seasonal Shift)
            # Find all confirmed or seasonal metrics for this campaign-day
            flagged_metrics = []
            for m_name, m_info in m_dict.items():
                orig_m = m_info["original_metric"]
                is_seasonal = (cmp, d_str, orig_m) in seasonal_keys
                is_stat = m_info["stat_confirmed"]
                
                if is_stat or is_seasonal:
                    flagged_metrics.append((m_info, is_seasonal))
                    
            if flagged_metrics:
                # Select primary metric (highest abs robust_z)
                primary_m_info, primary_is_seasonal = max(
                    flagged_metrics, key=lambda x: abs(x[0]["robust_z"])
                )
                
                act_v = float(primary_m_info["actual"])
                exp_v = float(primary_m_info["expected"])
                delta_pct = ((act_v - exp_v) / exp_v * 100.0) if exp_v != 0.0 else 0.0
                
                event_type = "seasonal_shift" if primary_is_seasonal else "other_anomaly"
                
                selected_event = {
                    "campaign": cmp,
                    "date": d_str,
                    "type": event_type,
                    "metric": primary_m_info["original_metric"],
                    "actual": act_v,
                    "expected": exp_v,
                    "delta_pct": round(delta_pct, 4),
                    "hard_rule": False,
                    "seasonal": primary_is_seasonal,
                }

        if selected_event is not None:
            events.append(selected_event)

    if not events:
        return pd.DataFrame(columns=output_columns)

    flag_df = pd.DataFrame(events)[output_columns]
    flag_df["hard_rule"] = flag_df["hard_rule"].astype(bool)
    flag_df["seasonal"] = flag_df["seasonal"].astype(bool)
    
    # Deterministic sorting by date and campaign
    flag_df = flag_df.sort_values(by=["date", "campaign", "metric"]).reset_index(drop=True)
    return flag_df


def get_freeze_feedback(flags: pd.DataFrame) -> pd.DataFrame:
    """
    Return the campaign/date information M1 needs to freeze incident days.

    Parameters:
        flags: M2 flag table DataFrame (from detect_anomalies).

    Returns:
        DataFrame containing unique ['campaign', 'date'] pairs of flagged incidents.
    """
    if not isinstance(flags, pd.DataFrame) or flags.empty:
        return pd.DataFrame(columns=["campaign", "date"])

    if "campaign" not in flags.columns or "date" not in flags.columns:
        raise ValueError("flags DataFrame must contain 'campaign' and 'date' columns")

    feedback_df = flags[["campaign", "date"]].drop_duplicates().sort_values(by=["date", "campaign"]).reset_index(drop=True)
    return feedback_df
