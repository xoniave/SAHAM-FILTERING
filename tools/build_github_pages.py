from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.config import (
    DATA_DIR,
    HISTORY_DIR,
    STATIC_DIR,
    MAX_HISTORY_BARS,
)

from app.engine.analyzer import analyze_symbol
from app.rulebook import RULEBOOK


SITE_DIR = ROOT / "site"
SITE_STATIC = SITE_DIR / "static"
SITE_DATA = SITE_DIR / "data"
ANALYZE_DIR = SITE_DATA / "analyze"


def read_json(path: Path) -> dict:

    if not path.exists():
        return {}

    try:

        obj = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        return (
            obj
            if isinstance(obj, dict)
            else {}
        )

    except Exception:

        return {}


def write_json(
    path: Path,
    value
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":")
        ),
        encoding="utf-8"
    )


def load_history(
    symbol: str
) -> pd.DataFrame:

    path = (
        HISTORY_DIR
        / f"{symbol}.csv"
    )

    if not path.exists():

        raise FileNotFoundError(
            f"History {symbol} belum tersedia"
        )

    df = pd.read_csv(path)

    required = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    if not set(required).issubset(
        df.columns
    ):

        raise ValueError(
            f"Format history {symbol} "
            f"tidak valid"
        )

    for c in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:

        df[c] = pd.to_numeric(
            df[c],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    )

    return (
        df.tail(
            MAX_HISTORY_BARS
        )
        .reset_index(
            drop=True
        )
    )


def make_quote(
    symbol: str,
    df: pd.DataFrame,
    intraday: dict,
    eod: dict,
):

    intraday_row = (
        intraday.get(
            "rows"
        ) or {}
    ).get(symbol)

    # =====================================
    # PRIORITAS 1
    # harga intraday terbaru
    # =====================================

    if (
        intraday_row
        and
        intraday_row.get(
            "last"
        ) is not None
    ):

        last = float(
            intraday_row["last"]
        )

        previous = float(
            intraday_row.get(
                "previous"
            )
            or last
        )

        quote = {

            "symbol":
                symbol,

            "last":
                last,

            "previous":
                previous,

            "change_pct":
                float(
                    intraday_row.get(
                        "change_pct"
                    )
                    or 0
                ),

            "volume":
                float(
                    intraday_row.get(
                        "volume"
                    )
                    or 0
                ),

            "bid":
                None,

            "offer":
                None,

            "bid_value":
                None,

            "offer_value":
                None,

            "timestamp":
                (
                    intraday_row.get(
                        "timestamp"
                    )
                    or
                    intraday_row.get(
                        "session_date"
                    )
                ),
        }

        return (
            quote,
            intraday_row
        )

    # =====================================
    # PRIORITAS 2
    # EOD terakhir
    # =====================================

    eod_row = (
        eod.get(
            "rows"
        ) or {}
    ).get(symbol)

    if (
        eod_row
        and
        eod_row.get(
            "close"
        ) is not None
    ):

        last = float(
            eod_row["close"]
        )

        previous = float(
            eod_row.get(
                "previous"
            )
            or last
        )

        quote = {

            "symbol":
                symbol,

            "last":
                last,

            "previous":
                previous,

            "change_pct":
                (
                    (
                        last
                        - previous
                    )
                    / previous
                    * 100
                )
                if previous
                else 0,

            "volume":
                float(
                    eod_row.get(
                        "volume"
                    )
                    or 0
                ),

            "bid":
                None,

            "offer":
                None,

            "bid_value":
                None,

            "offer_value":
                None,

            "timestamp":
                (
                    eod.get(
                        "session_date"
                    )
                    or
                    eod_row.get(
                        "date"
                    )
                ),
        }

        return (
            quote,
            None
        )

    # =====================================
    # PRIORITAS 3
    # history CSV terakhir
    # =====================================

    last = float(
        df.iloc[-1].close
    )

    previous = (
        float(
            df.iloc[-2].close
        )
        if len(df) > 1
        else last
    )

    quote = {

        "symbol":
            symbol,

        "last":
            last,

        "previous":
            previous,

        "change_pct":
            (
                (
                    last
                    - previous
                )
                / previous
                * 100
            )
            if previous
            else 0,

        "volume":
            float(
                df.iloc[-1].volume
            ),

        "bid":
            None,

        "offer":
            None,

        "bid_value":
            None,

        "offer_value":
            None,

        "timestamp":
            str(
                df.iloc[-1].timestamp
            ),
    }

    return (
        quote,
        None
    )


