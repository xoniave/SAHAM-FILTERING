from __future__ import annotations

from dataclasses import dataclass, asdict
import pandas as pd

from .structure import StructureResult
from ..config import SIDEWAYS_MIN_BARS, SIDEWAYS_MAX_WIDTH_PCT, BREAKOUT_BUFFER_PCT


@dataclass(slots=True)
class CycleResult:
    macro: str
    local: str
    context: str
    range_low: float | None
    range_high: float | None
    breakout: dict | None
    breakdown: dict | None

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_cycle(df: pd.DataFrame, structure: StructureResult) -> CycleResult:
    if len(df) < SIDEWAYS_MIN_BARS + 3:
        return CycleResult("UNKNOWN", "UNKNOWN", "Data belum cukup", None, None, None, None)

    current = float(df.iloc[-1].close)
    lookback = min(35, len(df) - 2)
    prior = df.iloc[-lookback-1:-1]
    range_high = float(prior.high.max())
    range_low = float(prior.low.min())
    width_pct = (range_high - range_low) / max((range_high + range_low) / 2, 1.0)
    breakout = None
    breakdown = None

    if current > range_high * (1 + BREAKOUT_BUFFER_PCT):
        breakout = {"level": round(range_high, 2), "index": len(df)-1, "timestamp": str(df.iloc[-1].timestamp), "price": current}
    if current < range_low * (1 - BREAKOUT_BUFFER_PCT):
        breakdown = {"level": round(range_low, 2), "index": len(df)-1, "timestamp": str(df.iloc[-1].timestamp), "price": current}

    local_sideways = width_pct <= SIDEWAYS_MAX_WIDTH_PCT

    if structure.trend == "UPTREND" and structure.state == "VALID":
        macro = "STAGE 2"
        if local_sideways and not breakout:
            local = "LOCAL STAGE 1 / RE-ACCUMULATION"
            context = "Macro Stage 2 tetap bullish sementara harga membentuk local base."
        else:
            local = "LOCAL STAGE 2"
            context = "Context participation / UPTREND."
    elif structure.trend == "UPTREND" and structure.state == "WEAKENING":
        macro, local = "STAGE 3 CANDIDATE", "DISTRIBUTION WATCH"
        context = "UPTREND sebelumnya mulai melemah; Lower High memerlukan kewaspadaan dan konfirmasi."
    elif structure.trend == "DOWNTREND" and structure.state == "VALID":
        macro, local = "STAGE 4", "LOCAL STAGE 4"
        context = "Context capitulation / DOWNTREND."
    else:
        if local_sideways:
            # If the longer price path is recovering from a downtrend, this is treated as Stage 1 candidate rather than Stage 3.
            slope = float(df.close.tail(60).iloc[-1] - df.close.tail(60).iloc[0]) if len(df) >= 60 else 0
            macro = "STAGE 1" if slope <= current * 0.12 else "STAGE 3 CANDIDATE"
            local = "LOCAL STAGE 1" if macro == "STAGE 1" else "TOP SIDEWAYS WATCH"
            context = "Sideways/base terdeteksi; MA hanya supporting evidence, bukan penentu cycle."
        else:
            macro, local = "TRANSITION", "MIXED"
            context = "Structure masih mixed; tunggu range atau urutan trend yang lebih jelas."

    if breakout and macro in {"STAGE 1", "TRANSITION"}:
        macro = "STAGE 1 → STAGE 2 CANDIDATE"
        local = "BREAKOUT / LOCAL STAGE 2"
        context = "Harga breakout dari range terbaru; Macro Stage 2 masih membutuhkan follow-through structure."
    if breakdown and macro in {"STAGE 3 CANDIDATE", "TRANSITION"}:
        macro, local = "STAGE 4 CANDIDATE", "BREAKDOWN"
        context = "Support terbaru breakdown; bearish confirmation semakin kuat jika disertai High Selling Volume."

    return CycleResult(macro, local, context, round(range_low,2), round(range_high,2), breakout, breakdown)
