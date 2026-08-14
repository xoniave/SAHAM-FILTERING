r"""
Convert an IDX stock-list Excel/CSV downloaded manually from the official IDX
Stock List page into app/data/symbols.csv.

Usage:
  python tools/import_idx_stock_list.py C:\Downloads\stock-list.xlsx

The official website can change its column names; this script looks for common
variants such as Code/Kode and Company Name/Nama Perusahaan.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

if len(sys.argv) < 2:
    raise SystemExit("Usage: python tools/import_idx_stock_list.py <stock-list.xlsx|csv>")

src = Path(sys.argv[1])
if not src.exists():
    raise SystemExit(f"File not found: {src}")

if src.suffix.lower() in {".xlsx", ".xls"}:
    df = pd.read_excel(src)
else:
    df = pd.read_csv(src)

cols = {str(c).strip().lower(): c for c in df.columns}
code_candidates = ["code", "kode", "stock code", "kode saham", "symbol"]
name_candidates = ["company name", "nama perusahaan", "stock name", "nama saham", "name"]
code_col = next((cols[x] for x in code_candidates if x in cols), None)
name_col = next((cols[x] for x in name_candidates if x in cols), None)
if not code_col:
    raise SystemExit(f"Could not find stock code column. Columns: {list(df.columns)}")

out = pd.DataFrame({"symbol": df[code_col].astype(str).str.strip().str.upper()})
out["name"] = df[name_col].astype(str).str.strip() if name_col else out["symbol"]
out = out[out.symbol.str.match(r"^[A-Z0-9]{4,8}$", na=False)].drop_duplicates("symbol").sort_values("symbol")
out_path = Path(__file__).resolve().parents[1] / "app" / "data" / "symbols.csv"
out.to_csv(out_path, index=False)
print(f"Wrote {len(out)} symbols to {out_path}")
