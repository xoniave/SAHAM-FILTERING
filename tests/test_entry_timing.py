from app.engine.decision import decide


def analysis_template(*, current=8725.0, support=8554.10, resistance=8845.37, pattern_age=1, macro="STAGE 2"):
    idx = 219
    patterns = [{
        "index": idx - pattern_age,
        "timestamp": "2026-08-13",
        "price": current,
        "name": "Bullish Engulfing",
        "group": "Bullish Reversal",
        "quality": "Higher",
        "reason": "test",
        "age_bars": pattern_age,
        "fresh_for_entry": pattern_age <= 3,
    }]
    return {
        "cycle": {"macro": macro, "local": "LOCAL STAGE 2", "breakout": None, "breakdown": None},
        "structure": {"trend": "UPTREND", "state": "VALID", "warning": None},
        "volume": {"high_volume": False, "classification": "BULLISH CONFIRMATION", "price_direction": "UP"},
        "levels": {
            "supports": [{"price": support}],
            "resistances": [{"price": resistance}],
        },
        "patterns": patterns,
        "quote": {"last": current},
        "current_index": idx,
        "bars": [{"index": idx}],
    }


def test_admf_like_location_is_not_ready_retracement():
    out = decide(analysis_template())
    assert out.decision == "DO NOT CHASE — NEAR RESISTANCE"


def test_old_pattern_is_not_used_as_fresh_entry_trigger():
    a = analysis_template(current=8580.0, support=8554.10, resistance=9200.0, pattern_age=9)
    out = decide(a)
    assert out.decision != "READY — BUY ON RETRACEMENT"
    assert "fresh" in " ".join(out.warnings + [out.next_trigger]).lower()


def test_fresh_pattern_near_support_with_room_can_be_ready():
    a = analysis_template(current=8580.0, support=8554.10, resistance=9200.0, pattern_age=1)
    out = decide(a)
    assert out.decision == "READY — BUY ON RETRACEMENT"
