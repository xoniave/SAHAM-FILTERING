from __future__ import annotations

from functools import lru_cache

from .base import MarketDataProvider
from .demo_provider import DemoProvider
from .csv_provider import CSVProvider
from ..config import MARKET_PROVIDER


@lru_cache(maxsize=1)
def get_provider() -> MarketDataProvider:
    if MARKET_PROVIDER == "csv":
        return CSVProvider()
    if MARKET_PROVIDER in {"real_eod", "eod", "real"}:
        from .real_eod_provider import RealEODProvider
        return RealEODProvider()
    return DemoProvider()
