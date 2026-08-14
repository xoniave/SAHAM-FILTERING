from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from ..config import (
    NEAR_LEVEL_PCT,
    ENTRY_PATTERN_MAX_AGE_BARS,
    ENTRY_MAX_SUPPORT_DISTANCE_PCT,
    ENTRY_RETRACEMENT_WATCH_MAX_DISTANCE_PCT,
    ENTRY_MIN_ROOM_TO_RESISTANCE_PCT,
    ENTRY_MIN_LOCATION_RR,
    BREAKOUT_ENTRY_MAX_DISTANCE_PCT,
)


@dataclass(slots=True)
class DecisionResult:
    decision: str
    confidence: str
    reasons: list[str]
    warnings: list[str]
    next_trigger: str

    def to_dict(self) -> dict:
        return asdict(self)


def _age_bars(pattern: dict[str, Any], current_index: int) -> int:
    try:
        return max(0, current_index - int(pattern.get("index", current_index)))
    except (TypeError, ValueError):
        return 999


def _latest_fresh_pattern(patterns: list[dict[str, Any]], prefix: str, current_index: int) -> dict | None:
    candidates = [
        p for p in patterns
        if str(p.get("group", "")).startswith(prefix)
        and _age_bars(p, current_index) <= ENTRY_PATTERN_MAX_AGE_BARS
    ]
    return max(candidates, key=lambda p: int(p.get("index", -1)), default=None)


def _pct_gap(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), 1.0)


def _entry_location(current: float, support: dict | None, resistance: dict | None) -> dict[str, float | bool | None]:
    support_gap = None
    resistance_gap = None
    location_rr = None

    if support and float(support["price"]) < current:
        support_gap = (current - float(support["price"])) / current
    if resistance and float(resistance["price"]) > current:
        resistance_gap = (float(resistance["price"]) - current) / current
    if support_gap is not None and support_gap > 0 and resistance_gap is not None:
        location_rr = resistance_gap / support_gap

    too_close_resistance = bool(
        resistance_gap is not None and resistance_gap <= ENTRY_MIN_ROOM_TO_RESISTANCE_PCT
    )
    poor_location_rr = bool(
        location_rr is not None and location_rr < ENTRY_MIN_LOCATION_RR
    )
    return {
        "support_gap": support_gap,
        "resistance_gap": resistance_gap,
        "location_rr": location_rr,
        "too_close_resistance": too_close_resistance,
        "poor_location_rr": poor_location_rr,
    }


def _pct_text(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.2f}%"


