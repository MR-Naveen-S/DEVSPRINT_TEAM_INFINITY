"""
Per-Campaign Plot Generator Module (Phase 4 Polish).
Owned by M4 (Evaluation, Tuning & Reporting Lead).
Visualizes actual metrics, baseline median, tolerance bands, flagged anomaly points, and seeded incident windows.
"""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
import config
import baseline
import detect
import evaluate

def generate_campaign_plots(data_path, incidents_path, output_filename="campaign_plots.png"):
    """
    Generates multi-panel time-series visualization for campaigns.
    Shows actual values, baseline median, baseline band, flagged days, and incident windows.
    """
    raw_df = baseline.load_real(data_path)
    res_df = baseline.run_baseline(raw_df)
    flag_df = detect.run_detection(res_df)
    incidents_df = evaluate.load_incidents(incidents_path)
    
    # Filter unique campaigns to plot (top 4 or all)
    campaigns = raw_df['campaign'].unique()[:4]
    
    fig, axes = plt.subplots(len(campaigns), 1, figsize=(14, 3.5 * len(campaigns)), sharex=False)
    if len(campaigns) == 1:
        axes = [axes]
        
    for i, c_id in enumerate(campaigns):
        ax = axes[i]
        c_raw = raw_df[raw_df['campaign'] == c_id].sort_values('date').reset_index(drop=True)
        c_res = res_df[(res_df['campaign'] == c_id) & (res_df['metric'] == 'conversions')].sort_values('date').reset_index(drop=True)
        c_flags = flag_df[flag_df['campaign'] == c_id]
        
        dates = pd.to_datetime(c_raw['date'])
        actuals = c_raw['conversions'].values
        
        # Extract expected & band
        if not c_res.empty:
            expected = c_res['expected'].values
            mad = c_res['mad'].values
            n_floor = c_res['noise_floor'].values
            band = np.maximum(config.T * mad, n_floor)
            upper_band = expected + band
            lower_band = np.maximum(0, expected - band)
        else:
            expected = actuals
            upper_band = actuals * 1.3
            lower_band = actuals * 0.7
            
        # Plot actual metric
        ax.plot(dates, actuals, label='Actual Conversions', color='#1f77b4', lw=2.0)
        
        # Plot baseline median & confidence band
        ax.plot(dates, expected, label=f'Baseline ({config.WINDOW}d Median)', color='#ff7f0e', linestyle='--', lw=1.5)
        ax.fill_between(dates, lower_band, upper_band, color='#ff7f0e', alpha=0.15, label=f'Tolerance Band (T={config.T})')
        
        # Shade seeded incident windows
        c_norm = evaluate.normalize_campaign_id(c_id)
        c_incidents = incidents_df[incidents_df['norm_campaign'] == c_norm]
        for _, inc in c_incidents.iterrows():
            ax.axvspan(inc['start'], inc['end'], color='#d62728', alpha=0.2, label=f"Seeded Incident ({inc['type']})")
            
        # Mark flagged anomaly days
        if not c_flags.empty:
            flag_dates = pd.to_datetime(c_flags['date'])
            flag_actuals = c_flags['actual']
            ax.scatter(flag_dates, flag_actuals, color='#d62728', s=70, zorder=5, label='Flagged Anomaly', marker='o')
            
        ax.set_title(f"Campaign: {c_id} - Conversion Metrics & Baseline Band", fontsize=12, fontweight='bold')
        ax.set_ylabel("Conversions", fontsize=10)
        ax.grid(True, linestyle=':', alpha=0.6)
        
        # Remove duplicate legend handles
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), loc='upper left', fontsize=8)
        
    plt.xlabel("Date", fontsize=10)
    plt.tight_layout()
    plt.savefig(output_filename, dpi=150)
    plt.close()
    
    print(f"Generated per-campaign plot saved to: {output_filename}")
    return output_filename

if __name__ == "__main__":
    generate_campaign_plots("stub_data.csv", "incidents.csv")
