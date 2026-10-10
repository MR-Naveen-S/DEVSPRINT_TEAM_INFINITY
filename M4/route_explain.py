"""
Severity, Routing & Explanation Module (M3 Shared Contract Interface).
Generates plain-English explanations, first diagnostic steps, computes severity, routes alerts (immediate vs digest),
and writes output CSVs.
"""

import pandas as pd
import json
import config

EXPLANATIONS = {
    'tracking_break': (
        "Conversions fell to {actual:.0f} (expected ~{expected:.1f}) for 2 days while clicks held steady. Suspected broken conversion tracking.",
        "Check the conversion tag and landing page snippet; test a conversion in preview mode."
    ),
    'budget_exhausted': (
        "Spend dropped to ${actual:.2f} (expected ~${expected:.2f}) and clicks collapsed. Suspected budget exhaustion or cap reached.",
        "Inspect daily budget cap settings, billing status, and pacing schedule."
    ),
    'bid_strategy_change': (
        "CPA shifted to ${actual:.2f} (expected ~${expected:.2f}, {delta_pct:+.1f}%). Suspected bid strategy change.",
        "Review recent bid target adjustments, tCPA/tROAS settings, or automated bidding logs."
    ),
    'seasonal_shift': (
        "Metric {metric} shifted to {actual:.1f} (expected ~{expected:.1f}), matching peer campaign movement across the account.",
        "Monitor account-wide conversion trends and compare with historical seasonal patterns."
    ),
    'other_anomaly': (
        "Metric {metric} deviated to {actual:.1f} (expected ~{expected:.1f}, {delta_pct:+.1f}% deviation from 28-day baseline).",
        "Review campaign change history, ad creative status, and search query reports."
    )
}

def run_routing(flag_df):
    """
    Consumes flag table and produces alert payloads matching Phase 0 Contract.
    Saves outputs to alerts_all.csv, alerts_immediate.csv, digest.csv.
    """
    alerts = []
    
    for idx, row in flag_df.iterrows():
        atype = row['type']
        if atype not in EXPLANATIONS:
            atype = 'other_anomaly'
            
        tpl_exp, tpl_step = EXPLANATIONS[atype]
        
        explanation = tpl_exp.format(
            metric=row['metric'],
            actual=row['actual'],
            expected=row['expected'],
            delta_pct=row['delta_pct']
        )
        
        first_step = tpl_step
        
        # Severity assignment
        if atype in ['tracking_break', 'budget_exhausted'] or row['hard_rule']:
            severity = 'HIGH'
        elif abs(row['delta_pct']) > 50.0:
            severity = 'MEDIUM'
        else:
            severity = 'LOW'
            
        # Routing logic: HIGH pages immediately; seasonal or low/medium goes to digest
        if severity == 'HIGH' and not row['seasonal']:
            route = 'immediate'
        else:
            route = 'digest'
            
        alert_payload = {
            'campaign': row['campaign'],
            'date': row['date'],
            'type': atype,
            'severity': severity,
            'route': route,
            'metric': row['metric'],
            'actual': float(row['actual']),
            'expected': float(row['expected']),
            'delta_pct': float(row['delta_pct']),
            'baseline': f"{config.WINDOW}-day median, weekday-adjusted",
            'explanation': explanation,
            'first_step': first_step
        }
        alerts.append(alert_payload)
        
    alerts_df = pd.DataFrame(alerts)
    if alerts_df.empty:
        alerts_df = pd.DataFrame(columns=[
            'campaign', 'date', 'type', 'severity', 'route', 'metric',
            'actual', 'expected', 'delta_pct', 'baseline', 'explanation', 'first_step'
        ])
        
    immediate_df = alerts_df[alerts_df['route'] == 'immediate'].reset_index(drop=True)
    digest_df = alerts_df[alerts_df['route'] == 'digest'].reset_index(drop=True)
    
    alerts_df.to_csv(config.ALERTS_ALL_PATH, index=False)
    immediate_df.to_csv(config.ALERTS_IMMEDIATE_PATH, index=False)
    digest_df.to_csv(config.DIGEST_PATH, index=False)
    
    return alerts_df, immediate_df, digest_df