def add_intraday_bar(
    analysis: dict,
    intraday_row
) -> None:

    if not intraday_row:

        return

    date = str(
        intraday_row.get(
            "session_date"
        )
        or ""
    )[:10]

    if not date:

        return

    bars = (
        analysis.get(
            "bars"
        )
        or []
    )

    # Kalau candle tanggal hari ini
    # sudah ada, jangan duplicate.

    if (
        bars
        and
        str(
            bars[-1].get(
                "timestamp",
                ""
            )
        )[:10]
        == date
    ):

        return

    bars.append({

        "index":
            int(
                analysis.get(
                    "current_index",
                    0
                )
            )
            + 1,

        "timestamp":
            date,

        "open":
            float(
                intraday_row.get(
                    "open"
                )
                or
                intraday_row.get(
                    "last"
                )
                or 0
            ),

        "high":
            float(
                intraday_row.get(
                    "high"
                )
                or
                intraday_row.get(
                    "last"
                )
                or 0
            ),

        "low":
            float(
                intraday_row.get(
                    "low"
                )
                or
                intraday_row.get(
                    "last"
                )
                or 0
            ),

        "close":
            float(
                intraday_row.get(
                    "last"
                )
                or 0
            ),

        "volume":
            float(
                intraday_row.get(
                    "volume"
                )
                or 0
            ),

        "ma20":
            None,

        "ma50":
            None,

        "ma100":
            None,

        "ma200":
            None,

        "partial_intraday":
            True,
    })

    analysis["bars"] = bars


def static_api_code() -> str:

    return r"""
async function api(url,options){

    const method =
        ((options && options.method) || 'GET')
        .toUpperCase();

    const getJson =
        async path => {

            const sep =
                path.includes('?')
                ? '&'
                : '?';

            const r =
                await fetch(
                    path
                    + sep
                    + 'v='
                    + Date.now(),
                    {
                        cache:'no-store'
                    }
                );

            if(!r.ok){
                throw new Error(
                    r.statusText
                );
            }

            return r.json();
        };


    if(url === '/api/status'){

        return getJson(
            'data/status.json'
        );
    }


    if(
        url.startsWith(
            '/api/scanner'
        )
    ){

        return getJson(
            'data/scanner.json'
        );
    }


    if(
        url === '/api/scan/status'
        ||
        url === '/api/scan/start'
    ){

        return getJson(
            'data/scan_status.json'
        );
    }


    if(
        url ===
        '/api/classifications'
    ){

        return getJson(
            'data/classifications.json'
        );
    }


    if(
        url ===
        '/api/rulebook'
    ){

        return getJson(
            'data/rulebook.json'
        );
    }


    if(
        url.startsWith(
            '/api/analyze/'
        )
    ){

        const symbol =
            decodeURIComponent(
                url.split('/').pop()
            )
            .toUpperCase();

        return getJson(
            `data/analyze/${symbol}.json`
        );
    }


    /*
       PORTFOLIO ONLINE

       Tidak masuk database GitHub.

       Disimpan hanya di browser
       masing-masing menggunakan
       localStorage.
    */

    const portfolioKey =
        'idx_dashboard_portfolio_v1';


    const readPortfolio = () => {

        try{

            return JSON.parse(
                localStorage.getItem(
                    portfolioKey
                )
                || '[]'
            );

        }catch{

            return [];
        }
    };


    const savePortfolio =
        rows => {

            localStorage.setItem(
                portfolioKey,
                JSON.stringify(rows)
            );
        };


    if(
        url === '/api/portfolio'
        &&
        method === 'GET'
    ){

        const output = [];

        for(
            const p
            of readPortfolio()
        ){

            const row = {
                ...p
            };

            try{

                const a =
                    await getJson(
                        `data/analyze/${p.symbol}.json`
                    );

                row.last =
                    a.quote.last;

                row.pnl_pct =
                    (
                        row.last
                        - row.average_entry
                    )
                    /
                    row.average_entry
                    * 100;

                row.decision =
                    a.decision;

                row.cycle =
                    a.cycle;

            }catch(e){

                row.error =
                    e.message;
            }

            output.push(
                row
            );
        }

        return output;
    }


    if(
        url === '/api/portfolio'
        &&
        method === 'POST'
    ){

        const body =
            JSON.parse(
                (
                    options
                    &&
                    options.body
                )
                || '{}'
            );

        let rows =
            readPortfolio();

        const index =
            rows.findIndex(
                x =>
                    x.symbol
                    === body.symbol
                    &&
                    x.style
                    === body.style
            );

        const row = {

            ...body,

            id:
                index >= 0
                ? rows[index].id
                : Date.now()
        };


        if(index >= 0){

            rows[index] =
                row;

        }else{

            rows.unshift(
                row
            );
        }


        savePortfolio(
            rows
        );

        return {
            ok:true
        };
    }


    if(
        url.startsWith(
            '/api/portfolio/'
        )
        &&
        method === 'DELETE'
    ){

        const id =
            Number(
                url.split('/').pop()
            );

        savePortfolio(
            readPortfolio()
            .filter(
                x =>
                    Number(x.id)
                    !== id
            )
        );

        return {
            ok:true
        };
    }


    throw new Error(
        'Endpoint static tidak tersedia: '
        + url
    );
}
"""


