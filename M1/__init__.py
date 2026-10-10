"""
M1 Package: Data & Baseline Engineering
"""
from .baseline import (
    load_real,
    validate_input_dataframe,
    derive_metrics,
    compute_baseline_residuals,
    calculate_mad,
    get_noise_floor,
    run_window_sensitivity_sweep,
    generate_synthetic_stub_data,
    generate_weekly_small_campaign_aggregates,
    run_m1_pipeline,
)
from .config import (
    ALIAS_MAP,
    CANONICAL_COLUMNS,
    DEFAULT_WINDOW_DAYS,
    DEFAULT_FREEZE_DAYS,
    DEFAULT_T_MULTIPLIER,
    MAD_SCALE_FACTOR,
)

__all__ = [
    "load_real",
    "validate_input_dataframe",
    "derive_metrics",
    "compute_baseline_residuals",
    "calculate_mad",
    "get_noise_floor",
    "run_window_sensitivity_sweep",
    "generate_synthetic_stub_data",
    "generate_weekly_small_campaign_aggregates",
    "run_m1_pipeline",
    "ALIAS_MAP",
    "CANONICAL_COLUMNS",
    "DEFAULT_WINDOW_DAYS",
    "DEFAULT_FREEZE_DAYS",
    "DEFAULT_T_MULTIPLIER",
    "MAD_SCALE_FACTOR",
]
