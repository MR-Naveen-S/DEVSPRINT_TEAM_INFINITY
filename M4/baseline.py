"""
Data Loading & Baseline Computation Module (M1 Shared Contract Interface).
Calculates rolling 28-day median baselines, MAD, noise floors, and robust Z-scores.
"""

import pandas as pd
import numpy as np
import config

def load_real(filepath):
    """
    Loads raw campaign data, maps column aliases, and performs input validation.
    """
    df = pd.read_csv(filepath)
    
    # Alias mapping
    alias_map = {
        'campaign_id': 'campaign',
        'campaign_name': 'campaign_name',
        'cost': 'spend',
        'conv': 'conversions',
        'day': 'date'
    }
    df = df.rename(columns={k: v for k, v in alias_map.items() if k in df.columns})
    
    # Standardize campaign column name
    if 'campaign' not in df.columns and 'campaign_id' in df.columns:
        df['campaign'] = df['campaign_id']
        
    required = ['date', 'campaign', 'spend', 'clicks', 'conversions']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in dataset: {missing}")
        
    # Convert date format
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    
    # Check duplicate campaign-days
    dups = df.duplicated(subset=['campaign', 'date']).sum()
    if dups > 0:
        raise ValueError(f"Dataset contains {dups} duplicate campaign-day rows")
        
    # Check negative values
    for col in ['spend', 'clicks', 'conversions']:
        if (df[col] < 0).any():
            raise ValueError(f"Dataset contains negative values in column '{col}'")
            
    # Derived metrics
    df['cpa'] = np.where(df['conversions'] > 0, df['spend'] / df['conversions'], 0.0)
    if 'impressions' in df.columns:
        df['ctr'] = np.where(df['impressions'] > 0, df['clicks'] / df['impressions'], 0.0)
    else:
        df['ctr'] = 0.0
    df['cvr'] = np.where(df['clicks'] > 0, df['conversions'] / df['clicks'], 0.0)
    
    return df.sort_values(by=['campaign', 'date']).reset_index(drop=True)

def run_baseline(filepath_or_df):
    """
    Computes residual table for metrics (spend, clicks, conversions, cpa, cvr).
    Returns DataFrame matching Phase 0 Contract:
    ['campaign', 'date', 'metric', 'actual', 'expected', 'mad', 'noise_floor', 'robust_z', 'frozen_flag']
    """
    if isinstance(filepath_or_df, str):
        df = load_real(filepath_or_df)
    else:
        df = filepath_or_df.copy()
        
    metrics = ['conversions', 'spend', 'clicks', 'cpa', 'cvr']
    residuals = []
    
    for campaign_id, c_df in df.groupby('campaign'):
        c_df = c_df.sort_values('date').reset_index(drop=True)
        dates = c_df['date'].values
        
        for m in metrics:
            vals = c_df[m].values
            n = len(vals)
            
            for i in range(n):
                # Shifted 1 day: lookback window is [max(0, i - config.WINDOW) : i]
                start_idx = max(0, i - config.WINDOW)
                end_idx = i
                
                if end_idx - start_idx < 3:
                    # Not enough history
                    exp = vals[i]
                    mad = 1.0
                    n_floor = 1.0
                    z = 0.0
                else:
                    hist = vals[start_idx:end_idx]
                    exp = float(np.median(hist))
                    dev = np.abs(hist - exp)
                    mad = float(np.median(dev) * 1.4826)
                    if mad < 1e-5:
                        mad = 0.1
                        
                    # Calculate noise floor
                    if m in ['conversions', 'clicks']:
                        n_floor = float(np.sqrt(max(1.0, exp)))
                    elif m == 'cvr':
                        n_floor = 0.01
                    else:
                        n_floor = 0.05 * max(1.0, exp)
                        
                    denom = max(mad, n_floor)
                    z = float((vals[i] - exp) / denom)
                    
                residuals.append({
                    'campaign': campaign_id,
                    'date': dates[i],
                    'metric': m,
                    'actual': float(vals[i]),
                    'expected': float(exp),
                    'mad': float(mad),
                    'noise_floor': float(n_floor),
                    'robust_z': float(z),
                    'frozen_flag': False
                })
                
    return pd.DataFrame(residuals)
