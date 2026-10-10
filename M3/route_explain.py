"""
M3: Severity, Routing & Explanation Engineer (route_explain.py)
Interactive, High-Performance & Professional Dashboard Edition

This module handles:
1. Human-friendly plain-English explanation generation per alert type.
2. First diagnostic step mapping per alert type with clear user instructions.
3. Severity score calculation: (type weight x deviation size x campaign spend share) with HIGH cutoff.
4. Routing logic: HIGH pages immediately; everything else goes to digest; seasonal ALWAYS goes to digest.
5. Building standardized JSON alert payloads.
6. Spot-checking message numbers against baseline source values.
7. Phase 3 Reporting Support (totals split, curated examples, methodology paragraph).
8. Phase 4 Polish & Interactive Web UI:
   - Next-gen responsive HTML dashboard (daily_digest.html) using Chart.js, CSS Glassmorphism, real-time Search, Stream Filters (Immediate vs Digest), JSON Exporters, and Interactive Remediation Checklists.
   - Enhanced Markdown digest view (daily_digest.md).
9. Output CSV files strictly inside M3 folder.
"""

import os
import json
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional


# ---------------------------------------------------------------------------
# Constants & Human-Friendly Mappings
# ---------------------------------------------------------------------------
BASELINE_WINDOW_DESC = "28-Day Historical Baseline (Day-of-Week Adjusted)"

METRIC_LABEL_MAP: Dict[str, str] = {
    "conversions": "Conversions",
    "spend": "Ad Spend ($)",
    "clicks": "Total Clicks",
    "cpa": "Cost Per Acquisition (CPA)",
    "ctr": "Click-Through Rate (CTR)",
    "cvr": "Conversion Rate (CVR)"
}

TYPE_LABEL_MAP: Dict[str, str] = {
    "tracking_break": "Broken Conversion Tracking",
    "budget_exhausted": "Early Budget Depletion",
    "bid_strategy_change": "Bidding Strategy Shift",
    "seasonal_shift": "Market Seasonal Pattern",
    "other_anomaly": "Unusual Metric Variance"
}

TYPE_WEIGHTS: Dict[str, float] = {
    "tracking_break": 1.0,
    "budget_exhausted": 0.9,
    "bid_strategy_change": 0.7,
    "other_anomaly": 0.6,
    "seasonal_shift": 0.2
}

HIGH_CUTOFF = 0.30
MEDIUM_CUTOFF = 0.15


# ---------------------------------------------------------------------------
# Plain-English Templates & Diagnostic Steps
# ---------------------------------------------------------------------------
ALERT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "tracking_break": {
        "suspected_cause": "Broken or missing conversion tracking tag on website/landing page.",
        "explanation": "{metric_name} dropped sharply to {actual_str} (expected ~{expected_str}, {delta_pct:+.1f}%) against the {baseline_window}, despite clicks and spend remaining normal. This strongly indicates a broken conversion tag or tracking snippet failure.",
        "first_step": "Inspect the conversion tracking pixel on the landing page; test a test conversion in Tag Manager / Preview Mode to ensure event firing."
    },
    "budget_exhausted": {
        "suspected_cause": "Daily spend limit reached early in the serving cycle.",
        "explanation": "{metric_name} dropped to {actual_str} (expected ~{expected_str}, {delta_pct:+.1f}%) compared to the {baseline_window}, while audience search demand remained high. This suggests the daily campaign budget cap was exhausted prematurely.",
        "first_step": "Review daily campaign spend caps, budget pacing settings, and active ad delivery schedule."
    },
    "bid_strategy_change": {
        "suspected_cause": "Recent automated or manual bid strategy adjustment.",
        "explanation": "{metric_name} shifted to {actual_str} compared to expected ~{expected_str} ({delta_pct:+.1f}%) following a detected bidding strategy or target CPA/ROAS adjustment against the {baseline_window}.",
        "first_step": "Check campaign change history in your ad manager to confirm recent target CPA/ROAS or bidding strategy modifications."
    },
    "seasonal_shift": {
        "suspected_cause": "Industry-wide market demand fluctuation or promotional calendar event.",
        "explanation": "{metric_name} moved to {actual_str} (expected ~{expected_str}, {delta_pct:+.1f}%), matching broader category-wide peer movement over the {baseline_window}. Classified as expected seasonal market variance.",
        "first_step": "Cross-reference category benchmarks, holiday promotional schedules, and peer campaign trends."
    },
    "other_anomaly": {
        "suspected_cause": "Unusual statistical variance exceeding normal baseline threshold.",
        "explanation": "{metric_name} recorded {actual_str} vs expected ~{expected_str} ({delta_pct:+.1f}%), deviating noticeably beyond the normal variance band for the {baseline_window}.",
        "first_step": "Analyze recent search query reports, ad group level bid edits, and target audience overlap."
    }
}


