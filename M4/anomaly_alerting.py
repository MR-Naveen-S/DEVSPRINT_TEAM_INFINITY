"""
Anomaly Alerting Entry Point & Tuning Lead Script.
Owned by M4 (Evaluation, Tuning & Reporting Lead).
Executes Phase 1 Pipeline, Phase 2 Tuning & Sensitivity Analysis, Naive Baseline comparison,
Phase 3 Reporting & Verification, and Phase 4 Polish (Plots & Isolation Forest).
"""

import sys
import os
import pandas as pd
import config
import baseline
import detect
import route_explain
import evaluate
import plots
import ml_isolation_forest

def run_phase1_pipeline(data_path, incidents_path):
    print("=" * 65)
    print("CAMPAIGN ANOMALY ALERTING PIPELINE - ENGINE RUN")
    print("=" * 65)
    print(f"Data Source:      {data_path}")
    print(f"Incidents Source: {incidents_path}")
    print("-" * 65)

    # 1. Load Data & M1 Baseline
    print("[1/4] Running M1 Baseline computation...")
    raw_df = baseline.load_real(data_path)
    residual_df = baseline.run_baseline(raw_df)
    print(f"      Calculated {len(residual_df)} residual entries across campaigns and metrics.")

    # 2. M2 Detection & Classification
    print("[2/4] Running M2 Detection & Classification...")
    flag_df = detect.run_detection(residual_df)
    print(f"      Flagged {len(flag_df)} candidate campaign-day anomalies.")

    # 3. M3 Routing & Explanations
    print("[3/4] Running M3 Severity Scoring, Routing & Explanations...")
    alerts_df, immediate_df, digest_df = route_explain.run_routing(flag_df)
    print(f"      Total Alerts Fired:   {len(alerts_df)}")
    print(f"      Immediate Pages:     {len(immediate_df)} saved to {config.ALERTS_IMMEDIATE_PATH}")
    print(f"      Digest Items:        {len(digest_df)} saved to {config.DIGEST_PATH}")

    # 4. M4 Evaluation
    print("[4/4] Running M4 Evaluation & Matching against Seeded Incidents...")
    incidents_df = evaluate.load_incidents(incidents_path)
    eval_results = evaluate.match_alerts_to_incidents(alerts_df, incidents_df)
    cm_results = evaluate.compute_campaign_day_confusion_matrix(raw_df, alerts_df, incidents_df)

    print("\n" + "=" * 65)
    print("EVALUATION & CONFUSION MATRIX SUMMARY")
    print("=" * 65)
    print(f"Total Seeded Incidents (Scored): {eval_results['total_incidents']}")
    print(f"Caught Incidents:              {eval_results['caught_incidents']}")
    print(f"Incident Recall:               {eval_results['incident_recall'] * 100:.1f}%")
    print(f"Alert Precision (Overall):     {eval_results['alert_precision'] * 100:.1f}%")
    print(f"Page Precision (Immediate):    {eval_results['page_precision'] * 100:.1f}%")
    print(f"Average Detection Lag:         {eval_results['avg_detection_lag']:.2f} days")
    print("-" * 65)
    print("Campaign-Day Confusion Matrix:")
    print(f"  - True Positives (TP):  {cm_results['TP']}")
    print(f"  - False Positives (FP): {cm_results['FP']}")
    print(f"  - False Negatives (FN): {cm_results['FN']}")
    print(f"  - True Negatives (TN):  {cm_results['TN']}")
    print(f"  - False Positive Rate (FPR): {cm_results['FPR'] * 100:.2f}%")
    print(f"  - FP Immediate Pages / Month: {cm_results['fp_pages_per_month']:.1f}")
    print("-" * 65)
    print("Per-Incident Details:")
    for inc in eval_results['incidents_summary']:
        status = "CAUGHT" if inc['caught'] else "MISSED"
        lag_str = f"{inc['detection_lag_days']}d lag" if inc['caught'] else "N/A"
        print(f"  - [{status}] Campaign: {inc['campaign']} ({inc['norm_campaign']}) | Dates: {inc['start']} to {inc['end']} | Type: {inc['type']} | {lag_str}")

    return raw_df, incidents_df, alerts_df, eval_results, cm_results

def run_phase2_tuning(data_path, incidents_path):
    print("\n" + "=" * 65)
    print("PHASE 2: THRESHOLD SWEEP & TUNING (T = 3.0 to 6.0)")
    print("=" * 65)
    
    sweep_df = evaluate.sweep_thresholds(data_path, incidents_path)
    print(sweep_df.to_string(index=False))
    
    flat_rows = sweep_df[sweep_df['recall_pct'] == sweep_df['recall_pct'].max()]
    chosen_t = float(flat_rows.iloc[len(flat_rows)//2]['T']) if not flat_rows.empty else 4.5
    print(f"\n---> Optimal T chosen in flat region of sweep: T = {chosen_t}")
    config.T = chosen_t

    print("\n" + "=" * 65)
    print("PHASE 2: WINDOW SENSITIVITY CHECK (21, 28, 35 DAYS)")
    print("=" * 65)
    
    sens_df = evaluate.check_window_sensitivity(data_path, incidents_path)
    print(sens_df.to_string(index=False))

    print("\n" + "=" * 65)
    print("PHASE 2: NAIVE BASELINE vs FINAL SYSTEM (BEFORE & AFTER)")
    print("=" * 65)
    
    naive_count = evaluate.compute_naive_baseline(data_path)
    
    raw_df = baseline.load_real(data_path)
    res_df = baseline.run_baseline(raw_df)
    flag_df = detect.run_detection(res_df)
    final_alerts_df, final_imm, final_dig = route_explain.run_routing(flag_df)
    final_count = len(final_alerts_df)
    
    reduction_count = naive_count - final_count
    reduction_pct = (reduction_count / naive_count * 100.0) if naive_count > 0 else 0.0
    
    print(f"Naive Fixed-Threshold Alerts (30% DoD rule):  {naive_count}")
    print(f"Final Intelligent Anomaly System Alerts:      {final_count} ({len(final_imm)} pages, {len(final_dig)} digest)")
    print(f"Alert Fatigue Reduction:                    {reduction_count} alerts eliminated ({reduction_pct:.1f}% reduction)")
    print("=" * 65 + "\n")

def run_phase4_polish(data_path, incidents_path):
    print("\n" + "=" * 65)
    print("PHASE 4: POLISH - PLOTS & ISOLATION FOREST CHECK")
    print("=" * 65)
    
    # 1. Generate Plots
    plot_file = plots.generate_campaign_plots(data_path, incidents_path, "campaign_plots.png")
    
    # 2. Run Isolation Forest
    _, ml_summary = ml_isolation_forest.run_isolation_forest(data_path, incidents_path)
    
    # 3. Report Generation
    report_file = evaluate.generate_phase3_report(data_path, incidents_path, "M4_PHASE3_SUBMISSION_REPORT.md")
    
    print(f"  [OK] Campaign Plot Visualization: {plot_file}")
    print(f"  [OK] Isolation Forest Cross-Check: {ml_summary['total_ml_anomalies']} anomalies, Recall = {ml_summary['ml_incident_recall']*100:.1f}%")
    print(f"  [OK] Submission Report with Mermaid Diagram: {report_file}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    data_file = sys.argv[1] if len(sys.argv) > 1 else "stub_data.csv"
    incidents_file = sys.argv[2] if len(sys.argv) > 2 else "incidents.csv"
    
    run_phase1_pipeline(data_file, incidents_file)
    run_phase2_tuning(data_file, incidents_file)
    run_phase4_polish(data_file, incidents_file)
