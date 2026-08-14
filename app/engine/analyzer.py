from __future__ import annotations

import math
from typing import Any

import pandas as pd

from .indicators import add_indicators
from .pivots import detect_pivots, label_structure
from .structure import analyze_structure
from .levels import build_levels
from .candles import detect_patterns
from .cycle import analyze_cycle
from .decision import decide
from ..config import ENTRY_PATTERN_MAX_AGE_BARS


def _serial(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def analyze_symbol(symbol: str, raw: pd.DataFrame, quote: dict, position: dict | None = None) -> dict[str, Any]:
    df = add_indicators(raw)
    pivots = label_structure(detect_pivots(df))
    structure = analyze_structure(pivots)
    levels = build_levels(df, pivots)
    active_support = levels["supports"][0]["price"] if levels["supports"] else None
    active_resistance = levels["resistances"][0]["price"] if levels["resistances"] else None
    patterns = [p.to_dict() for p in detect_patterns(df, active_support, active_resistance)]
    current_index = len(df) - 1
    for p in patterns:
        age = max(0, current_index - int(p.get("index", current_index)))
        p["age_bars"] = age
        p["fresh_for_entry"] = age <= ENTRY_PATTERN_MAX_AGE_BARS
    cycle = analyze_cycle(df, structure)

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    price_direction = "UP" if float(latest.close) > float(previous.close) else "DOWN" if float(latest.close) < float(previous.close) else "FLAT"
    vol_ma = float(latest.volume_ma20) if pd.notna(latest.volume_ma20) else None
    rvol = float(latest.rvol) if pd.notna(latest.rvol) else None
    high_volume = bool(vol_ma and float(latest.volume) > vol_ma)
    recent_vol = df.volume.tail(5)
    vol_direction = "RISING" if len(recent_vol) >= 2 and recent_vol.iloc[-1] > recent_vol.iloc[0] else "FALLING"
    if price_direction == "UP" and (high_volume or vol_direction == "RISING"):
        pv = "BULLISH CONFIRMATION"
    elif price_direction == "DOWN" and (high_volume or vol_direction == "RISING"):
        pv = "BEARISH CONFIRMATION"
    elif price_direction == "UP" and vol_direction == "FALLING":
        pv = "BUYING PRESSURE WEAKENING"
    elif price_direction == "DOWN" and vol_direction == "FALLING":
        pv = "SELLING PRESSURE WEAKENING"
    else:
        pv = "NEUTRAL"

    volume = {
        "current": float(latest.volume), "ma20": vol_ma, "rvol": rvol,
        "high_volume": high_volume, "direction": vol_direction,
        "price_direction": price_direction, "classification": pv,
    }

    bars = []
    for idx, row in df.tail(220).iterrows():
        bars.append({
            "index": int(idx), "timestamp": str(row.timestamp),
            "open": _serial(float(row.open)), "high": _serial(float(row.high)),
            "low": _serial(float(row.low)), "close": _serial(float(row.close)), "volume": _serial(float(row.volume)),
            "ma20": _serial(float(row.ma20)) if pd.notna(row.ma20) else None,
            "ma50": _serial(float(row.ma50)) if pd.notna(row.ma50) else None,
            "ma100": _serial(float(row.ma100)) if pd.notna(row.ma100) else None,
            "ma200": _serial(float(row.ma200)) if pd.notna(row.ma200) else None,
        })

    pivot_payload = [{"index": p.index, "timestamp": p.timestamp, "price": p.price, "kind": p.kind, "label": p.label} for p in pivots[-18:]]
    analysis = {
        "symbol": symbol,
        "quote": quote,
        "current_index": current_index,
        "bars": bars,
        "pivots": pivot_payload,
        "structure": structure.to_dict(),
        "cycle": cycle.to_dict(),
        "levels": levels,
        "volume": volume,
        "patterns": patterns[-12:],
        "indicators": {
            "ma20": _serial(float(latest.ma20)) if pd.notna(latest.ma20) else None,
            "ma50": _serial(float(latest.ma50)) if pd.notna(latest.ma50) else None,
            "ma100": _serial(float(latest.ma100)) if pd.notna(latest.ma100) else None,
            "ma200": _serial(float(latest.ma200)) if pd.notna(latest.ma200) else None,
        },
    }
    analysis["decision"] = decide(analysis, position).to_dict()

    # Unified chart annotation feed. Frontend renders these on the actual candle/level.
    annotations = []
    if cycle.breakout:
        annotations.append({"kind": "breakout", "label": "Breakout", **cycle.breakout})
    if cycle.breakdown:
        annotations.append({"kind": "breakdown", "label": "Breakdown", **cycle.breakdown})
    for p in patterns[-8:]:
        annotations.append({"kind": "pattern", "index": p["index"], "timestamp": p["timestamp"], "price": p["price"], "label": p["name"], "group": p["group"]})
    for p in pivot_payload[-10:]:
        if p["label"]:
            annotations.append({"kind": "structure", "index": p["index"], "timestamp": p["timestamp"], "price": p["price"], "label": p["label"]})
    analysis["annotations"] = annotations
    return analysis
