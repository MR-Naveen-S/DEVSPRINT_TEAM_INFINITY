# integration/contracts.py
CONTRACTS = {
    "residuals": ["campaign","date","metric","actual","expected","mad","noise_floor","robust_z"],
    "flags": ["campaign","date","type","metric","actual","expected","delta_pct","hard_rule","seasonal"],
    "alerts": ["campaign","date","type","severity","route","metric","actual","expected",
               "delta_pct","explanation","first_step"],
}

def validate(df, name):
    missing = [c for c in CONTRACTS[name] if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")
    return df