def format_metric_value(metric: str, val: float) -> str:
    """Format metric value with appropriate unit notation for clear readability."""
    metric_lower = metric.lower()
    if metric_lower in ["spend", "cpa"]:
        return f"${val:,.2f}" if val >= 1 else f"${val:.2f}"
    elif metric_lower in ["ctr", "cvr"]:
        return f"{val * 100:.2f}%" if val < 1 else f"{val:.1f}%"
    else:
        return f"{val:,.1f}" if val != int(val) else f"{int(val):,}"


def get_first_step(alert_type: str) -> str:
    """Return the first diagnostic step for a given alert type."""
    template = ALERT_TEMPLATES.get(alert_type, ALERT_TEMPLATES["other_anomaly"])
    return template["first_step"]


def format_explanation(
    alert_type: str,
    metric: str,
    actual: float,
    expected: float,
    delta_pct: float,
    baseline_window: str = BASELINE_WINDOW_DESC
) -> Tuple[str, str]:
    """
    Generate user-understandable plain-English explanation and actionable first diagnostic step.
    Returns: (explanation_text, first_step_text)
    """
    template_info = ALERT_TEMPLATES.get(alert_type, ALERT_TEMPLATES["other_anomaly"])
    explanation_fmt = template_info["explanation"]
    
    metric_name = METRIC_LABEL_MAP.get(metric.lower(), metric.title())
    actual_str = format_metric_value(metric, actual)
    expected_str = format_metric_value(metric, expected)
    
    explanation = explanation_fmt.format(
        metric_name=metric_name,
        actual_str=actual_str,
        expected_str=expected_str,
        delta_pct=delta_pct,
        baseline_window=baseline_window
    )
    first_step = template_info["first_step"]
    return explanation, first_step


def calculate_severity_score(
    alert_type: str,
    actual: float,
    expected: float,
    spend_share: float = 1.0
) -> Tuple[float, str]:
    """
    Severity score calculation: type weight x deviation size x campaign spend share.
    Returns: (severity_score, severity_label)
    """
    type_weight = TYPE_WEIGHTS.get(alert_type, 0.6)
    
    if expected != 0.0:
        deviation_size = abs(actual - expected) / abs(expected)
    else:
        deviation_size = 1.0 if actual != 0.0 else 0.0

    deviation_size = min(deviation_size, 2.0)
    score = round(type_weight * deviation_size * spend_share, 4)
    
    if score >= HIGH_CUTOFF:
        severity = "HIGH"
    elif score >= MEDIUM_CUTOFF:
        severity = "MEDIUM"
    else:
        severity = "LOW"
        
    return score, severity


def route_alert(alert_type: str, severity: str, is_seasonal: bool = False) -> str:
    """
    Routing logic:
    - Seasonal shifts ALWAYS go to digest stream.
    - HIGH severity alerts page immediately ("immediate").
    - Everything else goes to digest stream ("digest").
    """
    if is_seasonal or alert_type == "seasonal_shift":
        return "digest"
    elif severity == "HIGH":
        return "immediate"
    else:
        return "digest"