def build_frontend() -> None:

    SITE_STATIC.mkdir(
        parents=True,
        exist_ok=True
    )

    # =====================================
    # INDEX HTML
    # =====================================

    html = (
        STATIC_DIR
        / "index.html"
    ).read_text(
        encoding="utf-8"
    )

    # Absolute URL FastAPI
    # diubah menjadi relative GitHub Pages.

    html = html.replace(
        'href="/static/styles.css"',
        'href="static/styles.css"'
    )

    html = html.replace(
        'src="/static/app.js"',
        'src="static/app.js"'
    )

    (
        SITE_DIR
        / "index.html"
    ).write_text(
        html,
        encoding="utf-8"
    )

    shutil.copy2(
        STATIC_DIR
        / "styles.css",

        SITE_STATIC
        / "styles.css"
    )

    # =====================================
    # JAVASCRIPT
    # =====================================

    js = (
        STATIC_DIR
        / "app.js"
    ).read_text(
        encoding="utf-8"
    )

    old_api = (
        "async function api(url,options)"
        "{const r=await fetch(url,options);"
        "if(!r.ok){let msg=r.statusText;"
        "try{msg=(await r.json()).detail||msg}"
        "catch{}throw new Error(msg)}"
        "return r.json()}"
    )

    # str.replace mengganti seluruh
    # occurrence fungsi API FastAPI.

    js = js.replace(
        old_api,
        static_api_code()
    )

    # =====================================
    # LABEL MODE DATA
    # =====================================

    js = js.replace(

        "const liveLabel=s.is_live?"
        "'LIVE':"
        "(s.analysis_enabled?"
        "'EOD NYATA':"
        "'ANALISIS DIMATIKAN');",

        "const liveLabel="
        "s.intraday_monitoring?"
        "'MONITOR 5M':"
        "(s.is_live?"
        "'LIVE':"
        "(s.analysis_enabled?"
        "'EOD NYATA':"
        "'ANALISIS DIMATIKAN'));"
    )

    js = js.replace(

        "const src=a.data_source?"
        "`${a.data_source.data_mode}"
        "${a.data_source.is_live?"
        "' • LIVE':' • EOD'}`:'';",

        "const src=a.data_source?"
        "`${a.data_source.data_mode}"
        "${a.data_source.intraday_monitoring?"
        "' • MONITOR 5M':"
        "(a.data_source.is_live?"
        "' • LIVE':' • EOD')}`:'';"
    )

    js = js.replace(
        "Pembaruan EOD",
        "Pembaruan market"
    )

    # Penjelasan EOD lama diganti
    # dengan mode hybrid.

    old_notice = (
        "Mode EOD nyata.</b> "
        "Analisis memakai candle dari "
        "<b>sesi yang sudah selesai</b>"
        "${s.latest_session?"
        "' ('+formatDate(s.latest_session)+')':''}. "
        "Artinya harga yang bergerak di Stockbit "
        "<b>hari ini belum masuk</b> "
        "sampai sesi dianggap final. "
        "Sistem memeriksa EOD baru otomatis; "
        "sebelum 18:00 WIB provider sengaja "
        "memakai sesi sebelumnya agar candle "
        "hari berjalan tidak dianggap final."
    )

    new_notice = (
        "Mode hybrid.</b> "
        "Stage, Structure, MA, "
        "Support/Resistance, Volume dan Pattern "
        "memakai Daily confirmed. "
        "Harga terakhir dan Location Gate "
        "memakai snapshot intraday 5 menit terbaru "
        "bila tersedia. "
        "Ini monitoring berkala, "
        "<b>bukan feed broker real-time</b>."
    )

    js = js.replace(
        old_notice,
        new_notice
    )

    (
        SITE_STATIC
        / "app.js"
    ).write_text(
        js,
        encoding="utf-8"
    )


