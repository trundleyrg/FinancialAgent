"""手动触发刷新 stock_market_snapshot 行情估值快照。

Usage:
    python scripts/refresh_stock_market_snapshot.py 000423
    python scripts/refresh_stock_market_snapshot.py 000423 600519 000001
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from src.tools.stock_market_snapshot_fetcher import (
    fetch_and_save,
    load_latest_snapshot,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/refresh_stock_market_snapshot.py <stock_code> [<stock_code> ...]")
        return 1
    failed = 0
    for raw in sys.argv[1:]:
        code = raw.strip()
        print(f"\n=== {code} ===")
        snap_id = fetch_and_save(code)
        if snap_id is None:
            print(f"  抓取失败：所有 akshare 源都不可用")
            failed += 1
            continue
        latest = load_latest_snapshot(code)
        if latest:
            print(
                f"  id={snap_id} date={latest['snapshot_date']} "
                f"close={latest['close_price']} PE={latest['pe_ratio']} "
                f"PB={latest['pb_ratio']} cap={latest['total_market_cap']} "
                f"src={latest['source']}"
            )
    print(f"\n完成。失败: {failed}, 成功: {len(sys.argv) - 1 - failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
