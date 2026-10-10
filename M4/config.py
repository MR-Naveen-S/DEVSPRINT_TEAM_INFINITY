"""
Configuration module for Campaign Anomaly Alerting.
Owned by M4 (Evaluation, Tuning & Reporting Lead).
Frozen values after Phase 2 Tuning.
"""

# Threshold z-score for anomaly detection (frozen from flat sweep region)
T = 4.5

# Rolling baseline window in days
WINDOW = 28

# Incident freeze duration in days
FREEZE_DAYS = 14

# Seasonality thresholds
PEER_DEV = 0.08      # 8% threshold for peer campaign movement
PEER_SHARE = 0.40    # 40% of campaigns moving in same direction

# Volume guards for small campaign protection
MIN_CONVERSIONS_GUARD = 5.0
MIN_CLICKS_GUARD = 20.0
MIN_SPEND_GUARD = 10.0

# Output file paths
ALERTS_ALL_PATH = "alerts_all.csv"
ALERTS_IMMEDIATE_PATH = "alerts_immediate.csv"
DIGEST_PATH = "digest.csv"
