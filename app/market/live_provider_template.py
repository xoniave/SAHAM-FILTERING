from __future__ import annotations

"""
Template for a licensed broker / IDX Data adapter.

Do not scrape a website into this class. Implement the provider's documented
API/WebSocket protocol here, then the rest of the dashboard remains unchanged.
"""

from .base import MarketDataProvider, Quote


class LiveProviderTemplate(MarketDataProvider):
    name = "live-template"
    is_live = True

    async def list_symbols(self) -> list[dict]:
        raise NotImplementedError("Connect to the licensed provider's symbol master.")

    async def history(self, symbol: str, limit: int = 320):
        raise NotImplementedError("Connect to provider historical OHLCV.")

    async def quote(self, symbol: str) -> Quote:
        raise NotImplementedError("Connect to provider quote endpoint.")

    async def stream_quotes(self, symbols: list[str]):
        raise NotImplementedError("Connect to provider WebSocket / streaming feed.")
