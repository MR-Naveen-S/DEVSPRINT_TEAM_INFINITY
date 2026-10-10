"""
Detection & Classification Module (M2 Shared Contract Interface).
Applies z-score thresholding, persistence rules, hard rule checks, peer seasonality, and anomaly classification.
"""

import pandas as pd
import numpy as np
import config

def run_detection(residual_df):
    """
    Consumes residual table and returns Flag table DataFrame matching Phase 0 Contract:
    ['campaign', 'date', 'type', 'metric', 'actual', 'expected', 'delta_pct', 'hard_rule', 'seasonal']
    """
    flags = []
    
    # Check overall seasonality across all campaigns per date
    dates = residual_df['date'].unique()
    daily_seasonal = {}
    
    for d in dates:
        d_df = residual_df[(residual_df['date'] == d) & (residual_df['metric'] == 'conversions')]
        if len(d_df) > 0:
            up_moves = (d_df['robust_z'] > 2.5).sum()
            down_moves = (d_df['robust_z'] < -2.5).sum()
            total = len(d_df)
            if (up_moves / total >= config.PEER_SHARE) or (down_moves / total >= config.PEER_SHARE):
                daily_seasonal[d] = True
            else:
                daily_seasonal[d] = False
        else:
            daily_seasonal[d] = False

    # Process per campaign
    for campaign_id, c_df in residual_df.groupby('campaign'):
        dates_sorted = sorted(c_df['date'].unique())
        
        # Track historical z-score flags for persistence check
        z_flagged_dates = set()
        
        for i, d in enumerate(dates_sorted):
            day_residuals = c_df[c_df['date'] == d]
            
            # Check hard rules first
            conv_row = day_residuals[day_residuals['metric'] == 'conversions']
            spend_row = day_residuals[day_residuals['metric'] == 'spend']
            clicks_row = day_residuals[day_residuals['metric'] == 'clicks']
            
            is_hard_rule = False
            anomaly_type = None
            primary_metric = 'conversions'
            act_val = 0.0
            exp_val = 0.0
            
            # Hard Rule 1: Tracking Break (conversions == 0 with expected >= volume guard)
            if not conv_row.empty:
                c_act = conv_row['actual'].values[0]
                c_exp = conv_row['expected'].values[0]
                if c_act == 0 and c_exp >= config.MIN_CONVERSIONS_GUARD:
                    # Check preceding day if available
                    if i > 0:
                        prev_date = dates_sorted[i-1]
                        prev_conv = c_df[(c_df['date'] == prev_date) & (c_df['metric'] == 'conversions')]
                        if not prev_conv.empty and prev_conv['actual'].values[0] == 0:
                            is_hard_rule = True
                            anomaly_type = 'tracking_break'
                            primary_metric = 'conversions'
                            act_val = c_act
                            exp_val = c_exp
                            
            # Hard Rule 2: Budget Exhausted (spend or clicks drop sharply with high expected volume)
            if not is_hard_rule and not spend_row.empty:
                s_act = spend_row['actual'].values[0]
                s_exp = spend_row['expected'].values[0]
                s_z = spend_row['robust_z'].values[0]
                if s_z < -config.T and s_exp >= config.MIN_SPEND_GUARD:
                    if not clicks_row.empty and clicks_row['robust_z'].values[0] < -config.T:
                        is_hard_rule = True
                        anomaly_type = 'budget_exhausted'
                        primary_metric = 'spend'
                        act_val = s_act
                        exp_val = s_exp
                        
            # Evaluate statistical z-score flag
            max_z_row = day_residuals.loc[day_residuals['robust_z'].abs().idxmax()]
            max_z = max_z_row['robust_z']
            
            if abs(max_z) > config.T:
                z_flagged_dates.add(i)
                
            # Persistence rule: flag if z-score exceeded on 2 of last 3 days
            is_persistent = False
            recent_flags = [idx for idx in [i, i-1, i-2] if idx in z_flagged_dates]
            if len(recent_flags) >= 2:
                is_persistent = True
                
            # If hard rule or persistent flag, create alert entry
            if is_hard_rule or is_persistent:
                if not is_hard_rule:
                    primary_metric = max_z_row['metric']
                    act_val = max_z_row['actual']
                    exp_val = max_z_row['expected']
                    
                    if primary_metric == 'cpa':
                        anomaly_type = 'bid_strategy_change'
                    elif daily_seasonal.get(d, False):
                        anomaly_type = 'seasonal_shift'
                    else:
                        anomaly_type = 'other_anomaly'
                        
                delta_pct = ((act_val - exp_val) / exp_val * 100.0) if exp_val > 0 else 0.0
                is_seasonal = (anomaly_type == 'seasonal_shift') or daily_seasonal.get(d, False)
                
                flags.append({
                    'campaign': campaign_id,
                    'date': d,
                    'type': anomaly_type,
                    'metric': primary_metric,
                    'actual': float(act_val),
                    'expected': float(exp_val),
                    'delta_pct': float(delta_pct),
                    'hard_rule': is_hard_rule,
                    'seasonal': is_seasonal
                })
                
    return pd.DataFrame(flags)
