from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for period in (20, 50, 100, 200):
        out[f"ma{period}"] = out["close"].rolling(period, min_periods=max(5, period // 4)).mean()
    out["volume_ma20"] = out["volume"].rolling(20, min_periods=5).mean()
    out["rvol"] = out["volume"] / out["volume_ma20"].replace(0, pd.NA)
    prev_close = out["close"].shift(1)
    true_range = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr14"] = true_range.rolling(14, min_periods=5).mean()
    out["return_pct"] = out["close"].pct_change() * 100.0
    return out
