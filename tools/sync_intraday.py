from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR


SYMBOLS_PATH = DATA_DIR / "symbols.csv"
EOD_SNAPSHOT_PATH = DATA_DIR / "latest_idx_snapshot.json"
OUT_PATH = DATA_DIR / "intraday_snapshot.json"

JAKARTA = ZoneInfo("Asia/Jakarta")


def load_symbols(limit: int = 0) -> list[str]:

    if not SYMBOLS_PATH.exists():
        raise FileNotFoundError(
            f"Belum ada {SYMBOLS_PATH}. Jalankan sync data real dulu."
        )

    df = pd.read_csv(SYMBOLS_PATH)

    symbols = (
        df["symbol"]
        .astype(str)
        .str.upper()
        .str.strip()
        .drop_duplicates()
        .tolist()
    )

    return symbols[:limit] if limit > 0 else symbols


def load_eod_snapshot() -> dict:

    if not EOD_SNAPSHOT_PATH.exists():
        return {}

    try:
        return json.loads(
            EOD_SNAPSHOT_PATH.read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def extract_ticker_frame(
    data: pd.DataFrame,
    ticker: str
) -> pd.DataFrame | None:

    if data is None or data.empty:
        return None

    frame = data

    if isinstance(data.columns, pd.MultiIndex):

        level0 = set(
            map(str, data.columns.get_level_values(0))
        )

        level_last = set(
            map(str, data.columns.get_level_values(-1))
        )

        try:

            if ticker in level0:
                frame = data[ticker].copy()

            elif ticker in level_last:
                frame = data.xs(
                    ticker,
                    axis=1,
                    level=-1
                ).copy()

            else:
                return None

        except Exception:
            return None

    else:
        frame = data.copy()

    if isinstance(frame.columns, pd.MultiIndex):

        frame.columns = [
            str(c[0])
            for c in frame.columns
        ]

    cols = {
        str(c).lower(): c
        for c in frame.columns
    }

    required = (
        "open",
        "high",
        "low",
        "close",
        "volume",
    )

    if not all(name in cols for name in required):
        return None

    out = pd.DataFrame(
        {
            "open": pd.to_numeric(
                frame[cols["open"]],
                errors="coerce",
            ),

            "high": pd.to_numeric(
                frame[cols["high"]],
                errors="coerce",
            ),

            "low": pd.to_numeric(
                frame[cols["low"]],
                errors="coerce",
            ),

            "close": pd.to_numeric(
                frame[cols["close"]],
                errors="coerce",
            ),

            "volume": pd.to_numeric(
                frame[cols["volume"]],
                errors="coerce",
            ).fillna(0),
        },

        index=frame.index,
    )

    out = out.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close",
        ]
    )

    return out if not out.empty else None


def timestamp_jakarta(value) -> pd.Timestamp:

    ts = pd.Timestamp(value)

    if ts.tzinfo is None:
        return ts

    return ts.tz_convert(JAKARTA)


def summarize_intraday(
    symbol: str,
    frame: pd.DataFrame,
    eod: dict
) -> dict:

    first = frame.iloc[0]
    last = frame.iloc[-1]

    last_ts = timestamp_jakarta(
        frame.index[-1]
    )

    session_date = last_ts.strftime(
        "%Y-%m-%d"
    )

    eod_date = str(
        eod.get("session_date") or ""
    )[:10]

    eod_row = (
        eod.get("rows") or {}
    ).get(symbol, {})

    if eod_date == session_date:

        previous = (
            eod_row.get("previous")
            or eod_row.get("close")
        )

    else:

        previous = (
            eod_row.get("close")
            or eod_row.get("previous")
        )

    last_price = float(
        last["close"]
    )

    previous = (
        float(previous)
        if previous not in (None, 0, "")
        else last_price
    )

    change_pct = (
        (last_price - previous)
        / previous
        * 100.0
        if previous
        else 0.0
    )

    return {

        "symbol": symbol,

        "session_date": session_date,

        "timestamp": last_ts.isoformat(),

        "open": float(
            first["open"]
        ),

        "high": float(
            frame["high"].max()
        ),

        "low": float(
            frame["low"].min()
        ),

        "last": last_price,

        "previous": previous,

        "change_pct": change_pct,

        "volume": float(
            frame["volume"].sum()
        ),

        "last_bar_volume": float(
            last["volume"]
        ),

        "bars": int(
            len(frame)
        ),
    }


