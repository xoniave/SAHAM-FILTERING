import asyncio

from app.market.demo_provider import DemoProvider
from app.engine.indicators import add_indicators
from app.engine.pivots import detect_pivots, label_structure
from app.engine.levels import build_levels
from app.engine.candles import detect_patterns


def test_volume_ma20_exists():
    df = asyncio.run(DemoProvider().history("EXCL", 200))
    out = add_indicators(df)
    assert "volume_ma20" in out.columns
    assert out.volume_ma20.notna().sum() > 0


def test_levels_recalculate():
    df = add_indicators(asyncio.run(DemoProvider().history("EXCL", 250)))
    piv = label_structure(detect_pivots(df))
    levels = build_levels(df, piv)
    assert "supports" in levels and "resistances" in levels
    assert levels["supports"] or levels["resistances"]


def test_pattern_detector_returns_list():
    df = add_indicators(asyncio.run(DemoProvider().history("ANTM", 250)))
    events = detect_patterns(df)
    assert isinstance(events, list)
