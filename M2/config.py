"""
M2 Configuration module containing detection thresholds and rules parameters.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class M2Config:
    """
    Configuration parameters for M2 Anomaly Detection and Classification.
    All parameters have default values aligned with team contracts.
    """
    # Statistical anomaly threshold T for |robust_z| > T
    robust_threshold: float = 3.5

    # Persistence rule parameters: flagged on at least min_flagged out of lookback_days valid observations
    persistence_lookback_days: int = 3
    persistence_min_flagged: int = 2

    # Seasonality and common peer-movement parameters
    peer_dev_threshold: float = 0.08  # 8% deviation relative to expected
    peer_share_threshold: float = 0.40  # 40% of peer campaigns

    # Minimum volume guards for count / metric anomalies
    min_volume_conversions: float = 5.0
    min_volume_clicks: float = 20.0
    min_volume_spend: float = 10.0

    # Tracking break hard-rule parameters
    tracking_break_min_consec_zeros: int = 2
    tracking_break_min_expected_conversions: float = 5.0

    # Configuration switches
    enable_bid_strategy_detection: bool = True
    enable_persistence: bool = True
    enable_seasonality: bool = True

    @classmethod
    def from_dict(cls, config_dict: Optional[Dict[str, Any]] = None) -> "M2Config":
        """
        Build M2Config instance from a dictionary or return default config.
        """
        if config_dict is None:
            return cls()
        
        # Map common keys if needed (e.g. 'T' -> 'robust_threshold')
        kwargs = {}
        if "T" in config_dict:
            kwargs["robust_threshold"] = float(config_dict["T"])
        if "robust_threshold" in config_dict:
            kwargs["robust_threshold"] = float(config_dict["robust_threshold"])
        if "PEER_DEV" in config_dict:
            kwargs["peer_dev_threshold"] = float(config_dict["PEER_DEV"])
        if "peer_dev_threshold" in config_dict:
            kwargs["peer_dev_threshold"] = float(config_dict["peer_dev_threshold"])
        if "PEER_SHARE" in config_dict:
            kwargs["peer_share_threshold"] = float(config_dict["PEER_SHARE"])
        if "peer_share_threshold" in config_dict:
            kwargs["peer_share_threshold"] = float(config_dict["peer_share_threshold"])
        
        for k, v in config_dict.items():
            if hasattr(cls, k) and k not in kwargs:
                kwargs[k] = v

        return cls(**kwargs)


DEFAULT_CONFIG = M2Config()