def download_batch(
    batch: list[str],
    interval: str,
    period: str,
    eod: dict
) -> tuple[dict, list[str]]:

    tickers = [
        f"{symbol}.JK"
        for symbol in batch
    ]

    data = None
    last_error = None

    for attempt in range(2):

        try:

            data = yf.download(

                tickers=tickers,

                period=period,

                interval=interval,

                auto_adjust=False,

                repair=False,

                prepost=False,

                progress=False,

                group_by="ticker",

                threads=True,

                timeout=20,
            )

            if (
                data is not None
                and not data.empty
            ):
                break

        except Exception as exc:

            last_error = exc

        if attempt == 0:
            time.sleep(2)

    if (
        data is None
        or data.empty
    ):

        if last_error:
            print(
                f"download error: {last_error}"
            )

        return {}, batch

    rows: dict[str, dict] = {}

    failed: list[str] = []

    for symbol, ticker in zip(
        batch,
        tickers
    ):

        try:

            frame = extract_ticker_frame(
                data,
                ticker
            )

            if frame is None:

                failed.append(symbol)
                continue

            rows[symbol] = summarize_intraday(
                symbol,
                frame,
                eod
            )

        except Exception:

            failed.append(symbol)

        # Fallback:
    # saham yang tidak punya bar pada period=1d
    # dicoba lagi menggunakan history 5 hari.
    if failed and period == "1d":

        retry_symbols = failed.copy()

        retry_tickers = [
            f"{symbol}.JK"
            for symbol in retry_symbols
        ]

        try:

            retry_data = yf.download(
                tickers=retry_tickers,
                period="5d",
                interval=interval,
                auto_adjust=False,
                repair=False,
                prepost=False,
                progress=False,
                group_by="ticker",
                threads=True,
                timeout=20,
            )

            still_failed = []

            for symbol, ticker in zip(
                retry_symbols,
                retry_tickers
            ):

                try:

                    frame = extract_ticker_frame(
                        retry_data,
                        ticker
                    )

                    if frame is None:
                        still_failed.append(symbol)
                        continue

                    rows[symbol] = summarize_intraday(
                        symbol,
                        frame,
                        eod
                    )

                except Exception:
                    still_failed.append(symbol)

            failed = still_failed

        except Exception as exc:

            print(
                f"fallback 5d error: {exc}"
            )

    return rows, failed


def save_json(
    path: Path,
    payload: dict
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def main() -> int:

    ap = argparse.ArgumentParser(
        description=(
            "Ambil snapshot intraday IDX "
            "dari Yahoo Finance."
        )
    )

    ap.add_argument(
        "--batch-size",
        type=int,
        default=60,
    )

    ap.add_argument(
        "--limit",
        type=int,
        default=0,
    )

    ap.add_argument(
        "--interval",
        default="5m",
    )

    ap.add_argument(
        "--period",
        default="1d",
    )

    args = ap.parse_args()

    symbols = load_symbols(
        args.limit
    )

    eod = load_eod_snapshot()

    rows: dict[str, dict] = {}

    failed: list[str] = []

    started = time.perf_counter()

    print(
        f"[INTRADAY] "
        f"{len(symbols)} saham | "
        f"interval {args.interval}"
    )

    batch_size = max(
        1,
        args.batch_size
    )

    for start in range(
        0,
        len(symbols),
        batch_size
    ):

        batch = symbols[
            start:
            start + batch_size
        ]

        got, bad = download_batch(
            batch,
            args.interval,
            args.period,
            eod
        )

        rows.update(got)

        failed.extend(bad)

        done = min(
            start + len(batch),
            len(symbols)
        )

        print(
            f"{done}/{len(symbols)} | "
            f"intraday {len(rows)} | "
            f"gagal {len(failed)}"
        )

    session_dates = sorted(
        {
            row["session_date"]
            for row in rows.values()
            if row.get("session_date")
        }
    )

    payload = {

        "source":
            "Yahoo Finance via yfinance",

        "mode":
            "INTRADAY MONITORING",

        "interval":
            args.interval,

        "period":
            args.period,

        "fetched_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "fetched_at_jakarta":
            datetime.now(
                JAKARTA
            ).isoformat(),

        "session_dates":
            session_dates,

        "requested":
            len(symbols),

        "received":
            len(rows),

        "failed":
            sorted(set(failed)),

        "elapsed_seconds":
            round(
                time.perf_counter()
                - started,
                2
            ),

        "rows":
            rows,
    }

    save_json(
        OUT_PATH,
        payload
    )

    print(
        f"[OK] {OUT_PATH}"
    )

    print(
        f"received={len(rows)} "
        f"failed={len(set(failed))} "
        f"elapsed="
        f"{payload['elapsed_seconds']}s"
    )

    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())