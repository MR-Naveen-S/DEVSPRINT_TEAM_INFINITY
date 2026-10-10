# M3 Reporting Support: Severity & Routing

## 1. Totals Split: Immediate Pages vs Daily Digest

| Stream Category | Alert Count | Share of Total | Description |
|---|---|---|---|
| **Immediate Pages** | 2 | 40.0% | High-priority urgent notifications sent directly to ops |
| **Daily Digest Items** | 3 | 60.0% | Consolidated daily summary stream for non-paged anomalies |
| **Total Monitored Events** | 5 | 100.0% | Complete set of evaluated anomaly flags |

---

## 2. Representative Example Alerts

### Example 1: Broken Conversion Tracking (Immediate Page)
```json
{
  "campaign": "CMP-001",
  "date": "2026-03-01",
  "type": "tracking_break",
  "type_label": "Broken Conversion Tracking",
  "severity": "HIGH",
  "severity_score": 0.5,
  "route": "immediate",
  "metric": "conversions",
  "metric_label": "Conversions",
  "actual": 0.0,
  "actual_formatted": "0",
  "expected": 15.2,
  "expected_formatted": "15.2",
  "delta_pct": -100.0,
  "baseline": "28-Day Historical Baseline (Day-of-Week Adjusted)",
  "explanation": "Conversions dropped sharply to 0 (expected ~15.2, -100.0%) against the 28-Day Historical Baseline (Day-of-Week Adjusted), despite clicks and spend remaining normal. This strongly indicates a broken conversion tag or tracking snippet failure.",
  "first_step": "Inspect the conversion tracking pixel on the landing page; test a test conversion in Tag Manager / Preview Mode to ensure event firing."
}
```

### Example 2: Early Budget Depletion (Immediate Page)
```json
{
  "campaign": "CMP-004",
  "date": "2026-03-02",
  "type": "budget_exhausted",
  "type_label": "Early Budget Depletion",
  "severity": "HIGH",
  "severity_score": 0.3375,
  "route": "immediate",
  "metric": "spend",
  "metric_label": "Ad Spend ($)",
  "actual": 450.0,
  "actual_formatted": "$450.00",
  "expected": 1200.0,
  "expected_formatted": "$1,200.00",
  "delta_pct": -62.5,
  "baseline": "28-Day Historical Baseline (Day-of-Week Adjusted)",
  "explanation": "Ad Spend ($) dropped to $450.00 (expected ~$1,200.00, -62.5%) compared to the 28-Day Historical Baseline (Day-of-Week Adjusted), while audience search demand remained high. This suggests the daily campaign budget cap was exhausted prematurely.",
  "first_step": "Review daily campaign spend caps, budget pacing settings, and active ad delivery schedule."
}
```

### Example 3: Market Seasonal Shift (Daily Digest Stream)
```json
{
  "campaign": "CMP-010",
  "date": "2026-03-04",
  "type": "seasonal_shift",
  "type_label": "Market Seasonal Pattern",
  "severity": "LOW",
  "severity_score": 0.0407,
  "route": "digest",
  "metric": "clicks",
  "metric_label": "Total Clicks",
  "actual": 820.0,
  "actual_formatted": "820",
  "expected": 1100.0,
  "expected_formatted": "1,100",
  "delta_pct": -25.5,
  "baseline": "28-Day Historical Baseline (Day-of-Week Adjusted)",
  "explanation": "Total Clicks moved to 820 (expected ~1,100, -25.5%), matching broader category-wide peer movement over the 28-Day Historical Baseline (Day-of-Week Adjusted). Classified as expected seasonal market variance.",
  "first_step": "Cross-reference category benchmarks, holiday promotional schedules, and peer campaign trends."
}
```

### Example 4: Bidding Strategy Shift / Unusual Variance (Daily Digest Stream)
```json
{
  "campaign": "CMP-007",
  "date": "2026-03-03",
  "type": "bid_strategy_change",
  "type_label": "Bidding Strategy Shift",
  "severity": "LOW",
  "severity_score": 0.1464,
  "route": "digest",
  "metric": "cpa",
  "metric_label": "Cost Per Acquisition (CPA)",
  "actual": 45.0,
  "actual_formatted": "$45.00",
  "expected": 22.0,
  "expected_formatted": "$22.00",
  "delta_pct": 104.5,
  "baseline": "28-Day Historical Baseline (Day-of-Week Adjusted)",
  "explanation": "Cost Per Acquisition (CPA) shifted to $45.00 compared to expected ~$22.00 (+104.5%) following a detected bidding strategy or target CPA/ROAS adjustment against the 28-Day Historical Baseline (Day-of-Week Adjusted).",
  "first_step": "Check campaign change history in your ad manager to confirm recent target CPA/ROAS or bidding strategy modifications."
}
```

---

## 3. Severity and Routing Method Paragraph

Severity scoring and alert routing are designed to eliminate alert fatigue by enforcing strict prioritization based on financial impact and urgency. Each detected anomaly is assigned a severity score calculated as the product of the alert type's critical weight (ranging from 1.0 for tracking breaks down to 0.2 for seasonal shifts), the metric's relative deviation from baseline expectations, and the campaign's spend share within the total account portfolio. Alerts exceeding the HIGH severity threshold (>= 0.30) are routed immediately to the operational team as real-time pages, accompanied by a plain-English narrative and a specific first diagnostic step. To safeguard operators against noise, all market-wide peer seasonal shifts—regardless of deviation magnitude—as well as lower-severity anomalies (MEDIUM and LOW), are automatically routed into a unified daily digest stream, ensuring complete historical auditability without interrupting active workflows.
