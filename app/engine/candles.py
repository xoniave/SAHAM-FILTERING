from __future__ import annotations

from dataclasses import dataclass, asdict
import pandas as pd


@dataclass(slots=True)
class PatternEvent:
    index: int
    timestamp: str
    price: float
    name: str
    group: str
    quality: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _anatomy(row) -> dict:
    o, h, l, c = map(float, (row.open, row.high, row.low, row.close))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return {
        "bull": c > o, "bear": c < o,
        "body_ratio": body / rng,
        "upper_ratio": upper / rng,
        "lower_ratio": lower / rng,
        "body_low": min(o, c), "body_high": max(o, c),
    }


def detect_patterns(df: pd.DataFrame, support: float | None = None, resistance: float | None = None) -> list[PatternEvent]:
    events: list[PatternEvent] = []
    if len(df) < 3:
        return events

    def near(price: float, level: float | None, pct: float = 0.035) -> bool:
        return level is not None and abs(price - level) / max(price, 1.0) <= pct

    start = max(1, len(df) - 45)
    for i in range(start, len(df)):
        r = df.iloc[i]
        a = _anatomy(r)
        close = float(r.close)
        prev = df.iloc[i - 1]
        pa = _anatomy(prev)
        prior_slice = df.iloc[max(0, i - 6):i]
        prior_up = len(prior_slice) >= 3 and float(prior_slice.close.iloc[-1]) > float(prior_slice.close.iloc[0])
        prior_down = len(prior_slice) >= 3 and float(prior_slice.close.iloc[-1]) < float(prior_slice.close.iloc[0])

        if a["body_ratio"] >= 0.78 and a["upper_ratio"] <= 0.12 and a["lower_ratio"] <= 0.12:
            if a["bull"]:
                events.append(PatternEvent(i, str(r.timestamp), close, "Bullish Marubozu / White Marubozu", "Bullish Continuation", "Context required", "Body bullish besar dengan wick sangat kecil."))
            elif a["bear"]:
                events.append(PatternEvent(i, str(r.timestamp), close, "Bearish Marubozu", "Bearish Continuation", "Context required", "Body bearish besar dengan wick sangat kecil."))

        if a["lower_ratio"] >= 0.55 and a["body_ratio"] <= 0.35 and a["upper_ratio"] <= 0.2 and prior_down:
            q = "Higher" if near(close, support) else "Candidate"
            events.append(PatternEvent(i, str(r.timestamp), close, "Hammer", "Bullish Reversal", q, "Lower wick panjang setelah penurunan; kualitas meningkat jika berada dekat Support."))

        if a["upper_ratio"] >= 0.55 and a["body_ratio"] <= 0.35 and a["lower_ratio"] <= 0.2 and prior_up:
            q = "Higher" if near(close, resistance) else "Candidate"
            events.append(PatternEvent(i, str(r.timestamp), close, "Shooting Star", "Bearish Reversal", q, "Upper wick panjang setelah kenaikan; kualitas meningkat jika berada dekat Resistance."))

        # Bullish engulfing: body of current bullish candle envelops previous bearish body.
        if a["bull"] and pa["bear"] and a["body_low"] <= pa["body_low"] and a["body_high"] >= pa["body_high"]:
            q = "Higher" if near(close, support) else "Candidate"
            events.append(PatternEvent(i, str(r.timestamp), close, "Bullish Engulfing", "Bullish Reversal", q, "Body bullish menelan body bearish sebelumnya."))

        # Dark cloud cover (simplified): bullish candle followed by bearish open near/above prior close and close below prior body midpoint.
        prev_mid = (float(prev.open) + float(prev.close)) / 2
        if pa["bull"] and a["bear"] and float(r.open) >= float(prev.close) * 0.995 and close < prev_mid and prior_up:
            q = "Higher" if near(close, resistance) else "Candidate"
            events.append(PatternEvent(i, str(r.timestamp), close, "Dark Cloud Cover", "Bearish Reversal", q, "Candle bearish close melewati titik tengah body bullish sebelumnya."))

    # Rising Three Methods: five-candle simplified definition.
    for i in range(max(4, len(df) - 45), len(df)):
        w = df.iloc[i-4:i+1]
        a0, a4 = _anatomy(w.iloc[0]), _anatomy(w.iloc[4])
        middle = w.iloc[1:4]
        if a0["bull"] and a0["body_ratio"] >= 0.58 and a4["bull"] and a4["body_ratio"] >= 0.58:
            if float(w.iloc[4].close) > float(w.iloc[0].high):
                inside = bool(((middle.high <= float(w.iloc[0].high) * 1.01) & (middle.low >= float(w.iloc[0].low) * 0.99)).all())
                if inside:
                    events.append(PatternEvent(i, str(w.iloc[4].timestamp), float(w.iloc[4].close), "Rising Three Methods", "Bullish Continuation", "Candidate", "Candle bullish kuat, tiga candle konsolidasi di dalam range, lalu bullish continuation."))

    # Deduplicate same name/index.
    unique = {}
    for e in events:
        unique[(e.index, e.name)] = e
    return sorted(unique.values(), key=lambda e: e.index)
