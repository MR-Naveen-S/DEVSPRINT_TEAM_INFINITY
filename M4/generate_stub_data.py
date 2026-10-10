"""
Generates synthetic stub data for testing Phase 1 pipeline.
"""

import pandas as pd
import numpy as np

def generate_stub():
    np.random.seed(42)
    dates = pd.date_range(start="2026-03-01", periods=35, freq="D").strftime("%Y-%m-%d")
    campaigns = ["CMP-001", "CMP-002", "CMP-003", "CMP-004", "CMP-005"]
    
    rows = []
    for c in campaigns:
        base_spend = 100.0 if c != "CMP-004" else 500.0
        base_clicks = 200 if c != "CMP-004" else 1000
        base_conv = 20 if c != "CMP-004" else 100
        
        for d in dates:
            spend = base_spend + np.random.normal(0, 5.0)
            clicks = int(base_clicks + np.random.normal(0, 10.0))
            conv = int(base_conv + np.random.normal(0, 2.0))
            
            # Inject seeded incidents matching incidents.csv
            if c == "CMP-001" and "2026-03-15" <= d <= "2026-03-20":
                # Tracking break: conversions drop to 0 while spend/clicks normal
                conv = 0
            elif c == "CMP-002" and "2026-03-22" <= d <= "2026-03-25":
                # Budget exhausted: spend & clicks collapse
                spend = 5.0
                clicks = 10
                conv = 0
            elif c == "CMP-003" and "2026-03-10" <= d <= "2026-03-14":
                # Bid strategy change: CPA spikes
                spend = base_spend * 2.5
                clicks = base_clicks
                conv = 5
            elif d >= "2026-03-28":
                # Seasonal shift across campaigns
                conv = int(base_conv * 1.5)
                
            rows.append({
                'date': d,
                'campaign': c,
                'spend': max(0.0, round(spend, 2)),
                'clicks': max(0, clicks),
                'conversions': max(0, conv),
                'bid_strategy': 'tCPA'
            })
            
    df = pd.DataFrame(rows)
    df.to_csv("stub_data.csv", index=False)
    print("Generated stub_data.csv successfully!")

if __name__ == "__main__":
    generate_stub()