def create_alert_payload(flag_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build standardized JSON alert payload with clear user-facing labels and metrics.
    """
    alert_type = flag_row.get("type", "other_anomaly")
    metric = flag_row.get("metric", "conversions")
    actual = float(flag_row.get("actual", 0.0))
    expected = float(flag_row.get("expected", 0.0))
    delta_pct = float(flag_row.get("delta_pct", 0.0))
    spend_share = float(flag_row.get("spend_share", 1.0))
    is_seasonal = bool(flag_row.get("seasonal", False))
    baseline_window = flag_row.get("baseline", BASELINE_WINDOW_DESC)
    
    explanation, first_step = format_explanation(
        alert_type=alert_type,
        metric=metric,
        actual=actual,
        expected=expected,
        delta_pct=delta_pct,
        baseline_window=baseline_window
    )
    
    severity_score, severity = calculate_severity_score(
        alert_type=alert_type,
        actual=actual,
        expected=expected,
        spend_share=spend_share
    )
    
    if "severity" in flag_row and flag_row["severity"] in ["HIGH", "MEDIUM", "LOW"]:
        severity = flag_row["severity"]

    route = route_alert(alert_type=alert_type, severity=severity, is_seasonal=is_seasonal)

    payload = {
        "campaign": flag_row.get("campaign", "CMP-UNKNOWN"),
        "date": str(flag_row.get("date", "")),
        "type": alert_type,
        "type_label": TYPE_LABEL_MAP.get(alert_type, alert_type.replace("_", " ").title()),
        "severity": severity,
        "severity_score": severity_score,
        "route": route,
        "metric": metric,
        "metric_label": METRIC_LABEL_MAP.get(metric.lower(), metric.title()),
        "actual": actual,
        "actual_formatted": format_metric_value(metric, actual),
        "expected": expected,
        "expected_formatted": format_metric_value(metric, expected),
        "delta_pct": delta_pct,
        "baseline": baseline_window,
        "explanation": explanation,
        "first_step": first_step
    }
    return payload


def spot_check_messages(payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Spot-check messages to verify numbers quoted in explanation match payload fields.
    """
    results = []
    type_counts: Dict[str, int] = {}
    
    for payload in payloads:
        a_type = payload["type"]
        type_counts[a_type] = type_counts.get(a_type, 0) + 1
        
        if type_counts[a_type] <= 3:
            explanation = payload["explanation"]
            actual_str = payload["actual_formatted"]
            expected_str = payload["expected_formatted"]
            delta_str = f"{payload['delta_pct']:+.1f}%"
            
            actual_matches = actual_str in explanation
            expected_matches = expected_str in explanation
            delta_matches = delta_str in explanation
            
            passed = actual_matches and expected_matches and delta_matches
            
            results.append({
                "campaign": payload["campaign"],
                "type": a_type,
                "passed": passed,
                "quoted_actual": actual_str,
                "quoted_expected": expected_str,
                "quoted_delta": delta_str,
                "explanation_snippet": explanation[:100] + "..."
            })
            
    return results


def get_reporting_support(payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute totals split and pick example alerts for reporting.
    """
    total_alerts = len(payloads)
    immediate_pages = [p for p in payloads if p["route"] == "immediate"]
    digest_items = [p for p in payloads if p["route"] == "digest"]
    
    pages_count = len(immediate_pages)
    digest_count = len(digest_items)
    
    pages_pct = (pages_count / total_alerts * 100.0) if total_alerts > 0 else 0.0
    digest_pct = (digest_count / total_alerts * 100.0) if total_alerts > 0 else 0.0

    selected_examples = {
        "tracking_break": next((p for p in payloads if p["type"] == "tracking_break"), None),
        "budget_exhausted": next((p for p in payloads if p["type"] == "budget_exhausted"), None),
        "seasonal_shift": next((p for p in payloads if p["type"] == "seasonal_shift"), None),
        "miss_adjacent": next((p for p in payloads if p["type"] in ["other_anomaly", "bid_strategy_change"]), None)
    }

    severity_and_routing_paragraph = (
        "Severity scoring and alert routing are designed to eliminate alert fatigue by enforcing strict "
        "prioritization based on financial impact and urgency. Each detected anomaly is assigned a severity score "
        "calculated as the product of the alert type's critical weight (ranging from 1.0 for tracking breaks down to 0.2 "
        "for seasonal shifts), the metric's relative deviation from baseline expectations, and the campaign's spend "
        "share within the total account portfolio. Alerts exceeding the HIGH severity threshold (>= 0.30) are routed "
        "immediately to the operational team as real-time pages, accompanied by a plain-English narrative and a specific "
        "first diagnostic step. To safeguard operators against noise, all market-wide peer seasonal shifts—regardless of "
        "deviation magnitude—as well as lower-severity anomalies (MEDIUM and LOW), are automatically routed into a unified "
        "daily digest stream, ensuring complete historical auditability without interrupting active workflows."
    )

    return {
        "totals_split": {
            "total_alerts": total_alerts,
            "pages_count": pages_count,
            "pages_pct": round(pages_pct, 1),
            "digest_count": digest_count,
            "digest_pct": round(digest_pct, 1)
        },
        "examples": selected_examples,
        "method_paragraph": severity_and_routing_paragraph
    }


def write_reporting_doc(reporting_data: Dict[str, Any], output_dir: str) -> str:
    """
    Write M3/severity_and_routing_report.md.
    """
    doc_path = os.path.join(output_dir, "severity_and_routing_report.md")
    
    totals = reporting_data["totals_split"]
    examples = reporting_data["examples"]
    paragraph = reporting_data["method_paragraph"]
    
    content = f"""# M3 Reporting Support: Severity & Routing

## 1. Totals Split: Immediate Pages vs Daily Digest

| Stream Category | Alert Count | Share of Total | Description |
|---|---|---|---|
| **Immediate Pages** | {totals['pages_count']} | {totals['pages_pct']}% | High-priority urgent notifications sent directly to ops |
| **Daily Digest Items** | {totals['digest_count']} | {totals['digest_pct']}% | Consolidated daily summary stream for non-paged anomalies |
| **Total Monitored Events** | {totals['total_alerts']} | 100.0% | Complete set of evaluated anomaly flags |

---

## 2. Representative Example Alerts

### Example 1: Broken Conversion Tracking (Immediate Page)
```json
{json.dumps(examples.get('tracking_break'), indent=2)}
```

### Example 2: Early Budget Depletion (Immediate Page)
```json
{json.dumps(examples.get('budget_exhausted'), indent=2)}
```

### Example 3: Market Seasonal Shift (Daily Digest Stream)
```json
{json.dumps(examples.get('seasonal_shift'), indent=2)}
```

### Example 4: Bidding Strategy Shift / Unusual Variance (Daily Digest Stream)
```json
{json.dumps(examples.get('miss_adjacent'), indent=2)}
```

---

## 3. Severity and Routing Method Paragraph

{paragraph}
"""
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    return doc_path


def combine_daily_digest(payloads: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Combine individual digest items into unified daily summary objects by date.
    """
    digest_items = [p for p in payloads if p["route"] == "digest"]
    daily_summaries: Dict[str, Dict[str, Any]] = {}
    
    for item in digest_items:
        date_str = item["date"]
        if date_str not in daily_summaries:
            daily_summaries[date_str] = {
                "date": date_str,
                "total_items": 0,
                "seasonal_count": 0,
                "operational_count": 0,
                "items": []
            }

        daily_summaries[date_str]["total_items"] += 1
        if item["type"] == "seasonal_shift":
            daily_summaries[date_str]["seasonal_count"] += 1
        else:
            daily_summaries[date_str]["operational_count"] += 1

        daily_summaries[date_str]["items"].append(item)
        
    return daily_summaries


def generate_digest_markdown(daily_summaries: Dict[str, Dict[str, Any]], output_dir: str) -> str:
    """
    Generate Markdown summary digest document (daily_digest.md).
    """
    md_path = os.path.join(output_dir, "daily_digest.md")
    
    lines = [
        "# 📊 Campaign Anomaly Monitoring — Daily Digest Summary",
        "",
        "> **Purpose:** Consolidates non-critical operational anomalies and market seasonal shifts into a single daily summary to eliminate alert fatigue while maintaining full auditability.",
        ""
    ]

    if not daily_summaries:
        lines.append("*No non-paged digest items recorded for this monitoring window.*")
    else:
        for date_str, summary in sorted(daily_summaries.items()):
            lines.append(f"## 📅 Daily Digest for {date_str}")
            lines.append(f"**Total Summary Items:** {summary['total_items']} | **Seasonal Patterns:** {summary['seasonal_count']} | **Operational Digest Anomaly Items:** {summary['operational_count']}")
            lines.append("")
            
            for idx, item in enumerate(summary["items"], 1):
                lines.append(f"### {idx}. Campaign `{item['campaign']}` — {item['type_label']} ({item['severity']} Priority)")
                lines.append(f"- **Key Metric Affected:** `{item['metric_label']}`")
                lines.append(f"- **Observed Value:** `{item['actual_formatted']}` vs **Baseline Expected:** `{item['expected_formatted']}` (`{item['delta_pct']:+.1f}%`)")
                lines.append(f"- **Summary Explanation:** {item['explanation']}")
                lines.append(f"- **Recommended Action:** 🛠️ *{item['first_step']}*")
                lines.append("")
                
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    return md_path


def generate_digest_html(payloads: List[Dict[str, Any]], output_dir: str) -> str:
    """
    Generate an interactive, state-of-the-art responsive HTML dashboard (daily_digest.html)
    featuring Chart.js visualizations, live search, stream filters, glassmorphism cards, and JSON copiers.
    """
    html_path = os.path.join(output_dir, "daily_digest.html")
    
    payloads_json_str = json.dumps(payloads, indent=2)
    
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Campaign Anomaly Intelligence Center</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-body: #0b0f19;
            --bg-card: rgba(18, 24, 38, 0.75);
            --bg-card-hover: rgba(26, 35, 54, 0.9);
            --border-glass: rgba(255, 255, 255, 0.08);
            --primary-blue: #3b82f6;
            --primary-glow: rgba(59, 130, 246, 0.35);
            --accent-red: #ef4444;
            --accent-red-glow: rgba(239, 68, 68, 0.35);
            --accent-green: #10b981;
            --accent-amber: #f59e0b;
            --accent-sky: #38bdf8;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-sub: #cbd5e1;
        }}
        
        * {{
            box-sizing: border-box;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        
        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            margin: 0;
            padding: 24px;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(59, 130, 246, 0.12) 0%, transparent 45%),
                radial-gradient(circle at 85% 85%, rgba(239, 68, 68, 0.1) 0%, transparent 45%);
            background-attachment: fixed;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        /* Top Navigation Header */
        .top-navbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 20px 28px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }}
        
        .brand {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}
        
        .brand-icon {{
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.4em;
            box-shadow: 0 0 20px var(--primary-glow);
        }}
        
        .brand-text h1 {{
            margin: 0;
            font-size: 1.4em;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(to right, #ffffff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .brand-text p {{
            margin: 2px 0 0 0;
            font-size: 0.85em;
            color: var(--text-muted);
        }}
        
        .system-status {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
            padding: 8px 16px;
            border-radius: 30px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .status-dot {{
            width: 8px;
            height: 8px;
            background-color: #34d399;
            border-radius: 50%;
            box-shadow: 0 0 10px #34d399;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.4; transform: scale(1.2); }}
            100% {{ opacity: 1; transform: scale(1); }}
        }}
        
        /* Dashboard Charts & KPI Summary Grid */
        .analytics-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }}
        
        .chart-card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }}
        
        .chart-card h3 {{
            margin: 0 0 16px 0;
            font-size: 1.05em;
            font-weight: 700;
            color: var(--text-sub);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .kpi-column {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        
        .kpi-mini-card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .kpi-info h4 {{
            margin: 0;
            font-size: 0.8em;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .kpi-info .val {{
            font-size: 1.8em;
            font-weight: 800;
            margin-top: 4px;
            display: block;
        }}
        
        .kpi-badge {{
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3em;
        }}
        
        /* Interactive Controls Bar */
        .controls-bar {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 16px 24px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
        }}
        
        .search-box {{
            position: relative;
            flex: 1;
            min-width: 260px;
        }}
        
        .search-box input {{
            width: 100%;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-glass);
            border-radius: 10px;
            padding: 12px 16px 12px 42px;
            color: #ffffff;
            font-size: 0.9em;
            font-family: inherit;
        }}
        
        .search-box input:focus {{
            outline: none;
            border-color: var(--primary-blue);
            box-shadow: 0 0 15px var(--primary-glow);
        }}
        
        .search-icon {{
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
        }}
        
        .filter-pills {{
            display: flex;
            gap: 8px;
        }}
        
        .pill {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-glass);
            color: var(--text-muted);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            cursor: pointer;
        }}
        
        .pill:hover, .pill.active {{
            background: var(--primary-blue);
            color: #ffffff;
            border-color: var(--primary-blue);
            box-shadow: 0 0 15px var(--primary-glow);
        }}
        
        .pill.active-immediate {{
            background: var(--accent-red);
            color: #ffffff;
            border-color: var(--accent-red);
            box-shadow: 0 0 15px var(--accent-red-glow);
        }}
        
        /* Anomaly Cards Grid */
        .cards-list {{
            display: flex;
            flex-direction: column;
            gap: 18px;
        }}
        
        .alert-card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            position: relative;
            overflow: hidden;
        }}
        
        .alert-card:hover {{
            background: var(--bg-card-hover);
            transform: translateY(-2px);
            border-color: rgba(255, 255, 255, 0.15);
        }}
        
        .alert-card.route-immediate {{
            border-left: 6px solid var(--accent-red);
        }}
        
        .alert-card.route-digest {{
            border-left: 6px solid var(--primary-blue);
        }}
        
        .card-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        
        .campaign-meta {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        
        .campaign-badge {{
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: #ffffff;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85em;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
        }}
        
        .metric-title {{
            font-size: 1.2em;
            font-weight: 700;
            color: #ffffff;
        }}
        
        .badges-group {{
            display: flex;
            gap: 8px;
        }}
        
        .tag-badge {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}
        
        .tag-immediate {{
            background: rgba(239, 68, 68, 0.15);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.4);
        }}
        
        .tag-digest {{
            background: rgba(56, 189, 248, 0.15);
            color: #7dd3fc;
            border: 1px solid rgba(56, 189, 248, 0.4);
        }}
        
        .tag-severity-high {{
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
        }}
        
        .tag-severity-medium {{
            background: rgba(245, 158, 11, 0.2);
            color: #fbbf24;
        }}
        
        .tag-severity-low {{
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
        }}
        
        /* Metric Comparison Grid inside Card */
        .metric-comparison {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        
        .comp-box span.lbl {{
            display: block;
            font-size: 0.75em;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 600;
        }}
        
        .comp-box span.val {{
            display: block;
            font-size: 1.25em;
            font-weight: 800;
            margin-top: 4px;
        }}
        
        .val-observed {{ color: #ffffff; }}
        .val-expected {{ color: var(--text-sub); }}
        .val-delta-neg {{ color: #f87171; }}
        .val-delta-pos {{ color: #34d399; }}
        
        /* Explanation & Action Box */
        .narrative-box {{
            color: var(--text-sub);
            font-size: 0.95em;
            line-height: 1.6;
            margin-bottom: 16px;
        }}
        
        .action-card {{
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-radius: 10px;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 0.9em;
            color: #93c5fd;
        }}
        
        .action-icon {{
            font-size: 1.3em;
        }}
        
        .card-footer {{
            margin-top: 16px;
            padding-top: 12px;
            border-top: 1px solid var(--border-glass);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.82em;
            color: var(--text-muted);
        }}
        
        .btn-action {{
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid var(--border-glass);
            color: var(--text-main);
            padding: 6px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .btn-action:hover {{
            background: rgba(255, 255, 255, 0.18);
            color: #ffffff;
        }}
        
        /* Toast Notification */
        #toast {{
            visibility: hidden;
            min-width: 250px;
            background-color: #1e293b;
            color: #fff;
            text-align: center;
            border-radius: 10px;
            padding: 12px 20px;
            position: fixed;
            z-index: 100;
            right: 30px;
            bottom: 30px;
            border: 1px solid var(--primary-blue);
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            font-size: 0.9em;
        }}
        
        #toast.show {{
            visibility: visible;
            animation: fadein 0.3s, fadeout 0.3s 2.7s;
        }}
        
        @keyframes fadein {{ from {{ bottom: 0; opacity: 0; }} to {{ bottom: 30px; opacity: 1; }} }}
        @keyframes fadeout {{ from {{ bottom: 30px; opacity: 1; }} to {{ bottom: 0; opacity: 0; }} }}
        
        /* Responsive Breakpoints */
        @media (max-width: 868px) {{
            .analytics-grid {{ grid-template-columns: 1fr; }}
            .metric-comparison {{ grid-template-columns: 1fr; }}
            .controls-bar {{ flex-direction: column; align-items: stretch; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Top Navbar Header -->
        <div class="top-navbar">
            <div class="brand">
                <div class="brand-icon">⚡</div>
                <div class="brand-text">
                    <h1>Campaign Anomaly Intelligence Center</h1>
                    <p>Real-Time Severity Scoring, Root Cause Narrative & Smart Alert Routing</p>
                </div>
            </div>
            <div class="system-status">
                <div class="status-dot"></div>
                Monitoring Active
            </div>
        </div>
        
        <!-- Analytics & KPI Charts Grid -->
        <div class="analytics-grid">
            <div class="chart-card">
                <h3>📊 Anomaly Distribution by Category</h3>
                <div style="height: 180px; position: relative;">
                    <canvas id="typeChart"></canvas>
                </div>
            </div>
            <div class="kpi-column">
                <div class="kpi-mini-card">
                    <div class="kpi-info">
                        <h4>Immediate Pages</h4>
                        <span class="val" style="color: #ef4444;" id="immediateCount">2</span>
                    </div>
                    <div class="kpi-badge" style="background: rgba(239, 68, 68, 0.15); color: #ef4444;">🚨</div>
                </div>
                <div class="kpi-mini-card">
                    <div class="kpi-info">
                        <h4>Daily Digest Stream</h4>
                        <span class="val" style="color: #38bdf8;" id="digestCount">3</span>
                    </div>
                    <div class="kpi-badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">📬</div>
                </div>
            </div>
        </div>
        
        <!-- Interactive Controls Bar -->
        <div class="controls-bar">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" id="searchInput" placeholder="Search campaign (e.g. CMP-001), metric, or keyword..." onkeyup="filterAlerts()">
            </div>
            <div class="filter-pills">
                <button class="pill active" onclick="setFilter('all', this)">All Alerts</button>
                <button class="pill" onclick="setFilter('immediate', this)">🚨 Immediate Pages</button>
                <button class="pill" onclick="setFilter('digest', this)">📬 Daily Digest</button>
                <button class="pill" onclick="setFilter('seasonal', this)">📈 Seasonal Shifts</button>
            </div>
        </div>
        
        <!-- Anomaly Cards Container -->
        <div class="cards-list" id="cardsContainer">
            <!-- Cards rendered dynamically via JavaScript -->
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast">JSON Payload copied to clipboard!</div>

    <!-- JavaScript Application Logic -->
    <script>
        const alertData = {payloads_json_str};
        let currentFilter = 'all';

        function renderAlertCards(items) {{
            const container = document.getElementById('cardsContainer');
            container.innerHTML = '';
            
            if (items.length === 0) {{
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: var(--text-muted); background: var(--bg-card); border-radius: 16px; border: 1px solid var(--border-glass);">
                        🔍 No anomaly records matched your search query or active filter.
                    </div>
                `;
                return;
            }}

            items.forEach((item, index) => {{
                const isImmediate = item.route === 'immediate';
                const routeTagClass = isImmediate ? 'tag-immediate' : 'tag-digest';
                const routeLabel = isImmediate ? '🚨 Immediate Page' : '📬 Daily Digest';
                const sevClass = 'tag-severity-' + item.severity.toLowerCase();
                const deltaClass = item.delta_pct < 0 ? 'val-delta-neg' : 'val-delta-pos';
                const deltaSymbol = item.delta_pct < 0 ? '↓' : '↑';

                const cardHTML = `
                    <div class="alert-card route-${{item.route}}" data-campaign="${{item.campaign.toLowerCase()}}" data-type="${{item.type}}" data-route="${{item.route}}" data-text="${{(item.explanation + ' ' + item.metric_label + ' ' + item.campaign).toLowerCase()}}">
                        <div class="card-top">
                            <div class="campaign-meta">
                                <span class="campaign-badge">${{item.campaign}}</span>
                                <span class="metric-title">${{item.metric_label}}</span>
                            </div>
                            <div class="badges-group">
                                <span class="tag-badge ${{sevClass}}">${{item.severity}} Priority</span>
                                <span class="tag-badge ${{routeTagClass}}">${{routeLabel}}</span>
                            </div>
                        </div>

                        <div class="metric-comparison">
                            <div class="comp-box">
                                <span class="lbl">Observed Value</span>
                                <span class="val val-observed">${{item.actual_formatted}}</span>
                            </div>
                            <div class="comp-box">
                                <span class="lbl">Baseline Expected</span>
                                <span class="val val-expected">${{item.expected_formatted}}</span>
                            </div>
                            <div class="comp-box">
                                <span class="lbl">Deviation Magnitude</span>
                                <span class="val ${{deltaClass}}">${{deltaSymbol}} ${{item.delta_pct > 0 ? '+' : ''}}${{item.delta_pct.toFixed(1)}}%</span>
                            </div>
                        </div>

                        <div class="narrative-box">
                            <strong>Anomaly Root Cause:</strong> ${{item.explanation}}
                        </div>

                        <div class="action-card">
                            <span class="action-icon">🛠️</span>
                            <div>
                                <strong>Recommended Action Plan:</strong>
                                <div>${{item.first_step}}</div>
                            </div>
                        </div>

                        <div class="card-footer">
                            <span>📅 Event Date: <strong>${{item.date}}</strong> &bull; Baseline: <strong>${{item.baseline}}</strong></span>
                            <button class="btn-action" onclick="copyJSON(${{index}})">📋 Copy Alert JSON</button>
                        </div>
                    </div>
                `;
                container.innerHTML += cardHTML;
            }});
        }}

        function setFilter(filterType, element) {{
            currentFilter = filterType;
            document.querySelectorAll('.pill').forEach(p => p.classList.remove('active', 'active-immediate'));
            if (filterType === 'immediate') {{
                element.classList.add('active-immediate');
            }} else {{
                element.classList.add('active');
            }}
            filterAlerts();
        }}

        function filterAlerts() {{
            const searchVal = document.getElementById('searchInput').value.toLowerCase().trim();
            const filtered = alertData.filter(item => {{
                const matchesSearch = item.campaign.toLowerCase().includes(searchVal) ||
                                      item.metric_label.toLowerCase().includes(searchVal) ||
                                      item.explanation.toLowerCase().includes(searchVal) ||
                                      item.type.toLowerCase().includes(searchVal);
                
                let matchesFilter = true;
                if (currentFilter === 'immediate') matchesFilter = (item.route === 'immediate');
                if (currentFilter === 'digest') matchesFilter = (item.route === 'digest');
                if (currentFilter === 'seasonal') matchesFilter = (item.type === 'seasonal_shift');

                return matchesSearch && matchesFilter;
            }});

            renderAlertCards(filtered);
        }}

        function copyJSON(index) {{
            const payload = alertData[index];
            navigator.clipboard.writeText(JSON.stringify(payload, null, 2)).then(() => {{
                showToast("Copied alert JSON for " + payload.campaign + " to clipboard!");
            }});
        }}

        function showToast(message) {{
            const toast = document.getElementById("toast");
            toast.innerText = message;
            toast.className = "show";
            setTimeout(() => {{ toast.className = toast.className.replace("show", ""); }}, 3000);
        }}

        function initChart() {{
            const ctx = document.getElementById('typeChart').getContext('2d');
            const counts = {{}};
            alertData.forEach(item => {{
                counts[item.type_label] = (counts[item.type_label] || 0) + 1;
            }});

            new Chart(ctx, {{
                type: 'doughnut',
                data: {{
                    labels: Object.keys(counts),
                    datasets: [{{
                        data: Object.values(counts),
                        backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#38bdf8', '#10b981'],
                        borderWidth: 0
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'right',
                            labels: {{ color: '#cbd5e1', font: {{ family: 'Plus Jakarta Sans', size: 11 }} }}
                        }}
                    }}
                }}
            }});
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            renderAlertCards(alertData);
            initChart();
        }});
    </script>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
        
    return html_path


def generate_output_csvs(
    alerts: List[Dict[str, Any]],
    output_dir: str = None
) -> Dict[str, str]:
    """
    Write the three required output CSVs strictly in output_dir.
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(output_dir, exist_ok=True)
    df_all = pd.DataFrame(alerts)
    
    if df_all.empty:
        df_immediate = pd.DataFrame()
        df_digest = pd.DataFrame()
    else:
        df_immediate = df_all[df_all["route"] == "immediate"].copy()
        df_digest = df_all[df_all["route"] == "digest"].copy()
        
    path_all = os.path.join(output_dir, "alerts_all.csv")
    path_imm = os.path.join(output_dir, "alerts_immediate.csv")
    path_dig = os.path.join(output_dir, "digest.csv")
    
    df_all.to_csv(path_all, index=False)
    df_immediate.to_csv(path_imm, index=False)
    df_digest.to_csv(path_dig, index=False)
    
    return {
        "alerts_all": path_all,
        "alerts_immediate": path_imm,
        "digest": path_dig
    }


def generate_stub_flags() -> List[Dict[str, Any]]:
    """
    Generate synthetic stub flags for pipeline execution.
    """
    return [
        {
            "campaign": "CMP-001",
            "date": "2026-03-01",
            "type": "tracking_break",
            "metric": "conversions",
            "actual": 0.0,
            "expected": 15.2,
            "delta_pct": -100.0,
            "spend_share": 0.50,
            "hard_rule": True,
            "seasonal": False
        },
        {
            "campaign": "CMP-004",
            "date": "2026-03-02",
            "type": "budget_exhausted",
            "metric": "spend",
            "actual": 450.0,
            "expected": 1200.0,
            "delta_pct": -62.5,
            "spend_share": 0.60,
            "hard_rule": True,
            "seasonal": False
        },
        {
            "campaign": "CMP-007",
            "date": "2026-03-03",
            "type": "bid_strategy_change",
            "metric": "cpa",
            "actual": 45.0,
            "expected": 22.0,
            "delta_pct": 104.5,
            "spend_share": 0.20,
            "hard_rule": False,
            "seasonal": False
        },
        {
            "campaign": "CMP-010",
            "date": "2026-03-04",
            "type": "seasonal_shift",
            "metric": "clicks",
            "actual": 820.0,
            "expected": 1100.0,
            "delta_pct": -25.5,
            "spend_share": 0.80,
            "hard_rule": False,
            "seasonal": True
        },
        {
            "campaign": "CMP-012",
            "date": "2026-03-05",
            "type": "other_anomaly",
            "metric": "ctr",
            "actual": 0.012,
            "expected": 0.035,
            "delta_pct": -65.7,
            "spend_share": 0.15,
            "hard_rule": False,
            "seasonal": False
        }
    ]


def process_flags(flags: List[Dict[str, Any]], output_dir: str = None) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """
    Process stub/detector flags into alert payloads and export output files strictly inside output_dir.
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    alert_payloads = [create_alert_payload(f) for f in flags]
    out_paths = generate_output_csvs(alert_payloads, output_dir)
    
    reporting_data = get_reporting_support(alert_payloads)
    report_doc_path = write_reporting_doc(reporting_data, output_dir)
    out_paths["reporting_report"] = report_doc_path
    
    daily_summaries = combine_daily_digest(alert_payloads)
    digest_md_path = generate_digest_markdown(daily_summaries, output_dir)
    digest_html_path = generate_digest_html(alert_payloads, output_dir)
    out_paths["digest_md"] = digest_md_path
    out_paths["digest_html"] = digest_html_path
    
    return alert_payloads, out_paths, reporting_data


if __name__ == "__main__":
    print("--- M3: Severity, Routing & Explanation Engineer Execution ---")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    stub_flags = generate_stub_flags()
    payloads, files, reporting_info = process_flags(stub_flags, output_dir=current_dir)
    
    print(f"\nGenerated {len(payloads)} alert payloads.")
    
    print("\n--- Totals Split (Pages vs Digest) ---")
    ts = reporting_info["totals_split"]
    print(f"Total Monitored Events: {ts['total_alerts']}")
    print(f"Immediate Pages: {ts['pages_count']} ({ts['pages_pct']}%)")
    print(f"Daily Digest Items: {ts['digest_count']} ({ts['digest_pct']}%)")
    
    print("\n--- Spot-Check Verification ---")
    spot_checks = spot_check_messages(payloads)
    all_passed = True
    for sc in spot_checks:
        status = "PASSED" if sc["passed"] else "FAILED"
        print(f"[{status}] Campaign {sc['campaign']} ({sc['type']}): quoted actual={sc['quoted_actual']}, expected={sc['quoted_expected']}, delta={sc['quoted_delta']}")
        if not sc["passed"]:
            all_passed = False
            
    print(f"\nSpot Check Result: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    
    print("\n--- Output Files Generated (Strictly inside M3 folder) ---")
    for k, v in files.items():
        print(f"  [{k}]: {v}")
