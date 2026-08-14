from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from curl_cffi import requests


DEFAULT_BASE_URL = "https://www.idx.co.id/primary"
DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "referer": "https://www.idx.co.id/",
}


class IDXRequestError(RuntimeError):
    pass


@dataclass(slots=True)
class IDXWebClient:
    """
    Small client for the public IDX website endpoints used by idx.co.id itself.

    Important: this is NOT the licensed IDX real-time market-data feed. It is used
    only for listed-company reference data and completed-session stock summaries.
    """

    base_url: str = DEFAULT_BASE_URL
    delay_seconds: float = 0.20
    max_retries: int = 3

    def _get_json(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.get(
                    url,
                    params=params,
                    headers=DEFAULT_HEADERS,
                    impersonate="chrome",
                    timeout=35,
                )
                if r.status_code == 200:
                    time.sleep(self.delay_seconds)
                    return r.json()
                last_error = f"HTTP {r.status_code}: {r.text[:180]}"
                if r.status_code not in {429, 500, 502, 503, 504}:
                    break
            except Exception as exc:  # pragma: no cover - network specific
                last_error = str(exc)
            if attempt < self.max_retries:
                time.sleep(min(8.0, 1.0 + 2**attempt))
        raise IDXRequestError(f"IDX request failed for {endpoint}: {last_error or 'unknown error'}")

    def company_profiles(self) -> list[dict]:
        payload = self._get_json(
            "/ListedCompany/GetCompanyProfiles",
            {"start": 0, "length": 9999},
        )
        data = payload.get("data") or payload.get("Data") or []
        result: list[dict] = []
        for row in data:
            code = str(row.get("KodeEmiten") or row.get("Code") or "").strip().upper()
            if not code:
                continue
            result.append(
                {
                    "symbol": code,
                    "name": str(row.get("NamaEmiten") or row.get("NamaPerusahaan") or row.get("CompanyName") or code).strip(),
                    "sector": str(row.get("Sektor") or "").strip(),
                    "subsector": str(row.get("SubSektor") or "").strip(),
                    "industry": str(row.get("Industri") or "").strip(),
                    "subindustry": str(row.get("SubIndustri") or "").strip(),
                    "board": str(row.get("PapanPencatatan") or "").strip(),
                }
            )
        if len(result) < 100:
            raise IDXRequestError(f"IDX company profile response looked incomplete ({len(result)} rows).")
        return result

    def stock_summary(self, yyyymmdd: str) -> list[dict]:
        payload = self._get_json(
            "/TradingSummary/GetStockSummary",
            {"date": yyyymmdd, "start": 0, "length": 9999},
        )
        data = payload.get("data") or payload.get("Data") or []
        result: list[dict] = []
        for row in data:
            code = str(row.get("StockCode") or "").strip().upper()
            if not code:
                continue
            result.append(
                {
                    "symbol": code,
                    "name": str(row.get("StockName") or code).strip(),
                    "date": str(row.get("Date") or yyyymmdd),
                    "previous": _num(row.get("Previous")),
                    "open": _num(row.get("OpenPrice")),
                    "high": _num(row.get("High")),
                    "low": _num(row.get("Low")),
                    "close": _num(row.get("Close")),
                    "volume": _num(row.get("Volume")),
                    "value": _num(row.get("Value")),
                    "frequency": _num(row.get("Frequency")),
                    "bid": _num(row.get("Bid")),
                    "offer": _num(row.get("Offer")),
                    "bid_volume": _num(row.get("BidVolume")),
                    "offer_volume": _num(row.get("OfferVolume")),
                    "foreign_buy": _num(row.get("ForeignBuy")),
                    "foreign_sell": _num(row.get("ForeignSell")),
                }
            )
        return result

    def latest_completed_stock_summary(self, now_jakarta: datetime, lookback_days: int = 12) -> tuple[str, list[dict]]:
        """Find the most recent completed session conservatively.

        Before 18:00 WIB we start from the previous calendar day to avoid treating
        an in-progress session as final EOD. After 18:00 WIB we may try today.
        """
        start = now_jakarta.date()
        if now_jakarta.hour < 18:
            start -= timedelta(days=1)
        last_error: Exception | None = None
        for offset in range(lookback_days):
            d = start - timedelta(days=offset)
            if d.weekday() >= 5:
                continue
            key = d.strftime("%Y%m%d")
            try:
                rows = self.stock_summary(key)
            except Exception as exc:  # pragma: no cover - network specific
                last_error = exc
                continue
            # A normal IDX session should have hundreds of stock rows.
            if len(rows) >= 100:
                return d.isoformat(), rows
        raise IDXRequestError(f"Could not find a completed IDX stock-summary session. Last error: {last_error}")


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
