"""
Unit Test Suite for M4 Evaluation Module (evaluate.py).
Tests boundary conditions, matching logic, metric calculations, edge cases, zero denominators,
and seasonal exclusions against manually calculated expected ground truth.
"""

import pandas as pd
import numpy as np
import evaluate

def test_empty_datasets():
    print("[TEST 1/8] Empty Datasets Test...")
    empty_alerts = pd.DataFrame(columns=['campaign', 'date', 'type', 'route', 'severity'])
    empty_incidents = pd.DataFrame(columns=['campaign', 'start', 'end', 'type'])
    
    res = evaluate.match_alerts_to_incidents(empty_alerts, empty_incidents)
    assert res['incident_recall'] == 1.0, f"Expected 1.0, got {res['incident_recall']}"
    assert res['alert_precision'] == 1.0, f"Expected 1.0, got {res['alert_precision']}"
    assert res['page_precision'] == 1.0, f"Expected 1.0, got {res['page_precision']}"
    assert res['page_recall'] == 1.0, f"Expected 1.0, got {res['page_recall']}"
    assert res['caught_incidents'] == 0
    print("  -> PASS: Empty datasets handled safely without error or division-by-zero.")

def test_seasonal_exclusion():
    print("[TEST 2/8] Seasonal Incident Exclusion Test...")
    incidents = pd.DataFrame([
        {'campaign': 'C01', 'start': '2026-03-10', 'end': '2026-03-15', 'type': 'tracking_break'},
        {'campaign': 'C02', 'start': '2026-03-20', 'end': '2026-03-25', 'type': 'seasonal_shift'}
    ])
    incidents['norm_campaign'] = incidents['campaign'].apply(evaluate.normalize_campaign_id)
    incidents['start'] = pd.to_datetime(incidents['start'])
    incidents['end'] = pd.to_datetime(incidents['end'])
    
    # Alert for C01 inside window
    alerts = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-12', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'}
    ])
    
    res = evaluate.match_alerts_to_incidents(alerts, incidents)
    # Seasonal incident should be excluded from total_incidents, so total valid incidents = 1
    assert res['total_incidents'] == 1, f"Expected 1 total valid incident, got {res['total_incidents']}"
    assert res['caught_incidents'] == 1, f"Expected 1 caught incident, got {res['caught_incidents']}"
    assert res['incident_recall'] == 1.0, f"Expected 1.0 recall, got {res['incident_recall']}"
    print("  -> PASS: Seasonal incidents correctly excluded from scoring metrics.")

def test_date_boundary_matching():
    print("[TEST 3/8] Date Boundary Matching Test (Before, On, Inside, On End, After)...")
    incidents = pd.DataFrame([
        {'campaign': 'C01', 'start': '2026-03-10', 'end': '2026-03-15', 'type': 'tracking_break'}
    ])
    incidents['norm_campaign'] = incidents['campaign'].apply(evaluate.normalize_campaign_id)
    incidents['start'] = pd.to_datetime(incidents['start'])
    incidents['end'] = pd.to_datetime(incidents['end'])
    
    # 1. Alert 1 day BEFORE start (2026-03-09) -> Should NOT match
    alerts_before = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-09', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'}
    ])
    res_before = evaluate.match_alerts_to_incidents(alerts_before, incidents)
    assert res_before['caught_incidents'] == 0, "Alert before start date should NOT match"
    
    # 2. Alert ON start date (2026-03-10) -> Should MATCH (lag = 0)
    alerts_start = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-10', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'}
    ])
    res_start = evaluate.match_alerts_to_incidents(alerts_start, incidents)
    assert res_start['caught_incidents'] == 1, "Alert on start date MUST match"
    assert res_start['avg_detection_lag'] == 0.0, f"Expected lag 0, got {res_start['avg_detection_lag']}"
    
    # 3. Alert INSIDE window (2026-03-12) -> Should MATCH (lag = 2)
    alerts_inside = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-12', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'}
    ])
    res_inside = evaluate.match_alerts_to_incidents(alerts_inside, incidents)
    assert res_inside['caught_incidents'] == 1, "Alert inside window MUST match"
    assert res_inside['avg_detection_lag'] == 2.0, f"Expected lag 2, got {res_inside['avg_detection_lag']}"
    
    # 4. Alert ON end date (2026-03-15) -> Should MATCH
    alerts_end = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-15', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'}
    ])
    res_end = evaluate.match_alerts_to_incidents(alerts_end, incidents)
    assert res_end['caught_incidents'] == 1, "Alert on end date MUST match"
    
    # 5. Alert 1 day AFTER end date (2026-03-16) -> Should NOT match
    alerts_after = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-16', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'}
    ])
    res_after = evaluate.match_alerts_to_incidents(alerts_after, incidents)
    assert res_after['caught_incidents'] == 0, "Alert after end date should NOT match"
    
    print("  -> PASS: All date boundary conditions (Before, Start, Inside, End, After) behave strictly as expected.")

