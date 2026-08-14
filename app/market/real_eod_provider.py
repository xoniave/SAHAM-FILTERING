from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .base import MarketDataProvider, Quote
from .idx_client import IDXWebClient, save_json
from ..config import DATA_DIR, HISTORY_DIR, REAL_EOD_HISTORY_PERIOD


SYMBOLS_PATH = DATA_DIR / "symbols.csv"
LATEST_SNAPSHOT_PATH = DATA_DIR / "latest_idx_snapshot.json"


class RealEODProvider(MarketDataProvider):
    """Real completed-session provider.

    Sources:
    - Universe + latest completed IDX daily summary: idx.co.id website endpoints.
    - Longer daily history: Yahoo Finance via yfinance (`<CODE>.JK`), cached locally.

    This provider is deliberately NOT marked live. It is for real EOD analysis and
    rule calibration while the licensed/broker real-time feed is still absent.
    """

    name = "real_eod"
    is_live = False
    analysis_enabled = True
    data_mode = "REAL EOD"

    def __init__(self) -> None:
        self.client = IDXWebClient()
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    async def list_symbols(self) -> list[dict]:
        cached = await asyncio.to_thread(self._read_symbols)
        if len(cached) >= 100:
            return cached
        return await asyncio.to_thread(self._refresh_universe)

    def _read_symbols(self) -> list[dict]:
        if not SYMBOLS_PATH.exists():
            return []
        try:
            df = pd.read_csv(SYMBOLS_PATH, dtype=str).fillna("")
        except Exception:
            return []
        if "symbol" not in df.columns:
            return []
        cols = [c for c in ["symbol", "name", "sector", "subsector", "industry", "subindustry", "board"] if c in df.columns]
        return [{k: str(row[k]).strip() for k in cols} for _, row in df.iterrows() if str(row["symbol"]).strip()]

    def _refresh_universe(self) -> list[dict]:
        rows = self.client.company_profiles()
        pd.DataFrame(rows).to_csv(SYMBOLS_PATH, index=False, encoding="utf-8-sig")
        return rows

    async def history(self, symbol: str, limit: int = 320) -> pd.DataFrame:
        return await asyncio.to_thread(self._history_sync, symbol.upper(), limit)

    def _history_sync(self, symbol: str, limit: int) -> pd.DataFrame:
        path = HISTORY_DIR / f"{symbol}.csv"
        if path.exists():
            df = self._read_history_file(path)
        else:
            df = self._download_symbol_history(symbol)
        df = self._merge_latest_idx_snapshot(symbol, df)
        if df.empty:
            raise FileNotFoundError(f"No real daily history available for {symbol}.")
        return df.tail(limit).reset_index(drop=True)

    def _read_history_file(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        if not set(required).issubset(df.columns):
            raise ValueError(f"Invalid history cache: {path.name}")
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=required).reset_index(drop=True)

    def _download_symbol_history(self, symbol: str) -> pd.DataFrame:
        ticker = f"{symbol}.JK"
        data = yf.download(
            ticker,
            period=REAL_EOD_HISTORY_PERIOD,
            interval="1d",
            auto_adjust=False,
            repair=True,
            progress=False,
            threads=False,
        )
        if data is None or data.empty:
            raise FileNotFoundError(f"Yahoo Finance returned no history for {ticker}.")
        # Single-ticker downloads can still return MultiIndex columns in newer yfinance.
        if isinstance(data.columns, pd.MultiIndex):
            if ticker in data.columns.get_level_values(-1):
                try:
                    data = data.xs(ticker, axis=1, level=-1)
                except Exception:
                    pass
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [str(c[0]) for c in data.columns]
        data = data.reset_index()
        mapping = {str(c).lower(): c for c in data.columns}
        out = pd.DataFrame({
            "timestamp": pd.to_datetime(data[mapping.get("date") or mapping.get("datetime")]).dt.strftime("%Y-%m-%d"),
            "open": pd.to_numeric(data[mapping["open"]], errors="coerce"),
            "high": pd.to_numeric(data[mapping["high"]], errors="coerce"),
            "low": pd.to_numeric(data[mapping["low"]], errors="coerce"),
            "close": pd.to_numeric(data[mapping["close"]], errors="coerce"),
            "volume": pd.to_numeric(data[mapping["volume"]], errors="coerce"),
        }).dropna()
        if out.empty:
            raise FileNotFoundError(f"No usable OHLCV rows for {ticker}.")
        out.to_csv(HISTORY_DIR / f"{symbol}.csv", index=False)
        return out

    def _load_snapshot(self) -> dict:
        if not LATEST_SNAPSHOT_PATH.exists():
            return {}
        try:
            payload = json.loads(LATEST_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _merge_latest_idx_snapshot(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        payload = self._load_snapshot()
        rows = payload.get("rows") or {}
        row = rows.get(symbol)
        if not row:
            return df
        date = str(payload.get("session_date") or str(row.get("date", ""))[:10])
        if not date or row.get("close") is None:
            return df
        record = {
            "timestamp": date,
            "open": row.get("open") or row.get("close"),
            "high": row.get("high") or row.get("close"),
            "low": row.get("low") or row.get("close"),
            "close": row.get("close"),
            "volume": row.get("volume") or 0,
        }
        merged = df.copy()
        merged["timestamp"] = merged["timestamp"].astype(str).str.slice(0, 10)
        merged = merged[merged["timestamp"] != date]
        merged = pd.concat([merged, pd.DataFrame([record])], ignore_index=True)
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        return merged

    async def quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        payload = await asyncio.to_thread(self._load_snapshot)
        row = (payload.get("rows") or {}).get(symbol)
        if row and row.get("close") is not None:
            close = float(row["close"])
            previous = float(row.get("previous") or close)
            bid = _float_or_none(row.get("bid"))
            offer = _float_or_none(row.get("offer"))
            bid_volume = _float_or_none(row.get("bid_volume"))
            offer_volume = _float_or_none(row.get("offer_volume"))
            return Quote(
                symbol=symbol,
                last=close,
                previous=previous,
                volume=float(row.get("volume") or 0),
                bid=bid,
                offer=offer,
                # IDX queue volumes are represented in lots on the summary endpoint;
                # convert to approximate rupiah notional using 100 shares/lot.
                bid_value=(bid * bid_volume * 100) if bid is not None and bid_volume is not None else None,
                offer_value=(offer * offer_volume * 100) if offer is not None and offer_volume is not None else None,
                timestamp=str(payload.get("session_date") or row.get("date") or ""),
            )
        df = await self.history(symbol, 2)
        last = float(df.iloc[-1].close)
        prev = float(df.iloc[-2].close) if len(df) > 1 else last
        return Quote(
            symbol=symbol,
            last=last,
            previous=prev,
            volume=float(df.iloc[-1].volume),
            timestamp=str(df.iloc[-1].timestamp),
        )

    async def refresh_reference_and_snapshot(self) -> dict:
        return await asyncio.to_thread(self._refresh_reference_and_snapshot_sync)

    def _append_session_to_history(self, session_date: str, summary: list[dict]) -> int:
        """Append one completed IDX session to existing local history caches.

        Only symbols that already have a historical CSV are touched. This keeps the
        initial Yahoo history as the long baseline while daily completed sessions are
        maintained from the IDX summary itself.
        """
        appended = 0
        for row in summary:
            symbol = str(row.get("symbol") or "").upper().strip()
            path = HISTORY_DIR / f"{symbol}.csv"
            if not symbol or not path.exists() or row.get("close") is None:
                continue
            try:
                df = self._read_history_file(path)
                date = str(session_date)[:10]
                df["timestamp"] = df["timestamp"].astype(str).str.slice(0, 10)
                record = {
                    "timestamp": date,
                    "open": row.get("open") or row.get("close"),
                    "high": row.get("high") or row.get("close"),
                    "low": row.get("low") or row.get("close"),
                    "close": row.get("close"),
                    "volume": row.get("volume") or 0,
                }
                df = df[df["timestamp"] != date]
                df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
                df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
                df.to_csv(path, index=False)
                appended += 1
            except Exception:
                continue
        return appended

    def _backfill_between(self, old_session: str | None, new_session: str) -> int:
        if not old_session or old_session >= new_session:
            return 0
        try:
            start = datetime.fromisoformat(old_session).date() + timedelta(days=1)
            end = datetime.fromisoformat(new_session).date()
        except ValueError:
            return 0
        appended = 0
        d = start
        while d <= end:
            if d.weekday() < 5:
                try:
                    rows = self.client.stock_summary(d.strftime("%Y%m%d"))
                    if len(rows) >= 100:
                        appended += self._append_session_to_history(d.isoformat(), rows)
                except Exception:
                    pass
            d += timedelta(days=1)
        return appended

    def _refresh_reference_and_snapshot_sync(self) -> dict:
        symbols = self._refresh_universe()
        previous = self._load_snapshot()
        old_session = previous.get("session_date") if isinstance(previous, dict) else None
        now = datetime.now(ZoneInfo("Asia/Jakarta"))
        session_date, summary = self.client.latest_completed_stock_summary(now)
        rows = {r["symbol"]: r for r in summary}

        # If the dashboard was closed for one or more sessions, fill those completed
        # daily bars into the existing history caches before replacing the snapshot.
        appended = self._backfill_between(old_session, session_date) if session_date != old_session else 0

        save_json(LATEST_SNAPSHOT_PATH, {
            "session_date": session_date,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "rows": rows,
        })
        return {
            "universe_count": len(symbols), "session_date": session_date,
            "summary_count": len(rows), "history_rows_appended": appended,
        }


def _float_or_none(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
