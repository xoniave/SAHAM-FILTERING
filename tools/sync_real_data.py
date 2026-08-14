from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, HISTORY_DIR, REAL_EOD_HISTORY_PERIOD
from app.market.real_eod_provider import RealEODProvider
from app.engine.analyzer import analyze_symbol


def normalize_one(symbol: str, ticker: str, frame: pd.DataFrame) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    df = frame.copy()
    if isinstance(df.columns, pd.MultiIndex):
        # group_by='ticker' -> ticker is normally first level.
        levels0 = set(map(str, df.columns.get_level_values(0)))
        levels1 = set(map(str, df.columns.get_level_values(-1)))
        try:
            if ticker in levels0:
                df = df[ticker]
            elif ticker in levels1:
                df = df.xs(ticker, axis=1, level=-1)
        except Exception:
            return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]) for c in df.columns]
    df = df.reset_index()
    mapping = {str(c).lower(): c for c in df.columns}
    date_col = mapping.get('date') or mapping.get('datetime')
    required = ['open','high','low','close','volume']
    if not date_col or not all(x in mapping for x in required):
        return None
    out = pd.DataFrame({
        'timestamp': pd.to_datetime(df[date_col]).dt.strftime('%Y-%m-%d'),
        'open': pd.to_numeric(df[mapping['open']], errors='coerce'),
        'high': pd.to_numeric(df[mapping['high']], errors='coerce'),
        'low': pd.to_numeric(df[mapping['low']], errors='coerce'),
        'close': pd.to_numeric(df[mapping['close']], errors='coerce'),
        'volume': pd.to_numeric(df[mapping['volume']], errors='coerce'),
    }).dropna()
    return out if len(out) >= 30 else None


def download_batch(batch: list[str]) -> tuple[int, list[str]]:
    tickers = [f"{s}.JK" for s in batch]
    data = yf.download(
        tickers,
        period=REAL_EOD_HISTORY_PERIOD,
        interval='1d',
        auto_adjust=False,
        repair=True,
        progress=False,
        group_by='ticker',
        threads=True,
    )
    ok = 0
    failed: list[str] = []
    for symbol, ticker in zip(batch, tickers):
        try:
            frame = data[ticker] if isinstance(data.columns, pd.MultiIndex) and ticker in set(map(str, data.columns.get_level_values(0))) else data
            out = normalize_one(symbol, ticker, frame)
            if out is None or out.empty:
                failed.append(symbol)
                continue
            out.to_csv(HISTORY_DIR / f"{symbol}.csv", index=False)
            ok += 1
        except Exception:
            failed.append(symbol)
    return ok, failed



