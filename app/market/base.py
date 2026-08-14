from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

import pandas as pd


@dataclass(slots=True)
class Quote:
    symbol: str
    last: float
    previous: float
    volume: float
    bid: float | None = None
    offer: float | None = None
    bid_value: float | None = None
    offer_value: float | None = None
    timestamp: str | None = None

    @property
    def change_pct(self) -> float:
        if not self.previous:
            return 0.0
        return (self.last - self.previous) / self.previous * 100.0


class MarketDataProvider(ABC):
    name: str = "base"
    is_live: bool = False
    analysis_enabled: bool = True
    data_mode: str = "UNKNOWN"

    @abstractmethod
    async def list_symbols(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def history(self, symbol: str, limit: int = 320) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    async def quote(self, symbol: str) -> Quote:
        raise NotImplementedError

    async def stream_quotes(self, symbols: list[str]) -> AsyncIterator[Quote]:
        if False:
            yield  # pragma: no cover
        return
