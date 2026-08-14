from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from ..config import PIVOT_WINDOW


@dataclass(slots=True)
class Pivot:
    index: int
    timestamp: str
    price: float
    kind: str  # high | low
    label: str = ""


def detect_pivots(df: pd.DataFrame, window: int = PIVOT_WINDOW) -> list[Pivot]:
    pivots: list[Pivot] = []
    if len(df) < window * 2 + 1:
        return pivots
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    for i in range(window, len(df) - window):
        if highs[i] >= highs[i-window:i+window+1].max():
            pivots.append(Pivot(i, str(df.iloc[i]["timestamp"]), float(highs[i]), "high"))
        if lows[i] <= lows[i-window:i+window+1].min():
            pivots.append(Pivot(i, str(df.iloc[i]["timestamp"]), float(lows[i]), "low"))
    pivots.sort(key=lambda p: p.index)
    return pivots


def label_structure(pivots: list[Pivot], tolerance_pct: float = 0.008) -> list[Pivot]:
    last_by_kind: dict[str, Pivot] = {}
    for p in pivots:
        prev = last_by_kind.get(p.kind)
        if prev is not None:
            tol = max(prev.price, 1.0) * tolerance_pct
            if p.kind == "high":
                if p.price > prev.price + tol:
                    p.label = "HH"
                elif p.price < prev.price - tol:
                    p.label = "LH"
                else:
                    p.label = "EH"
            else:
                if p.price > prev.price + tol:
                    p.label = "HL"
                elif p.price < prev.price - tol:
                    p.label = "LL"
                else:
                    p.label = "EL"
        last_by_kind[p.kind] = p
    return pivots