def main() -> int:

    # Bersihkan build lama.

    if SITE_DIR.exists():

        shutil.rmtree(
            SITE_DIR
        )

    ANALYZE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    symbols_path = (
        DATA_DIR
        / "symbols.csv"
    )

    if not symbols_path.exists():

        raise FileNotFoundError(
            "app/data/symbols.csv "
            "tidak ditemukan"
        )

    # =====================================
    # LOAD UNIVERSE IDX
    # =====================================

    symbols_df = pd.read_csv(
        symbols_path,
        dtype=str
    ).fillna("")

    items = []

    seen = set()

    for _, row in (
        symbols_df.iterrows()
    ):

        symbol = str(
            row.get(
                "symbol",
                ""
            )
        ).upper().strip()

        if (
            not symbol
            or
            symbol in seen
        ):

            continue

        seen.add(
            symbol
        )

        name = str(
            row.get(
                "name",
                symbol
            )
        ).strip()

        items.append({

            "symbol":
                symbol,

            "name":
                name or symbol,
        })

    # =====================================
    # LOAD SNAPSHOT
    # =====================================

    intraday = read_json(
        DATA_DIR
        / "intraday_snapshot.json"
    )

    eod = read_json(
        DATA_DIR
        / "latest_idx_snapshot.json"
    )

    scanner = []

    errors = 0

    print(
        f"[BUILD] "
        f"{len(items)} saham"
    )

    # =====================================
    # SCAN SEMUA SAHAM
    # =====================================

    for index, item in enumerate(
        items,
        start=1
    ):

        symbol = item["symbol"]

        try:

            df = load_history(
                symbol
            )

            quote, intraday_row = (
                make_quote(
                    symbol,
                    df,
                    intraday,
                    eod
                )
            )

            # Rule Engine utama.

            analysis = analyze_symbol(
                symbol,
                df,
                quote,
                None
            )

            analysis[
                "data_source"
            ] = {

                "provider":
                    "github_static",

                "data_mode":
                    "DAILY CONFIRMED + INTRADAY",

                "is_live":
                    False,

                "analysis_enabled":
                    True,

                "intraday_monitoring":
                    (
                        intraday_row
                        is not None
                    ),
            }

            analysis[
                "intraday"
            ] = intraday_row

            # Tambah candle sementara hari ini
            # hanya untuk visual chart.
            # Tidak ikut menghitung
            # Stage/Pattern confirmed.

            add_intraday_bar(
                analysis,
                intraday_row
            )

            write_json(

                ANALYZE_DIR
                / f"{symbol}.json",

                analysis
            )

            # =================================
            # SCANNER ROW
            # =================================

            pattern_names = []

            for pattern in (
                analysis.get(
                    "patterns",
                    []
                )[-8:]
            ):

                name = pattern.get(
                    "name"
                )

                if (
                    name
                    and
                    name
                    not in pattern_names
                ):

                    pattern_names.append(
                        name
                    )

            scanner.append({

                "symbol":
                    symbol,

                "name":
                    item["name"],

                "last":
                    analysis[
                        "quote"
                    ][
                        "last"
                    ],

                "change_pct":
                    analysis[
                        "quote"
                    ][
                        "change_pct"
                    ],

                "macro_cycle":
                    analysis[
                        "cycle"
                    ][
                        "macro"
                    ],

                "local_cycle":
                    analysis[
                        "cycle"
                    ][
                        "local"
                    ],

                "trend":
                    analysis[
                        "structure"
                    ][
                        "trend"
                    ],

                "rvol":
                    analysis[
                        "volume"
                    ][
                        "rvol"
                    ],

                "decision":
                    analysis[
                        "decision"
                    ][
                        "decision"
                    ],

                "confidence":
                    analysis[
                        "decision"
                    ][
                        "confidence"
                    ],

                "patterns":
                    pattern_names[-2:],

                "intraday":
                    (
                        intraday_row
                        is not None
                    ),
            })

        except Exception as exc:

            errors += 1

            scanner.append({

                "symbol":
                    symbol,

                "name":
                    item["name"],

                "decision":
                    "DATA ERROR",

                "error":
                    str(exc),

                "intraday":
                    False,
            })

        if (
            index % 100 == 0
            or
            index == len(items)
        ):

            print(
                f"  "
                f"{index}/"
                f"{len(items)}"
                f" | error "
                f"{errors}"
            )

    # =====================================
    # CLASSIFICATION
    # =====================================

    classifications = {}

    for row in scanner:

        decision = row.get(
            "decision",
            "UNKNOWN"
        )

        classifications.setdefault(
            decision,
            []
        ).append(
            row
        )

    # =====================================
    # STATUS
    # =====================================

    intraday_rows = (
        intraday.get(
            "rows"
        )
        or {}
    )

    session_dates = (
        intraday.get(
            "session_dates"
        )
        or []
    )

    latest_intraday_session = (

        session_dates[-1]

        if session_dates

        else None
    )

    status = {

        "provider":
            "github_static",

        "data_mode":
            (
                "DAILY CONFIRMED "
                "+ INTRADAY 5M"
            ),

        "is_live":
            False,

        "intraday_monitoring":
            True,

        "analysis_enabled":
            True,

        "universe_count":
            len(items),

        "history_cached_count":
            len(
                list(
                    HISTORY_DIR.glob(
                        "*.csv"
                    )
                )
            ),

        "sync_required":
            False,

        "auto_eod_sync":
            True,

        "auto_eod_check_seconds":
            600,

        "latest_session":
            eod.get(
                "session_date"
            ),

        "latest_intraday_session":
            latest_intraday_session,

        "intraday_received":
            len(
                intraday_rows
            ),

        "intraday_failed":
            len(
                intraday.get(
                    "failed"
                )
                or []
            ),

        "snapshot_fetched_at":
            intraday.get(
                "fetched_at"
            ),

        "auto_sync": {

            "status":
                "idle",

            "message":
                (
                    "GitHub snapshot "
                    "dijadwalkan "
                    "setiap 10 menit "
                    "saat jam bursa."
                ),
        },

        "scan": {

            "status":
                "done",

            "processed":
                len(items),

            "total":
                len(items),

            "percent":
                100.0,

            "errors":
                errors,

            "message":
                (
                    f"Snapshot selesai: "
                    f"{len(items)-errors} "
                    f"dianalisis, "
                    f"{errors} error."
                ),
        },

        "message":
            (
                "Daily confirmed "
                "+ monitoring intraday "
                "berkala; "
                "bukan feed broker "
                "real-time."
            ),
    }

    # =====================================
    # WRITE WEBSITE DATA
    # =====================================

    write_json(
        SITE_DATA
        / "status.json",
        status
    )

    write_json(
        SITE_DATA
        / "scan_status.json",
        status["scan"]
    )

    write_json(
        SITE_DATA
        / "scanner.json",
        scanner
    )

    write_json(
        SITE_DATA
        / "classifications.json",
        classifications
    )

    write_json(
        SITE_DATA
        / "rulebook.json",
        RULEBOOK
    )

    write_json(
        SITE_DATA
        / "build_meta.json",
        {

            "built_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "universe":
                len(items),

            "errors":
                errors,

            "intraday_received":
                len(
                    intraday_rows
                ),
        }
    )

    # =====================================
    # BUILD HTML / CSS / JS
    # =====================================

    build_frontend()

    # Disable Jekyll processing.

    (
        SITE_DIR
        / ".nojekyll"
    ).write_text(
        "",
        encoding="utf-8"
    )

    print()

    print(
        "[OK] Website siap:"
    )

    print(
        SITE_DIR
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )