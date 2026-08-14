from __future__ import annotations

from dataclasses import dataclass, asdict
from math import floor, log10

import pandas as pd

from .pivots import Pivot
from ..config import LEVEL_CLUSTER_TOLERANCE_PCT, LEVEL_TOUCH_TOLERANCE_PCT


@dataclass(slots=True)
class Level:
    price: float
    kind: str
    score: float
    sources: list[str]
    touches: int
    recency: int
    label: str

    def to_dict(self) -> dict:
        return asdict(self)


def _round_candidates(price: float) -> list[float]:
    if price <= 0:
        return []
    magnitude = 10 ** floor(log10(price))
    steps = sorted({max(1.0, magnitude / d) for d in (20, 10, 5, 2, 1)})
    out = set()
    for step in steps:
        base = round(price / step) * step
        for k in (-2, -1, 0, 1, 2):
            v = base + k * step
            if v > 0:
                out.add(float(round(v, 4)))
    return sorted(out)


def build_levels(df: pd.DataFrame, pivots: list[Pivot]) -> dict:
    current = float(df.iloc[-1]["close"])
    candidates: list[tuple[float, str, float, int]] = []  # price, source, base score, recency
    n = len(df)

    for p in pivots[-30:]:
        source = "Swing Low" if p.kind == "low" else "Swing High"
        age = n - 1 - p.index
        recency_score = max(0.3, 1.8 - age / 90.0)
        candidates.append((p.price, source, 2.2 * recency_score, age))

    latest = df.iloc[-1]
    for period in (20, 50, 100, 200):
        val = latest.get(f"ma{period}")
        if pd.notna(val):
            candidates.append((float(val), f"MA{period}", 1.35 if period <= 50 else 1.1, 0))

    for r in _round_candidates(current):
        if abs(r - current) / current <= 0.15:
            candidates.append((r, "Round Number", 0.85, 0))

    # Cluster levels that are close together. This naturally updates whenever
    # newer pivots/MA values become more relevant.
    candidates.sort(key=lambda x: x[0])
    clusters: list[list[tuple[float, str, float, int]]] = []
    for item in candidates:
        if not clusters:
            clusters.append([item])
            continue
        center = sum(x[0] for x in clusters[-1]) / len(clusters[-1])
        if abs(item[0] - center) / max(center, 1.0) <= LEVEL_CLUSTER_TOLERANCE_PCT:
            clusters[-1].append(item)
        else:
            clusters.append([item])

    levels: list[Level] = []
    closes = df["close"].to_numpy()
    for cluster in clusters:
        weights = [max(x[2], 0.1) for x in cluster]
        price = sum(x[0] * w for x, w in zip(cluster, weights)) / sum(weights)
        sources = sorted(set(x[1] for x in cluster))
        touches = int(sum(abs(closes - price) / max(price, 1.0) <= LEVEL_TOUCH_TOLERANCE_PCT))
        recency = min(x[3] for x in cluster)
        proximity = max(0.0, 1.5 - abs(current - price) / current * 12)
        score = sum(x[2] for x in cluster) + min(touches, 6) * 0.35 + proximity
        kind = "support" if price < current else "resistance"
        levels.append(Level(price=round(price, 2), kind=kind, score=round(score, 2), sources=sources, touches=touches, recency=recency, label=""))

    supports = sorted([x for x in levels if x.kind == "support"], key=lambda x: (abs(current - x.price), -x.score))
    resistances = sorted([x for x in levels if x.kind == "resistance"], key=lambda x: (abs(current - x.price), -x.score))

    if supports:
        supports[0].label = "Support Aktif"
        if len(supports) > 1:
            strongest = max(supports[1:], key=lambda x: x.score)
            strongest.label = "Support Mayor"
    if resistances:
        resistances[0].label = "Resistance Aktif"
        if len(resistances) > 1:
            strongest = max(resistances[1:], key=lambda x: x.score)
            strongest.label = "Resistance Mayor"

    return {
        "supports": [x.to_dict() for x in supports[:5]],
        "resistances": [x.to_dict() for x in resistances[:5]],
    }
