"""
M1 Configuration and Hyperparameters for PS-04 Campaign Anomaly Alerting
=========================================================================
Central configuration for M1 data loading, metric derivation, baseline calculation,
noise floors, and incident freezing.
"""

from typing import Dict, List, Set

# Default Baseline Hyperparameters
DEFAULT_WINDOW_DAYS: int = 28
ALLOWED_WINDOW_DAYS: List[int] = [21, 28, 35]
DEFAULT_FREEZE_DAYS: int = 14
DEFAULT_T_MULTIPLIER: float = 3.0
MAD_SCALE_FACTOR: float = 1.4826  # Normal consistency factor: 1 / norm.ppf(0.75) ≈ 1.4826

# Small Campaign Volume Thresholds for Weekly Aggregation
SMALL_CAMPAIGN_DAILY_SPEND_THRESHOLD: float = 300.0  # Daily spend < $300 treated as small tier
SMALL_CAMPAIGN_CONV_THRESHOLD: float = 5.0          # Daily conv < 5

# Canonical Columns Schema
CANONICAL_COLUMNS = {
    "day": "day",
    "campaign_id": "campaign_id",
    "campaign_name": "campaign_name",
    "cost": "cost",
    "conv": "conv",
    "impressions": "impressions",
    "clicks": "clicks",
    "revenue": "revenue",
    "bid_strategy": "bid_strategy",
}

# Required columns for successful baseline generation
REQUIRED_CANONICAL_FIELDS: Set[str] = {
    "day",
    "campaign_id",
    "cost",
    "conv",
    "impressions",
    "clicks",
}

# Non-negative numerical fields
NON_NEGATIVE_METRICS: List[str] = [
    "cost",
    "conv",
    "impressions",
    "clicks",
    "revenue",
]

# Alias Dictionary: Normalized (lowercase, stripped, no punctuation) -> Canonical Field
ALIAS_MAP: Dict[str, str] = {
    # Day / Date
    "day": "day",
    "date": "day",
    "event_date": "day",
    "report_date": "day",
    "timestamp": "day",
    "dt": "day",
    "day_date": "day",
    # Campaign ID
    "campaign_id": "campaign_id",
    "campaignid": "campaign_id",
    "cid": "campaign_id",
    "campaign_key": "campaign_id",
    "id": "campaign_id",
    # Campaign Name
    "campaign_name": "campaign_name",
    "campaignname": "campaign_name",
    "campaign": "campaign_name",  # If only 'campaign' is present, can serve as name or id fallback
    "name": "campaign_name",
    "campaign_title": "campaign_name",
    # Cost / Spend
    "cost": "cost",
    "spend": "cost",
    "daily_spend": "cost",
    "ad_spend": "cost",
    "expenditure": "cost",
    "amount_spent": "cost",
    # Conversions
    "conv": "conv",
    "conversions": "conv",
    "conversion": "conv",
    "total_conv": "conv",
    "leads": "conv",
    "orders": "conv",
    "purchases": "conv",
    # Impressions
    "impressions": "impressions",
    "impression": "impressions",
    "imp": "impressions",
    "impr": "impressions",
    "imprs": "impressions",
    "views": "impressions",
    # Clicks
    "clicks": "clicks",
    "click": "clicks",
    "clks": "clicks",
    # Revenue
    "revenue": "revenue",
    "rev": "revenue",
    "sales": "revenue",
    "conversion_value": "revenue",
    "conv_value": "revenue",
    "value": "revenue",
    # Bid Strategy
    "bid_strategy": "bid_strategy",
    "bidding_strategy": "bid_strategy",
    "strategy": "bid_strategy",
    "bidding_type": "bid_strategy",
    # Metadata attributes
    "channel": "channel",
    "platform": "channel",
    "vertical": "vertical",
    "industry": "vertical",
    "landing_page_group": "landing_page_group",
    "lp_group": "landing_page_group",
}

# Tracking Metrics for Baseline & Residual Generation
BASELINE_METRICS: List[str] = [
    "cost",
    "impressions",
    "clicks",
    "conv",
    "revenue",
    "ctr",
    "cvr",
    "cpa",
]

# Units and descriptions for uncertainty floors
FLOOR_DOCUMENTATION = {
    "conv": "Poisson standard error floor: sqrt(max(expected_conv, 1.0)) in conversion count units.",
    "clicks": "Poisson standard error floor: sqrt(max(expected_clicks, 1.0)) in click count units.",
    "impressions": "Poisson standard error floor: sqrt(max(expected_imp, 100.0)) in impression count units.",
    "cost": "Conservative minimum spend fluctuation floor: max(0.05 * expected_cost, $5.00) in USD currency units.",
    "revenue": "Conservative revenue fluctuation floor: max(0.08 * expected_revenue, $10.00) in USD currency units.",
    "cvr": "Binomial proportion standard error floor: sqrt(p * (1 - p) / max(N_clicks, 10)) in rate units [0, 1].",
    "ctr": "Binomial proportion standard error floor: sqrt(p * (1 - p) / max(N_impressions, 100)) in rate units [0, 1].",
    "cpa": "Cost-per-acquisition noise floor: max(0.12 * expected_cpa, $3.00) in USD per conversion.",
}
