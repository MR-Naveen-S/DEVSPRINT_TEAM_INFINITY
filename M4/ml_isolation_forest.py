"""
Optional Isolation Forest Cross-Check Module (Phase 4 Polish).
Owned by M4 (Evaluation, Tuning & Reporting Lead).
Runs an unsupervised Isolation Forest on standardized residual metrics as a secondary signal.
Kept strictly separate so it never pages alone or muddies primary statistical metrics.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import config
import baseline
import evaluate

def run_isolation_forest(data_path, incidents_path, contamination=0.05):
    """
    Runs Isolation Forest model on multi-metric robust z-scores per campaign.
    Returns comparison metrics vs statistical pipeline and seeded incidents.
    """
    raw_df = baseline.load_real(data_path)
    res_df = baseline.run_baseline(raw_df)
    incidents_df = evaluate.load_incidents(incidents_path)
    
    # Pivot residuals matrix: columns per metric robust z-score
    pivot_df = res_df.pivot(index=['campaign', 'date'], columns='metric', values='robust_z').fillna(0.0).reset_index()
    
    feature_cols = [c for c in pivot_df.columns if c not in ['campaign', 'date']]
    X = pivot_df[feature_cols].values
    
    # Train Isolation Forest
    model = IsolationForest(contamination=contamination, random_state=42)
    pivot_df['iforest_prediction'] = model.fit_predict(X)  # -1 for anomaly, 1 for normal
    pivot_df['iforest_anomaly'] = pivot_df['iforest_prediction'] == -1
    
    ml_anomalies = pivot_df[pivot_df['iforest_anomaly']]
    total_ml_anomalies = len(ml_anomalies)
    
    # Match ML predictions against seeded incidents
    valid_incidents = incidents_df[~incidents_df['type'].astype(str).str.lower().str.contains('seasonal')].copy()
    
    ml_caught = 0
    for idx, inc in valid_incidents.iterrows():
        c_norm = inc['norm_campaign']
        s_d = inc['start'].strftime('%Y-%m-%d')
        e_d = inc['end'].strftime('%Y-%m-%d')
        
        c_piv = pivot_df[pivot_df['campaign'].apply(evaluate.normalize_campaign_id) == c_norm]
        matches = c_piv[(c_piv['date'] >= s_d) & (c_piv['date'] <= e_d) & (c_piv['iforest_anomaly'])]
        if not matches.empty:
            ml_caught += 1
            
    ml_recall = (ml_caught / len(valid_incidents)) if len(valid_incidents) > 0 else 1.0
    
    summary = {
        'total_ml_anomalies': total_ml_anomalies,
        'ml_caught_incidents': ml_caught,
        'total_incidents': len(valid_incidents),
        'ml_incident_recall': float(ml_recall)
    }
    
    print(f"Isolation Forest Analysis Complete: Flagged {total_ml_anomalies} anomalies, Incident Recall = {ml_recall*100:.1f}%")
    return pivot_df, summary

if __name__ == "__main__":
    run_isolation_forest("stub_data.csv", "incidents.csv")