def build_scanner_snapshot(provider: RealEODProvider, symbols: list[str]) -> tuple[int, list[str]]:
    latest_path = DATA_DIR / 'latest_idx_snapshot.json'
    latest = json.loads(latest_path.read_text(encoding='utf-8')) if latest_path.exists() else {}
    latest_rows = latest.get('rows') or {}
    output = []
    failed = []
    names_map={x.get('symbol'):x.get('name',x.get('symbol')) for x in provider._read_symbols()}
    for i, symbol in enumerate(symbols, start=1):
        try:
            df = provider._history_sync(symbol, 320)
            row = latest_rows.get(symbol)
            if row and row.get('close') is not None:
                last = float(row['close']); prev = float(row.get('previous') or last)
                quote = {
                    'symbol': symbol, 'last': last, 'previous': prev,
                    'change_pct': ((last-prev)/prev*100) if prev else 0.0,
                    'volume': float(row.get('volume') or 0), 'bid': row.get('bid'), 'offer': row.get('offer'),
                    'bid_value': None, 'offer_value': None, 'timestamp': latest.get('session_date'),
                }
            else:
                last=float(df.iloc[-1].close); prev=float(df.iloc[-2].close) if len(df)>1 else last
                quote={'symbol':symbol,'last':last,'previous':prev,'change_pct':((last-prev)/prev*100) if prev else 0.0,'volume':float(df.iloc[-1].volume),'bid':None,'offer':None,'bid_value':None,'offer_value':None,'timestamp':str(df.iloc[-1].timestamp)}
            a = analyze_symbol(symbol, df, quote, None)
            names=[]
            for pat in a.get('patterns', [])[-8:]:
                name=pat.get('name')
                if name and name not in names: names.append(name)
            output.append({
                'symbol': symbol,
                'name': names_map.get(symbol, symbol),
                'last': a['quote']['last'], 'change_pct': a['quote']['change_pct'],
                'macro_cycle': a['cycle']['macro'], 'local_cycle': a['cycle']['local'],
                'trend': a['structure']['trend'], 'rvol': a['volume']['rvol'],
                'decision': a['decision']['decision'], 'confidence': a['decision']['confidence'],
                'patterns': names[-2:],
            })
        except Exception as exc:
            failed.append(symbol)
            output.append({'symbol':symbol,'name':symbol,'decision':'DATA ERROR','error':str(exc)})
        if i % 100 == 0 or i == len(symbols):
            print(f'  analysis snapshot {i}/{len(symbols)}')
    payload={'session_date':latest.get('session_date'),'built_at':pd.Timestamp.utcnow().isoformat(),'rows':output}
    (DATA_DIR / 'scanner_snapshot.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return len(output)-len(failed), failed


def main() -> int:
    ap = argparse.ArgumentParser(description='Sync real IDX universe + completed EOD data + Yahoo daily history cache.')
    ap.add_argument('--batch-size', type=int, default=60)
    ap.add_argument('--limit', type=int, default=0, help='Optional test limit; 0 means all symbols.')
    ap.add_argument('--skip-history', action='store_true')
    args = ap.parse_args()

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    provider = RealEODProvider()
    started = perf_counter()

    print('[1/3] Refreshing official IDX listed-company universe and latest completed session...')
    ref = provider._refresh_reference_and_snapshot_sync()
    print(f"  Universe: {ref['universe_count']} | Latest completed session: {ref['session_date']} | Summary rows: {ref['summary_count']}")

    symbols = [x['symbol'] for x in provider._read_symbols()]
    if args.limit > 0:
        symbols = symbols[:args.limit]

    failed: list[str] = []
    downloaded = 0
    if not args.skip_history:
        print(f'[2/3] Downloading/caching {REAL_EOD_HISTORY_PERIOD} of daily OHLCV for {len(symbols)} IDX symbols via Yahoo Finance...')
        for i in range(0, len(symbols), max(1, args.batch_size)):
            batch = symbols[i:i+max(1,args.batch_size)]
            try:
                ok, bad = download_batch(batch)
            except Exception as exc:
                ok, bad = 0, batch
                print(f'  Batch {i+1}-{i+len(batch)} error: {exc}')
            downloaded += ok
            failed.extend(bad)
            print(f'  {min(i+len(batch),len(symbols))}/{len(symbols)} processed | cached {downloaded} | failed {len(failed)}')
    else:
        print('[2/3] History download skipped.')

    print('[3/4] Building scanner snapshot from cached real OHLCV...')
    analyzed, analysis_failed = build_scanner_snapshot(provider, symbols)
    print(f'  scanner snapshot ready: {analyzed} analyzed | {len(analysis_failed)} errors')

    report = {
        'universe_count': ref['universe_count'],
        'session_date': ref['session_date'],
        'history_requested': len(symbols),
        'history_cached': downloaded if not args.skip_history else None,
        'history_failed': sorted(set(failed)),
        'scanner_analyzed': analyzed,
        'scanner_failed': sorted(set(analysis_failed)),
        'history_period': REAL_EOD_HISTORY_PERIOD,
        'elapsed_seconds': round(perf_counter()-started,2),
    }
    (DATA_DIR / 'sync_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[4/4] Sync report saved to app/data/sync_report.json')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ref['universe_count'] >= 100 else 2


if __name__ == '__main__':
    raise SystemExit(main())
