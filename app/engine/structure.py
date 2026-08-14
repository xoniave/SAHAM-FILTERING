from __future__ import annotations

from dataclasses import dataclass, asdict
from .pivots import Pivot


@dataclass(slots=True)
class StructureResult:
    trend: str
    state: str
    sequence: list[str]
    warning: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_structure(pivots: list[Pivot]) -> StructureResult:
    labeled = [p for p in pivots if p.label]
    sequence = [p.label for p in labeled[-8:]]
    highs = [p.label for p in labeled if p.kind == "high"][-3:]
    lows = [p.label for p in labeled if p.kind == "low"][-3:]

    trend = "SIDEWAYS / MIXED"
    state = "NEUTRAL"
    warning = None

    if highs and lows:
        if highs[-1] == "HH" and lows[-1] == "HL":
            trend, state = "UPTREND", "VALID"
        elif highs[-1] == "LH" and lows[-1] == "LL":
            trend, state = "DOWNTREND", "VALID"
        elif highs[-1] == "LH" and lows[-1] in {"HL", "EL"}:
            trend, state = "UPTREND", "WEAKENING"
            warning = "Lower High terdeteksi; UPTREND melemah tetapi belum otomatis invalid."
        elif highs[-1] in {"HH", "EH"} and lows[-1] == "LL":
            trend, state = "MIXED", "WEAKENING"
            warning = "Lower Low terdeteksi di dalam structure yang sebelumnya lebih kuat."

    return StructureResult(trend, state, sequence, warning)
