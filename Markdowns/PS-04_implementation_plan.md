# PS-04: Campaign Anomaly Alerting Without Alert Fatigue, Implementation Plan

## 1. Goal

Build an alerting system over daily campaign metrics that flags genuine anomalies and stays quiet otherwise. Every alert carries a plain-English explanation, and the submission reports its own precision and recall against the seeded incidents, including the misses.

## 2. Approach at a glance

| Component | What it does |
|---|---|
| Per-campaign baseline | Rolling 28-day median per campaign and metric, with a day-of-week adjustment, computed on data shifted by one day so today never sits in its own baseline |
| Robust volatility | Median absolute deviation (MAD) per campaign and metric, so past incidents do not inflate the band |
| Noise floor | Poisson floor for counts and binomial floor for CVR, so small campaigns need proportionally larger swings to alert |
| Incident freeze | Flagged days are excluded from the baseline for up to 14 days, so a slow incident cannot become the new normal |
| Persistence | Alert only when a day is flagged on 2 of the last 3 days, unless a hard rule fires |
| Hard rules | Immediate alerts for conversion tracking breaks and budget exhaustion, guarded by volume so zero is never mistaken for noise |
| Classification | Tracking break, budget exhausted, bid strategy change, seasonal shift, or other anomaly |
| Seasonality check | A day is labeled seasonal when at least 40% of campaigns move the same way by more than 8% and the campaign returns to range after removing that market move |
| Severity and routing | Score from alert type, size of deviation and campaign spend share; HIGH pages immediately, everything else goes to the digest |
| Explanations | Each alert type has its own plain-English message, with the metric, actual value, expected value, and the baseline it was compared against |
| Evaluation | Recall, precision (overall and for pages only), false positives per month, detection lag, and a threshold sweep |

## 3. Data

**Input:** 180 days of daily metrics across roughly 20 campaigns.

**Required columns:** `date`, `campaign`, `spend`, `clicks`, `conversions`. Optional extras can be added later as metrics.

**Column mapping:** `load_real()` already accepts common aliases (`campaign_id`, `campaign_name`, `cost`, `conv`, `day`). Check the real file's headers against them and add any missing mappings.

**Incident file (`incidents.csv`):** one row per seeded incident with `campaign`, `start`, `end`, and `type`. Use the types `tracking_break`, `budget_exhausted`, and `bid_strategy_change`. Mark the seasonal shift as `seasonal`; it is excluded from scoring.

## 4. Implementation steps

### Phase 1: Baseline run (about 30 minutes)

1. Confirm the Python environment has `pandas` and `numpy`. Install with `pip install pandas numpy --break-system-packages` if needed.
2. Place the real data and incident file in the project folder.
3. Run the script:
   ```
   python anomaly_alerting.py data.csv incidents.csv
   ```
4. Check the output files: `alerts_all.csv`, `alerts_immediate.csv`, `digest.csv`.
5. Confirm that every alert has a plain-English message and a first diagnostic step. This already meets the minimum complete submission.

### Phase 2: Tuning on real data (about 45 minutes)

1. Read the threshold sweep printed by the script (T = 3 to 6). Choose the T that gives the best precision while keeping recall at 100%, or as close to it as possible.
2. Set the chosen value as `T` in the script and re-run.
3. For each seeded incident, record: caught or missed, detection lag in days, and the alert type assigned.
4. For each alert that does not match a seeded incident, decide whether it is a true false positive or an unseeded real anomaly. Note the reasoning.
5. Confirm the seasonal shift is routed to the digest as `seasonal_shift`. If it is not, adjust `PEER_DEV` (default 0.08) or `PEER_SHARE` (default 0.40).
6. Check the message text on a few alerts of each type. Make sure the numbers quoted match the source data.

### Phase 3: Reporting (about 30 minutes)

Write the submission covering these points:

1. **Headline numbers:** total alerts fired over the 180 days, split into immediate pages and digest items.
2. **Precision and recall:** overall, and for immediate pages only. Include false-positive pages per month.
3. **Missed incidents:** list each one with the most likely reason. Low volume making the signal statistically thin is an acceptable and honest reason.
4. **Method:** per-campaign robust baseline, noise floor for small campaigns, persistence rule, incident freeze, peer-adjusted seasonality, severity routing.
5. **Before and after:** the alert count from a naive fixed-threshold rule compared with the final alert count. This shows the alert-fatigue improvement directly.
6. **Limitations:** very small campaigns on conversions, gradual drift that the baseline absorbs before the freeze engages, and seasonality detected only through peer behaviour rather than year-over-year history.

### Phase 4: Optional polish (if time remains)

- Send the digest as one daily summary message instead of individual items.
- Plot each flagged campaign: metric, baseline band, and the flagged day.
- Add a weekly aggregate view for the smallest campaigns, where daily counts are too sparse.

## 5. Acceptance checklist

- [ ] Script runs end-to-end on the real data without errors
- [ ] Every alert has a plain-English explanation and a first diagnostic step
- [ ] Total alert count is reported
- [ ] Precision and recall are computed against the seeded incidents
- [ ] Missed incidents are listed with reasons
- [ ] Seasonal shift is routed to the digest, not paged
- [ ] Before/after alert count is included
- [ ] Limitations are stated honestly

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Column names differ from the aliases | Map them in `load_real()` before running anything else |
| Incidents are gradual rather than sudden | Report the detection lag; the freeze and persistence rules may delay detection, which is worth stating |
| Too few conversions for reliable conversion-based alerts | Rely on the zero-run rule and state the limitation |
| Seasonal shift confused with a real incident | Check the peer-share calculation and the residual z-score; adjust `PEER_DEV` and `PEER_SHARE` |
| Tuning T overfits to the seeded incidents | Prefer a T in the flat region of the sweep rather than the single best value |

## 7. Deliverables

- `anomaly_alerting.py`: the detection and evaluation script
- `alerts_all.csv`, `alerts_immediate.csv`, `digest.csv`: alert outputs
- `incidents.csv`: the seeded incident list used for evaluation
- Submission write-up covering Phase 3 points