def decide(analysis: dict[str, Any], position: dict | None = None) -> DecisionResult:
    cycle = analysis["cycle"]
    structure = analysis["structure"]
    volume = analysis["volume"]
    levels = analysis["levels"]
    patterns = analysis["patterns"]
    current = float(analysis["quote"]["last"])
    current_index = int(analysis.get("current_index", analysis["bars"][-1]["index"] if analysis.get("bars") else 0))
    reasons: list[str] = []
    warnings: list[str] = []

    active_support = levels["supports"][0] if levels["supports"] else None
    active_res = levels["resistances"][0] if levels["resistances"] else None
    near_support = bool(active_support and _pct_gap(current, float(active_support["price"])) <= NEAR_LEVEL_PCT)
    near_res = bool(active_res and _pct_gap(float(active_res["price"]), current) <= NEAR_LEVEL_PCT)
    bullish_pattern = _latest_fresh_pattern(patterns, "Bullish", current_index)
    bearish_pattern = _latest_fresh_pattern(patterns, "Bearish", current_index)
    location = _entry_location(current, active_support, active_res)

    if position:
        style = position.get("style", "SWING")
        if structure["trend"] == "DOWNTREND" and structure["state"] == "VALID":
            return DecisionResult("SELL / EXIT", "HIGH", ["Structure sudah membentuk DOWNTREND LH-LL yang valid."], ["Perlindungan modal menjadi prioritas."], "Pertimbangkan entry kembali hanya setelah terbentuk setup baru yang valid.")
        if cycle["breakdown"] and volume["high_volume"] and volume["price_direction"] == "DOWN":
            return DecisionResult("SELL / EXIT", "HIGH", ["Terjadi breakdown pada Support.", "Penurunan disertai High Volume."], [], "Tunggu terbentuk base / Stage 1 baru sebelum mempertimbangkan entry kembali.")
        if style == "SWING":
            if near_res and bearish_pattern:
                age = _age_bars(bearish_pattern, current_index)
                return DecisionResult("SELL ON STRENGTH", "HIGH", ["Harga berada dekat Resistance aktif.", f"Terdeteksi bearish reversal pattern yang masih fresh ({age} candle lalu): {bearish_pattern['name']}."], [], "Lindungi profit; evaluasi ulang jika Resistance berhasil breakout dengan konfirmasi.")
            if near_res:
                return DecisionResult("SELL ON STRENGTH WATCH", "MEDIUM", ["Harga mendekati Resistance aktif."], [], "Pantau reaksi harga, Volume, dan bearish reversal candle fresh di area Resistance.")
        else:  # SUPER
            if structure["state"] == "WEAKENING":
                warnings.append(structure.get("warning") or "Structure trend mulai melemah.")
            if volume["classification"] == "BEARISH CONFIRMATION":
                warnings.append("Harga turun dengan Volume tinggi/meningkat: distribution warning.")
            if warnings:
                return DecisionResult("HOLD — CAUTION", "MEDIUM", ["Konfirmasi exit mayor belum lengkap."], warnings, "Exit menjadi lebih kuat jika Support/structure mayor breakdown disertai High Selling Volume.")
        return DecisionResult("HOLD", "MEDIUM", ["Belum ada invalidasi structure mayor."], warnings, "Lanjut pantau Support aktif, structure, dan Volume.")

    # Belum punya posisi: entry scanner.
    if cycle["macro"].startswith("STAGE 4") or (structure["trend"] == "DOWNTREND" and structure["state"] == "VALID"):
        return DecisionResult("AVOID", "HIGH", ["Context saat ini berada pada Stage 4 / DOWNTREND valid."], [], "Tunggu DOWNTREND melemah dan terbentuk sideways/base baru sebelum entry.")

    # Buy on Breakout must also be time/location aware. A valid breakout can become
    # stale if price has already run too far from the actual breakout level.
    if cycle["breakout"]:
        level = float(cycle["breakout"]["level"])
        breakout_distance = max(0.0, (current - level) / max(level, 1.0))
        if breakout_distance > BREAKOUT_ENTRY_MAX_DISTANCE_PCT:
            return DecisionResult(
                "DO NOT CHASE — BREAKOUT TOO FAR",
                "HIGH",
                [
                    f"Breakout memang terdeteksi, tetapi harga sudah {breakout_distance * 100:.2f}% di atas level breakout {level:,.2f}.",
                    "Window entry Buy on Breakout dianggap sudah lewat.",
                ],
                ["Saham dapat tetap bullish, tetapi lokasi entry baru sudah tidak efisien."],
                "Tunggu retracement/retest ke Support baru atau setup baru; jangan mengejar candle yang sudah lari.",
            )
        if volume["high_volume"]:
            reasons.extend(["Terdeteksi breakout dari Resistance/range terbaru.", "Volume berada di atas Volume MA20 sehingga aktivitas breakout terkonfirmasi."])
            if cycle["macro"].startswith("STAGE 1 →"):
                warnings.append("Macro Stage 2 masih kandidat sampai muncul follow-through structure HH-HL.")
            return DecisionResult("READY — BUY ON BREAKOUT", "HIGH" if not warnings else "MEDIUM", reasons, warnings, "Entry hanya valid selama harga belum terlalu jauh dari level breakout; pantau retest dan follow-through structure.")
        return DecisionResult("WATCH — BUY ON BREAKOUT", "MEDIUM", ["Harga menembus Resistance/range terbaru."], ["Volume belum berada di atas Volume MA20; risiko false breakout masih ada."], "Tunggu konfirmasi Volume atau retest yang berhasil.")

    # Location gate: in Stage 2, a retracement setup is invalid as a *new* entry
    # when the rebound has already carried price too close to Resistance or the
    # remaining room is smaller than the distance back to Support.
    if cycle["macro"] == "STAGE 2" and active_support and active_res:
        if location["too_close_resistance"] or location["poor_location_rr"]:
            reason = [
                f"Harga sekarang berjarak {_pct_text(location['support_gap'])} di atas Support aktif dan hanya {_pct_text(location['resistance_gap'])} dari Resistance aktif.",
            ]
            if location["location_rr"] is not None:
                reason.append(f"Ruang ke Resistance dibanding jarak kembali ke Support hanya sekitar {location['location_rr']:.2f}x; lokasi entry tidak efisien.")
            if bullish_pattern:
                age = _age_bars(bullish_pattern, current_index)
                warnings.append(f"Ada {bullish_pattern['name']} ({age} candle lalu), tetapi pattern tidak mengalahkan lokasi entry yang sudah terlalu dekat Resistance.")
            return DecisionResult(
                "DO NOT CHASE — NEAR RESISTANCE",
                "HIGH",
                reason,
                warnings,
                "Tunggu retracement baru ke Support/cluster yang relevan atau breakout Resistance yang benar-benar terkonfirmasi.",
            )

    if near_support and cycle["macro"] in {"STAGE 1", "STAGE 2", "STAGE 1 → STAGE 2 CANDIDATE"}:
        if bullish_pattern or volume["classification"] == "SELLING PRESSURE WEAKENING":
            support_gap = location["support_gap"]
            if support_gap is not None and support_gap > ENTRY_MAX_SUPPORT_DISTANCE_PCT:
                return DecisionResult(
                    "ENTRY EXPIRED — WAIT RETRACEMENT",
                    "MEDIUM",
                    [f"Bullish context masih ada, tetapi harga sudah {_pct_text(support_gap)} di atas Support aktif."],
                    ["Trigger entry sebelumnya dianggap sudah lewat; jangan memakai pattern lama sebagai alasan entry baru."],
                    "Tunggu harga kembali membentuk retracement sehat ke Support atau setup breakout baru.",
                )
            reasons.append("Harga berada dekat area Support aktif.")
            if bullish_pattern:
                age = _age_bars(bullish_pattern, current_index)
                reasons.append(f"Terdeteksi bullish reversal/continuation pattern yang masih fresh ({age} candle lalu): {bullish_pattern['name']}.")
            if volume["classification"] == "SELLING PRESSURE WEAKENING":
                reasons.append("Harga turun sementara Volume melemah, menunjukkan selling pressure berkurang.")
            if cycle["macro"] == "STAGE 2":
                return DecisionResult("READY — BUY ON RETRACEMENT", "MEDIUM", reasons, [], "Support harus tetap bertahan; setup invalid jika structure/Support breakdown atau harga menjauh hingga dekat Resistance.")
            return DecisionResult("READY — BUY ON WEAKNESS", "MEDIUM", reasons, [], "Support harus tetap bertahan; tunggu konfirmasi lebih kuat jika risk/reward kurang baik.")
        return DecisionResult("WATCH — BUY ON WEAKNESS", "LOW", ["Harga berada dekat Support aktif."], ["Belum ada bullish confirmation fresh yang kuat."], "Tunggu perbaikan Price/Volume atau bullish reversal pattern baru yang valid.")

    if cycle["macro"] == "STAGE 2" and active_support:
        support_gap = location["support_gap"]
        if support_gap is not None and support_gap <= ENTRY_RETRACEMENT_WATCH_MAX_DISTANCE_PCT:
            if active_res and (location["too_close_resistance"] or location["poor_location_rr"]):
                return DecisionResult(
                    "DO NOT CHASE — NEAR RESISTANCE",
                    "HIGH",
                    ["Macro Stage 2 masih valid, tetapi harga sudah lebih dekat ke Resistance daripada area retracement yang efisien."],
                    [],
                    "Tunggu retracement baru ke Support atau breakout Resistance dengan konfirmasi.",
                )
            return DecisionResult("WATCH — BUY ON RETRACEMENT", "MEDIUM", ["Macro Stage 2 masih valid.", "Harga mendekati cluster Support dinamis/structure."], [], "Tunggu Support bertahan disertai bullish Price/Volume atau candlestick confirmation yang masih fresh.")

    return DecisionResult("WAIT", "LOW", ["Belum ada setup entry lengkap pada harga sekarang."], [], "Tunggu harga mendekati Support, membentuk breakout valid, atau menghasilkan setup retracement baru.")
