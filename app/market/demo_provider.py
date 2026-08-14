from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import math
import random

import numpy as np
import pandas as pd

from .base import MarketDataProvider, Quote


SYMBOLS = [
    ("AALI", "Astra Agro Lestari Tbk."), ("ACES", "Aspirasi Hidup Indonesia Tbk."),
    ("ADRO", "Alamtri Resources Indonesia Tbk."), ("AKRA", "AKR Corporindo Tbk."),
    ("AMMN", "Amman Mineral Internasional Tbk."), ("ANTM", "Aneka Tambang Tbk."),
    ("ASII", "Astra International Tbk."), ("BBCA", "Bank Central Asia Tbk."),
    ("BBNI", "Bank Negara Indonesia (Persero) Tbk."), ("BBRI", "Bank Rakyat Indonesia (Persero) Tbk."),
    ("BMRI", "Bank Mandiri (Persero) Tbk."), ("BRIS", "Bank Syariah Indonesia Tbk."),
    ("BRMS", "Bumi Resources Minerals Tbk."), ("BUMI", "Bumi Resources Tbk."),
    ("CPIN", "Charoen Pokphand Indonesia Tbk."), ("ERAA", "Erajaya Swasembada Tbk."),
    ("EXCL", "XLSMART Telecom Sejahtera Tbk."), ("GOTO", "GoTo Gojek Tokopedia Tbk."),
    ("ICBP", "Indofood CBP Sukses Makmur Tbk."), ("INCO", "Vale Indonesia Tbk."),
    ("INDF", "Indofood Sukses Makmur Tbk."), ("MDKA", "Merdeka Copper Gold Tbk."),
    ("PGAS", "Perusahaan Gas Negara Tbk."), ("PTBA", "Bukit Asam Tbk."),
    ("TLKM", "Telkom Indonesia (Persero) Tbk."), ("UNTR", "United Tractors Tbk."),
]


class DemoProvider(MarketDataProvider):
    name = "demo"
    is_live = False
    analysis_enabled = False
    data_mode = "DEMO"

    def __init__(self) -> None:
        self._cache: dict[str, pd.DataFrame] = {}
        self._rng = random.Random(20260814)

    async def list_symbols(self) -> list[dict]:
        return [{"symbol": s, "name": n} for s, n in SYMBOLS]

    def _seed(self, symbol: str) -> int:
        return sum((i + 1) * ord(c) for i, c in enumerate(symbol))

    def _generate(self, symbol: str, bars: int = 340) -> pd.DataFrame:
        seed = self._seed(symbol)
        rng = np.random.default_rng(seed)
        start_prices = {
            "EXCL": 2300, "BBRI": 3900, "BBCA": 9400, "BRMS": 320, "ANTM": 2600,
            "BUMI": 180, "TLKM": 2900, "BMRI": 5500, "ADRO": 2100, "ACES": 600,
        }
        p0 = start_prices.get(symbol, 700 + (seed % 5000))
        dates = [datetime(2025, 4, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(bars)]
        # Keep weekdays to make the visual feel like market data, while still demo only.
        dates = [d for d in dates if d.weekday() < 5]
        n = len(dates)

        # Build regime sequences so the rule engine has meaningful structures to detect.
        if symbol == "EXCL":
            anchors = [
                (0, 2300), (45, 2220), (85, 2260), (120, 2800), (150, 2550),
                (185, 4300), (205, 2900), (225, 3250), (250, 2400), (n - 12, 2460), (n - 1, 2780),
            ]
        elif symbol in {"BRMS", "BRIS", "BBNI", "ACES"}:
            anchors = [(0, p0), (70, p0 * 0.97), (120, p0 * 1.02), (175, p0 * 1.18), (n - 30, p0 * 1.16), (n - 1, p0 * 1.31)]
        elif symbol in {"BUMI", "AMMN", "PTBA"}:
            anchors = [(0, p0 * 1.25), (75, p0 * 1.18), (135, p0 * 1.30), (185, p0 * 1.10), (n - 1, p0 * 0.82)]
        else:
            anchors = [(0, p0), (70, p0 * 0.98), (125, p0 * 1.03), (190, p0 * 1.16), (n - 30, p0 * 1.10), (n - 1, p0 * 1.14)]

        base = np.zeros(n)
        for (i0, v0), (i1, v1) in zip(anchors, anchors[1:]):
            i0, i1 = min(i0, n - 1), min(i1, n - 1)
            if i1 <= i0:
                continue
            base[i0:i1 + 1] = np.linspace(v0, v1, i1 - i0 + 1)
        if base[0] == 0:
            base[:] = p0
        base[base == 0] = np.interp(np.flatnonzero(base == 0), np.flatnonzero(base != 0), base[base != 0])
        noise = rng.normal(0, 0.018, n)
        close = np.maximum(10, base * (1 + noise))
        open_ = close * (1 + rng.normal(0, 0.008, n))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.010, 0.008, n)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.010, 0.008, n)))

        vol_base = 8_000_000 + (seed % 25_000_000)
        vol = vol_base * np.maximum(0.25, 1 + rng.normal(0, 0.35, n))
        # Breakout / stress regimes receive higher volume.
        returns = np.r_[0, np.abs(np.diff(close) / close[:-1])]
        vol *= 1 + np.clip(returns * 15, 0, 2.5)
        if symbol == "EXCL":
            vol[-1] = 13_150_000

        frame = pd.DataFrame({
            "timestamp": [d.isoformat() for d in dates],
            "open": open_, "high": high, "low": low, "close": close, "volume": vol,
        })
        return frame.round({"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0})

    async def history(self, symbol: str, limit: int = 320) -> pd.DataFrame:
        symbol = symbol.upper()
        if symbol not in self._cache:
            self._cache[symbol] = self._generate(symbol)
        return self._cache[symbol].tail(limit).copy().reset_index(drop=True)

    async def quote(self, symbol: str) -> Quote:
        df = await self.history(symbol, 3)
        last = float(df.iloc[-1]["close"])
        previous = float(df.iloc[-2]["close"])
        volume = float(df.iloc[-1]["volume"])
        tick = max(1.0, round(last * 0.001))
        return Quote(
            symbol=symbol.upper(), last=last, previous=previous, volume=volume,
            bid=max(tick, last - tick), offer=last + tick,
            bid_value=500_000_000.0, offer_value=480_000_000.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def stream_quotes(self, symbols: list[str]):
        prices = {}
        for s in symbols:
            q = await self.quote(s)
            prices[s] = q.last
        while True:
            await asyncio.sleep(2)
            for s in symbols:
                last = prices[s]
                drift = self._rng.uniform(-0.0025, 0.0025)
                next_price = max(1.0, round(last * (1 + drift)))
                prices[s] = next_price
                yield Quote(
                    symbol=s, last=next_price, previous=last, volume=0,
                    bid=max(1.0, next_price - 1), offer=next_price + 1,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
