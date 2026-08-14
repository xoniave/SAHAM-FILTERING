from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
load_dotenv(PROJECT_DIR / ".env", override=False)
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "dashboard.sqlite3"))
MARKET_PROVIDER = os.getenv("MARKET_PROVIDER", "real_eod").lower()
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "15"))
MAX_HISTORY_BARS = int(os.getenv("MAX_HISTORY_BARS", "320"))
REAL_EOD_HISTORY_PERIOD = os.getenv("REAL_EOD_HISTORY_PERIOD", "2y")
SCANNER_CACHE_SECONDS = int(os.getenv("SCANNER_CACHE_SECONDS", "180"))

# Rule parameters are intentionally configurable. These defaults are starting
# points for calibration, not claims that the user's method requires them.
PIVOT_WINDOW = int(os.getenv("PIVOT_WINDOW", "3"))
SIDEWAYS_MIN_BARS = int(os.getenv("SIDEWAYS_MIN_BARS", "18"))
SIDEWAYS_MAX_WIDTH_PCT = float(os.getenv("SIDEWAYS_MAX_WIDTH_PCT", "0.12"))
LEVEL_CLUSTER_TOLERANCE_PCT = float(os.getenv("LEVEL_CLUSTER_TOLERANCE_PCT", "0.015"))
LEVEL_TOUCH_TOLERANCE_PCT = float(os.getenv("LEVEL_TOUCH_TOLERANCE_PCT", "0.012"))
BREAKOUT_BUFFER_PCT = float(os.getenv("BREAKOUT_BUFFER_PCT", "0.003"))
NEAR_LEVEL_PCT = float(os.getenv("NEAR_LEVEL_PCT", "0.025"))
DO_NOT_CHASE_PCT = float(os.getenv("DO_NOT_CHASE_PCT", "0.08"))

# Entry timing / freshness gates. These are calibration defaults, deliberately
# configurable so they can be tuned against historical cases instead of being
# buried as magic numbers inside the decision engine.
ENTRY_PATTERN_MAX_AGE_BARS = int(os.getenv("ENTRY_PATTERN_MAX_AGE_BARS", "3"))
ENTRY_MAX_SUPPORT_DISTANCE_PCT = float(os.getenv("ENTRY_MAX_SUPPORT_DISTANCE_PCT", "0.03"))
ENTRY_RETRACEMENT_WATCH_MAX_DISTANCE_PCT = float(os.getenv("ENTRY_RETRACEMENT_WATCH_MAX_DISTANCE_PCT", "0.045"))
ENTRY_MIN_ROOM_TO_RESISTANCE_PCT = float(os.getenv("ENTRY_MIN_ROOM_TO_RESISTANCE_PCT", "0.025"))
ENTRY_MIN_LOCATION_RR = float(os.getenv("ENTRY_MIN_LOCATION_RR", "1.20"))
BREAKOUT_ENTRY_MAX_DISTANCE_PCT = float(os.getenv("BREAKOUT_ENTRY_MAX_DISTANCE_PCT", "0.04"))
ROUND_NUMBER_STEPS = [10, 20, 25, 50, 100, 200, 500, 1000]

# Automatic EOD refresh. The server checks the IDX completed-session summary
# periodically. A new daily session triggers a background scanner refresh.
AUTO_EOD_SYNC = os.getenv("AUTO_EOD_SYNC", "true").lower() in {"1", "true", "yes", "on"}
AUTO_EOD_CHECK_SECONDS = int(os.getenv("AUTO_EOD_CHECK_SECONDS", "1200"))
