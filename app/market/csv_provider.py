from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .base import MarketDataProvider, Quote
from ..config import HISTORY_DIR, DATA_DIR


class CSVProvider(MarketDataProvider):
    """
    Provider for real OHLCV exports placed in app/data/history/<SYMBOL>.csv.

    Required columns (case-insensitive): timestamp/date, open, high, low, close, volume.
    This provider is intentionally simple so exported broker/provider data can be
    analyzed without changing the rule engine.
    """
    name = "csv"
    is_live = False
    analysis_enabled = True
    data_mode = "REAL CSV / EOD"

    async def list_symbols(self) -> list[dict]:
        symbols_path = DATA_DIR / "symbols.csv"
        if symbols_path.exists():
            df = pd.read_csv(symbols_path)
            cols = {c.lower(): c for c in df.columns}
            sc = cols.get("symbol") or cols.get("code")
            nc = cols.get("name") or cols.get("company_name")
            if sc:
                return [{"symbol": str(row[sc]).upper(), "name": str(row[nc]) if nc else str(row[sc])} for _, row in df.iterrows()]
        return [{"symbol": p.stem.upper(), "name": p.stem.upper()} for p in sorted(HISTORY_DIR.glob("*.csv"))]

    async def history(self, symbol: str, limit: int = 320) -> pd.DataFrame:
        path = HISTORY_DIR / f"{symbol.upper()}.csv"
        if not path.exists():
            raise FileNotFoundError(f"History file not found: {path}")
        df = pd.read_csv(path)
        mapping = {c.lower().strip(): c for c in df.columns}
        rename = {}
        for target, aliases in {
            "timestamp": ["timestamp", "date", "datetime", "time"],
            "open": ["open", "o"], "high": ["high", "h"], "low": ["low", "l"],
            "close": ["close", "c", "last"], "volume": ["volume", "vol", "v"],
        }.items():
            src = next((mapping[a] for a in aliases if a in mapping), None)
            if src:
                rename[src] = target
        df = df.rename(columns=rename)
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns in {path.name}: {missing}")
        df = df[required].copy()
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna().tail(limit).reset_index(drop=True)
        return df

    async def quote(self, symbol: str) -> Quote:
        df = await self.history(symbol, 2)
        last = float(df.iloc[-1].close)
        prev = float(df.iloc[-2].close) if len(df) > 1 else last
        return Quote(symbol=symbol.upper(), last=last, previous=prev, volume=float(df.iloc[-1].volume), timestamp=datetime.now(timezone.utc).isoformat())