def test_multiple_alerts_per_incident():
    print("[TEST 4/8] Multiple Alerts for Single Incident Test...")
    incidents = pd.DataFrame([
        {'campaign': 'C01', 'start': '2026-03-10', 'end': '2026-03-15', 'type': 'tracking_break'}
    ])
    incidents['norm_campaign'] = incidents['campaign'].apply(evaluate.normalize_campaign_id)
    incidents['start'] = pd.to_datetime(incidents['start'])
    incidents['end'] = pd.to_datetime(incidents['end'])
    
    # 3 alerts during the same incident window
    alerts = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-11', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'},
        {'campaign': 'C01', 'date': '2026-03-12', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'},
        {'campaign': 'C01', 'date': '2026-03-13', 'type': 'tracking_break', 'route': 'digest', 'severity': 'MEDIUM'}
    ])
    
    res = evaluate.match_alerts_to_incidents(alerts, incidents)
    assert res['total_incidents'] == 1, "Should count 1 incident"
    assert res['caught_incidents'] == 1, "Should catch 1 incident (not 3)"
    assert res['incident_recall'] == 1.0
    assert res['avg_detection_lag'] == 1.0, f"Expected earliest lag 1 day (2026-03-11 - 2026-03-10), got {res['avg_detection_lag']}"
    assert res['tp_alerts'] == 3, f"Expected 3 TP alerts, got {res['tp_alerts']}"
    print("  -> PASS: Incident counted exactly once; detection lag uses earliest alert.")

def test_page_precision_and_page_recall():
    print("[TEST 5/8] Page Precision and Page Recall Test...")
    incidents = pd.DataFrame([
        {'campaign': 'C01', 'start': '2026-03-10', 'end': '2026-03-15', 'type': 'tracking_break'},
        {'campaign': 'C02', 'start': '2026-03-20', 'end': '2026-03-25', 'type': 'budget_exhausted'}
    ])
    incidents['norm_campaign'] = incidents['campaign'].apply(evaluate.normalize_campaign_id)
    incidents['start'] = pd.to_datetime(incidents['start'])
    incidents['end'] = pd.to_datetime(incidents['end'])
    
    # Alerts: C01 has an immediate page match; C02 has ONLY a digest match; C03 has an FP immediate page
    alerts = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-11', 'type': 'tracking_break', 'route': 'immediate', 'severity': 'HIGH'},
        {'campaign': 'C02', 'date': '2026-03-21', 'type': 'budget_exhausted', 'route': 'digest', 'severity': 'MEDIUM'},
        {'campaign': 'C03', 'date': '2026-03-30', 'type': 'other_anomaly', 'route': 'immediate', 'severity': 'HIGH'}
    ])
    
    res = evaluate.match_alerts_to_incidents(alerts, incidents)
    # Total valid incidents = 2.
    # Overall caught = 2 (C01 and C02). Overall recall = 2/2 = 1.0 (100%).
    # Immediate pages: 2 total (C01 and C03). C01 matched incident -> 1 TP page. C03 is FP. Page precision = 1/2 = 0.50 (50%).
    # Page recall: C01 caught by immediate page; C02 caught by digest only. Page recall = 1/2 = 0.50 (50%).
    assert res['incident_recall'] == 1.0
    assert res['page_precision'] == 0.5, f"Expected page_precision 0.5, got {res['page_precision']}"
    assert res['page_recall'] == 0.5, f"Expected page_recall 0.5, got {res['page_recall']}"
    print("  -> PASS: Page precision and Page recall computed accurately.")

