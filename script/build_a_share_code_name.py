#!/usr/bin/env python3
"""Build data/db/a_share_code_name.csv from akshare.

Run:
    python script/build_a_share_code_name.py
"""
import sys
from pathlib import Path
import pandas as pd
import akshare as ak


CSV_PATH = Path("data/db/a_share_code_name.csv")


def main() -> int:
    df = ak.stock_info_a_code_name()
    if list(df.columns) != ["code", "name"]:
        print(f"Unexpected columns: {list(df.columns)}", file=sys.stderr)
        return 2
    df = df.assign(code=df["code"].astype(str).str.zfill(6))
    df = df.drop_duplicates(subset=["code"]).sort_values("code").reset_index(drop=True)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"Wrote {len(df)} rows to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
