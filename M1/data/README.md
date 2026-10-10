# M1 Synthetic Datasets & Stub Catalogue

This directory contains reproducible synthetic datasets created for testing and benchmarking the M1 data & baseline pipeline without external dependencies.

## Datasets

### 1. `synthetic_campaign_stub.csv`
- **Purpose:** Minimal lightweight stub dataset for rapid local testing and development across M1–M4.
- **Scope:** 3 campaigns (Large, Medium, Small) $\times$ 30 days (90 rows).
- **Seeded Event:** Broken conversion tracking on campaign `C01` on day `2026-01-15`.
- **Columns:** `date`, `campaign_id`, `campaign_name`, `spend`, `impressions`, `clicks`, `conversions`, `revenue`, `bid_strategy`.

### 2. `synthetic_campaign_metrics.csv`
- **Purpose:** Full synthetic benchmark dataset replicating the 20-campaign portfolio dynamics.
- **Scope:** 20 campaigns (6 Large, 8 Medium, 6 Small) $\times$ 180 days (3,600 rows).
- **Features:** Day-of-week seasonality (weekend dips), lognormal noise, realistic CTR/CVR/AOV profiles across budget tiers.

## Reproducibility
Generated via `M1.baseline.generate_synthetic_stub_data()` with deterministic random seed `42`.