def test_confusion_matrix_and_fpr():
    print("[TEST 6/8] Confusion Matrix & FPR Test...")
    # Create 10 campaign-days for C01 (2026-03-01 to 2026-03-10)
    data = pd.DataFrame([
        {'campaign': 'C01', 'date': f'2026-03-{d:02d}'} for d in range(1, 11)
    ])
    
    # Incident on days 03-02 to 03-04 (3 incident days)
    incidents = pd.DataFrame([
        {'campaign': 'C01', 'start': '2026-03-02', 'end': '2026-03-04', 'type': 'tracking_break'}
    ])
    incidents['norm_campaign'] = incidents['campaign'].apply(evaluate.normalize_campaign_id)
    incidents['start'] = pd.to_datetime(incidents['start'])
    incidents['end'] = pd.to_datetime(incidents['end'])
    
    # Alerts on 03-02 (TP), 03-03 (TP), 03-05 (FP immediate page)
    alerts = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-02', 'type': 'tracking_break', 'route': 'immediate'},
        {'campaign': 'C01', 'date': '2026-03-03', 'type': 'tracking_break', 'route': 'digest'},
        {'campaign': 'C01', 'date': '2026-03-05', 'type': 'other_anomaly', 'route': 'immediate'}
    ])
    
    cm = evaluate.compute_campaign_day_confusion_matrix(data, alerts, incidents)
    # Total days = 10.
    # Incident days = 3 (03-02, 03-03, 03-04). Non-incident days = 7.
    # Alerts on incident days = 2 (03-02, 03-03) -> TP = 2.
    # Incident day without alert = 1 (03-04) -> FN = 1.
    # Non-incident day with alert = 1 (03-05) -> FP = 1.
    # Non-incident day without alert = 6 -> TN = 6.
    # FPR = FP / (FP + TN) = 1 / (1 + 6) = 1/7 = 0.142857 (14.29%).
    assert cm['TP'] == 2, f"Expected TP 2, got {cm['TP']}"
    assert cm['FN'] == 1, f"Expected FN 1, got {cm['FN']}"
    assert cm['FP'] == 1, f"Expected FP 1, got {cm['FP']}"
    assert cm['TN'] == 6, f"Expected TN 6, got {cm['TN']}"
    assert abs(cm['FPR'] - (1/7)) < 1e-4, f"Expected FPR 0.1428, got {cm['FPR']}"
    print("  -> PASS: Campaign-day Confusion Matrix (TP, FP, FN, TN, FPR) calculated perfectly.")

def test_zero_denominators_and_edge_cases():
    print("[TEST 7/8] Zero Denominators & Edge Cases Test...")
    # 0 alerts, 0 incidents
    data = pd.DataFrame([{'campaign': 'C01', 'date': '2026-03-01'}])
    empty_alerts = pd.DataFrame(columns=['campaign', 'date', 'type', 'route'])
    empty_incidents = pd.DataFrame(columns=['campaign', 'start', 'end', 'type'])
    
    cm = evaluate.compute_campaign_day_confusion_matrix(data, empty_alerts, empty_incidents)
    assert cm['FPR'] == 0.0, f"FPR should be 0.0 for 0 FPs, got {cm['FPR']}"
    assert cm['TN'] == 1
    assert cm['FP'] == 0
    print("  -> PASS: Division by zero avoided in edge cases.")

def test_naive_baseline_comparison():
    print("[TEST 8/8] Naive Baseline DoD Test...")
    data = pd.DataFrame([
        {'campaign': 'C01', 'date': '2026-03-01', 'spend': 100.0, 'clicks': 50, 'conversions': 10},
        {'campaign': 'C01', 'date': '2026-03-02', 'spend': 140.0, 'clicks': 50, 'conversions': 10}, # +40% spend -> Naive Flag
        {'campaign': 'C01', 'date': '2026-03-03', 'spend': 140.0, 'clicks': 50, 'conversions': 10}  # 0% change -> Normal
    ])
    # Write temporary file
    temp_path = "test_naive_temp.csv"
    data.to_csv(temp_path, index=False)
    
    naive_count = evaluate.compute_naive_baseline(temp_path)
    import os
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    assert naive_count == 1, f"Expected 1 naive alert on day 2, got {naive_count}"
    print("  -> PASS: Naive fixed-threshold baseline correctly flags DoD swings > 30%.")

def run_all_unit_tests():
    print("=" * 60)
    print("RUNNING M4 EVALUATION UNIT TESTS")
    print("=" * 60)
    test_empty_datasets()
    test_seasonal_exclusion()
    test_date_boundary_matching()
    test_multiple_alerts_per_incident()
    test_page_precision_and_page_recall()
    test_confusion_matrix_and_fpr()
    test_zero_denominators_and_edge_cases()
    test_naive_baseline_comparison()
    print("=" * 60)
    print("ALL 8 UNIT TESTS PASSED SUCCESSFULLY!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_all_unit_tests()
