from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    STATIC_DIR, MAX_HISTORY_BARS, DATA_DIR, HISTORY_DIR,
    AUTO_EOD_SYNC, AUTO_EOD_CHECK_SECONDS,
)
from .db import init_db, connect, utc_now
from .models import PortfolioCreate, PortfolioUpdate
from .market.service import get_provider
from .engine.analyzer import analyze_symbol
from .rulebook import RULEBOOK

app = FastAPI(title="IDX Decision Dashboard", version="4.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_scanner_cache: list[dict] = []
_scanner_cache_time: float = 0.0
_scanner_lock = asyncio.Lock()
_scan_task: asyncio.Task | None = None
_auto_sync_task: asyncio.Task | None = None
_scan_state: dict[str, Any] = {
    "status": "idle", "processed": 0, "total": 0, "percent": 0.0,
    "errors": 0, "started_at": None, "finished_at": None, "message": "Belum ada scan aktif.",
}
_auto_sync_state: dict[str, Any] = {
    "status": "idle", "last_check": None, "last_update": None, "message": "Pembaruan EOD otomatis siap.",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
async def startup() -> None:
    global _scanner_cache, _scanner_cache_time, _auto_sync_task
    init_db()
    prebuilt = _prebuilt_scanner_snapshot()
    if prebuilt:
        _scanner_cache = prebuilt
        _scanner_cache_time = time.monotonic()
    if AUTO_EOD_SYNC:
        _auto_sync_task = asyncio.create_task(_auto_eod_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    for task in (_scan_task, _auto_sync_task):
        if task and not task.done():
            task.cancel()


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


def row_to_position(row) -> dict | None:
    if row is None:
        return None
    return {"id": row["id"], "symbol": row["symbol"], "average_entry": row["average_entry"], "lots": row["lots"], "style": row["style"]}


def get_position(symbol: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM portfolio WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol.upper(),)).fetchone()
    return row_to_position(row)


def _snapshot_meta() -> dict:
    path = DATA_DIR / "latest_idx_snapshot.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "latest_session": payload.get("session_date"),
            "snapshot_fetched_at": payload.get("fetched_at"),
            "snapshot_rows": len(payload.get("rows") or {}),
        }
    except Exception:
        return {}


def _prebuilt_scanner_snapshot() -> list[dict]:
    path = DATA_DIR / "scanner_snapshot.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        latest = _snapshot_meta().get("latest_session")
        # If the scanner snapshot is older than the newest EOD snapshot, keep it visible
        # while a background rescan runs. This prevents the table from disappearing.
        rows = payload.get("rows") or []
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _write_scanner_snapshot(rows: list[dict]) -> None:
    payload = {
        "session_date": _snapshot_meta().get("latest_session"),
        "built_at": _iso_now(),
        "rows": rows,
    }
    path = DATA_DIR / "scanner_snapshot.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


async def analyze(symbol: str) -> dict[str, Any]:
    provider = get_provider()
    try:
        raw = await provider.history(symbol.upper(), MAX_HISTORY_BARS)
        q = await provider.quote(symbol.upper())
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    position = get_position(symbol)
    quote = {
        "symbol": q.symbol, "last": q.last, "previous": q.previous, "change_pct": q.change_pct,
        "volume": q.volume, "bid": q.bid, "offer": q.offer, "bid_value": q.bid_value,
        "offer_value": q.offer_value, "timestamp": q.timestamp,
    }
    result = analyze_symbol(symbol.upper(), raw, quote, position)
    result["data_source"] = {
        "provider": provider.name,
        "data_mode": provider.data_mode,
        "is_live": provider.is_live,
        "analysis_enabled": provider.analysis_enabled,
    }
    if not provider.analysis_enabled:
        result["patterns"] = []
        result["annotations"] = [z for z in result.get("annotations", []) if z.get("kind") not in {"pattern", "breakout", "breakdown"}]
        result["decision"] = {
            "decision": "DEMO — ANALISIS DIMATIKAN",
            "confidence": "—",
            "reasons": ["Data synthetic hanya untuk uji tampilan; keputusan entry/exit dimatikan."],
            "warnings": ["Gunakan provider REAL EOD atau CSV sebelum menilai rule trading."],
            "next_trigger": "Sinkronkan data nyata terlebih dahulu.",
        }
    return result


async def _scanner_row(item: dict) -> dict:
    try:
        a = await analyze(item["symbol"])
        pattern_names: list[str] = []
        for p in a.get("patterns", [])[-8:]:
            name = p.get("name")
            if name and name not in pattern_names:
                pattern_names.append(name)
        return {
            "symbol": item["symbol"], "name": item.get("name", item["symbol"]),
            "last": a["quote"]["last"], "change_pct": a["quote"]["change_pct"],
            "macro_cycle": a["cycle"]["macro"], "local_cycle": a["cycle"]["local"],
            "trend": a["structure"]["trend"], "rvol": a["volume"]["rvol"],
            "decision": a["decision"]["decision"], "confidence": a["decision"]["confidence"],
            "patterns": pattern_names[-2:],
        }
    except Exception as exc:
        return {
            "symbol": item["symbol"], "name": item.get("name", item["symbol"]),
            "error": str(exc), "decision": "DATA ERROR",
        }


async def _background_scan() -> None:
    global _scanner_cache, _scanner_cache_time, _scan_state
    provider = get_provider()
    universe = await provider.list_symbols()
    total = len(universe)
    _scan_state = {
        "status": "running", "processed": 0, "total": total, "percent": 0.0,
        "errors": 0, "started_at": _iso_now(), "finished_at": None,
        "message": "Scanning seluruh universe IDX…",
    }

    sem = asyncio.Semaphore(12)
    results: list[dict | None] = [None] * total

    async def bounded(index: int, item: dict):
        async with sem:
            return index, await _scanner_row(item)

    tasks = [asyncio.create_task(bounded(i, item)) for i, item in enumerate(universe)]
    try:
        for fut in asyncio.as_completed(tasks):
            idx, row = await fut
            results[idx] = row
            _scan_state["processed"] += 1
            if row.get("decision") == "DATA ERROR":
                _scan_state["errors"] += 1
            _scan_state["percent"] = round(_scan_state["processed"] / max(total, 1) * 100, 1)
            _scan_state["message"] = f"Memindai {_scan_state['processed']}/{total} saham"
        rows = [x for x in results if x is not None]
        _scanner_cache = rows
        _scanner_cache_time = time.monotonic()
        await asyncio.to_thread(_write_scanner_snapshot, rows)
        _scan_state.update({
            "status": "done", "percent": 100.0, "finished_at": _iso_now(),
            "message": f"Scan selesai: {len(rows)} saham, {_scan_state['errors']} error.",
        })
    except asyncio.CancelledError:
        _scan_state.update({"status": "cancelled", "finished_at": _iso_now(), "message": "Scan dibatalkan."})
        raise
    except Exception as exc:
        _scan_state.update({"status": "error", "finished_at": _iso_now(), "message": f"Scan gagal: {exc}"})
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def _start_scan_if_needed(force: bool = False) -> dict:
    global _scan_task
    if _scan_task and not _scan_task.done():
        return _scan_state
    if not force and _scanner_cache:
        return _scan_state
    _scan_task = asyncio.create_task(_background_scan())
    return _scan_state


async def _auto_eod_loop() -> None:
    global _auto_sync_state
    # First check shortly after startup; subsequent checks happen periodically.
    await asyncio.sleep(8)
    while True:
        try:
            provider = get_provider()
            if provider.name == "real_eod":
                before = _snapshot_meta().get("latest_session")
                _auto_sync_state.update({"status": "checking", "last_check": _iso_now(), "message": "Memeriksa sesi EOD terbaru…"})
                ref = await provider.refresh_reference_and_snapshot()
                after = ref.get("session_date")
                if after and after != before:
                    _auto_sync_state.update({"status": "updated", "last_update": _iso_now(), "message": f"Data EOD diperbarui ke {after}; scan ulang dimulai."})
                    await _start_scan_if_needed(force=True)
                else:
                    _auto_sync_state.update({"status": "idle", "message": f"Data EOD sudah terbaru ({after or before or 'belum ada'})."})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _auto_sync_state.update({"status": "error", "last_check": _iso_now(), "message": f"Cek EOD otomatis gagal: {exc}"})
        await asyncio.sleep(max(300, AUTO_EOD_CHECK_SECONDS))


@app.get("/api/status")
async def status():
    p = get_provider()
    symbols = await p.list_symbols()
    history_count = len(list(HISTORY_DIR.glob("*.csv")))
    meta = _snapshot_meta()
    return {
        "provider": p.name,
        "data_mode": p.data_mode,
        "is_live": p.is_live,
        "analysis_enabled": p.analysis_enabled,
        "universe_count": len(symbols),
        "history_cached_count": history_count,
        "sync_required": p.name == "real_eod" and (len(symbols) < 100 or history_count < 100),
        "auto_eod_sync": AUTO_EOD_SYNC,
        "auto_eod_check_seconds": AUTO_EOD_CHECK_SECONDS,
        "auto_sync": _auto_sync_state,
        "scan": _scan_state,
        **meta,
        "message": (
            "Feed real-time broker/licensed terhubung." if p.is_live else
            "Data sesi selesai (EOD) nyata; bukan data intraday real-time." if p.analysis_enabled else
            "Data demo: analisis trading dimatikan."
        ),
    }


@app.get("/api/symbols")
async def symbols(search: str = ""):
    items = await get_provider().list_symbols()
    q = search.strip().lower()
    if q:
        items = [x for x in items if q in x["symbol"].lower() or q in x.get("name", "").lower()]
    return items


@app.get("/api/analyze/{symbol}")
async def analyze_route(symbol: str):
    return await analyze(symbol)


@app.get("/api/scanner")
async def scanner(search: str = "", limit: int = 1200):
    global _scanner_cache, _scanner_cache_time
    if not _scanner_cache:
        prebuilt = _prebuilt_scanner_snapshot()
        if prebuilt:
            _scanner_cache = prebuilt
            _scanner_cache_time = time.monotonic()
        else:
            await _start_scan_if_needed(force=True)
    rows = _scanner_cache
    q = search.strip().lower()
    if q:
        rows = [x for x in rows if q in x.get("symbol", "").lower() or q in x.get("name", "").lower()]
    return rows[:max(1, min(limit, 1500))]


@app.post("/api/scan/start")
async def scan_start():
    return await _start_scan_if_needed(force=True)


@app.get("/api/scan/status")
async def scan_status():
    return _scan_state


@app.get("/api/classifications")
async def classifications():
    rows = _scanner_cache or _prebuilt_scanner_snapshot()
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(row.get("decision", "UNKNOWN"), []).append(row)
    return groups


@app.post("/api/refresh-scan")
async def refresh_scan():
    return await _start_scan_if_needed(force=True)


@app.get("/api/portfolio")
async def portfolio_list():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM portfolio ORDER BY created_at DESC").fetchall()
    output = []
    for row in rows:
        p = row_to_position(row)
        try:
            a = await analyze(row["symbol"])
            p["last"] = a["quote"]["last"]
            p["pnl_pct"] = (p["last"] - p["average_entry"]) / p["average_entry"] * 100
            p["decision"] = a["decision"]
            p["cycle"] = a["cycle"]
        except Exception as exc:
            p["error"] = str(exc)
        output.append(p)
    return output


@app.post("/api/portfolio")
async def portfolio_create(payload: PortfolioCreate):
    symbol = payload.symbol.upper().strip()
    with connect() as conn:
        conn.execute(
            "INSERT INTO portfolio(symbol,average_entry,lots,style,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(symbol,style) DO UPDATE SET average_entry=excluded.average_entry,lots=excluded.lots,created_at=excluded.created_at",
            (symbol, payload.average_entry, payload.lots, payload.style, utc_now()),
        )
    return {"ok": True, "symbol": symbol}


@app.patch("/api/portfolio/{portfolio_id}")
async def portfolio_update(portfolio_id: int, payload: PortfolioUpdate):
    fields = []
    values = []
    if payload.average_entry is not None:
        fields.append("average_entry=?"); values.append(payload.average_entry)
    if payload.lots is not None:
        fields.append("lots=?"); values.append(payload.lots)
    if payload.style is not None:
        fields.append("style=?"); values.append(payload.style)
    if not fields:
        return {"ok": True}
    values.append(portfolio_id)
    with connect() as conn:
        conn.execute(f"UPDATE portfolio SET {', '.join(fields)} WHERE id=?", values)
    return {"ok": True}


@app.delete("/api/portfolio/{portfolio_id}")
async def portfolio_delete(portfolio_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM portfolio WHERE id=?", (portfolio_id,))
    return {"ok": True}


@app.get("/api/rulebook")
async def rulebook():
    return RULEBOOK


@app.websocket("/ws/quotes")
async def ws_quotes(ws: WebSocket):
    await ws.accept()
    provider = get_provider()
    if not provider.is_live:
        await ws.send_json({"error": f"Provider {provider.data_mode} bukan real-time."})
        await ws.close()
        return
    try:
        query = ws.query_params.get("symbols", "EXCL,BBRI,BBCA")
        symbols = [x.strip().upper() for x in query.split(",") if x.strip()][:30]
        async for q in provider.stream_quotes(symbols):
            await ws.send_json({
                "symbol": q.symbol, "last": q.last, "previous": q.previous,
                "change_pct": q.change_pct, "timestamp": q.timestamp,
            })
    except WebSocketDisconnect:
        return
    except NotImplementedError:
        await ws.send_json({"error": "Provider yang dipilih belum mendukung streaming."})
        await ws.close()
