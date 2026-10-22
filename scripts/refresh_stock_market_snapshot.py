"""手动触发刷新行情估值 + 日线数据。

Usage:
    # 只拉估值(原行为)
    python scripts/refresh_stock_market_snapshot.py 600285
    # 拉估值 + 全量日线
    python scripts/refresh_stock_market_snapshot.py 600285 --with-price
    # 只拉日线(估值跳过)
    python scripts/refresh_stock_market_snapshot.py 600285 --price-only
    python scripts/refresh_stock_market_snapshot.py 600285 --price-only --start 2020-01-01 --end 2024-12-31

注:股票行情接口在 2026-09 频繁断连(雪球/东财/百度),
  把每次成功抓到的估值 / 日线落到本地表,skill 在外网挂掉时仍可读。
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")

from src.tools.stock_market_snapshot_fetcher import (
    fetch_and_save,
    load_latest_snapshot,
)
from src.tools.stock_daily_price_fetcher import (
    fetch_and_save_daily_prices,
    load_daily_prices,
)
from src.tools.valuation_fetcher import (
    fetch_and_save_valuation,
    get_latest_valuation,
)


def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(
        description="刷新估值 / 日线到本地表",
    )
    parser.add_argument(
        "codes", nargs="+", help="股票代码列表(可多个)",
    )
    parser.add_argument(
        "--with-price", action="store_true",
        help="除估值外,顺带拉并入库全量日线(stock_daily_price)",
    )
    parser.add_argument(
        "--price-only", action="store_true",
        help="只刷新日线,跳过估值快照",
    )
    parser.add_argument(
        "--start", default=None, help="日线起始日(YYYY-MM-DD),默认全量",
    )
    parser.add_argument(
        "--end", default=None, help="日线结束日(YYYY-MM-DD),默认今天",
    )
    parser.add_argument(
        "--adjust", default="qfq", choices=("", "qfq", "hfq"),
        help="复权方式,qfq=前复权(默认,hfq=后复权,''=不复权)",
    )
    parser.add_argument(
        "--val-lookback", type=int, default=365,
        help="估值快照回溯天数,默认 365(约 243 个交易日);传 0 表示全量历史",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    failed = 0
    for raw in args.codes:
        code = raw.strip()
        print(f"\n=== {code} ===")

        # 估值快照 — 优先用 stock_value_em(东财个股估值,带历史序列)。
        # 旧链路(spot_em / 百度)仅在 stock_value_em 失败时兜底,
        # 因为 2026-09 起百度接口频繁断连。
        if not args.price_only:
            val_res = None
            try:
                val_res = fetch_and_save_valuation(
                    code,
                    lookback_days=args.val_lookback or None,
                )
            except Exception as exc:
                print(f"  [valuation] stock_value_em 异常: {exc}")
            if val_res and (val_res["inserted"] or val_res["updated"]):
                latest = get_latest_valuation(code) or {}
                print(
                    f"  [valuation] 插入 {val_res['inserted']} / 更新 {val_res['updated']}; "
                    f"date={latest.get('snapshot_date')} "
                    f"close={latest.get('close_price')} PE={latest.get('pe_ratio')} "
                    f"PB={latest.get('pb_ratio')} cap={latest.get('total_market_cap')} "
                    f"src={latest.get('source')}"
                )
            else:
                # 兜底:旧链路(单日快照,无历史)
                snap_id = fetch_and_save(code)
                if snap_id is None:
                    print(f"  [valuation] 抓取失败:所有 akshare 源都不可用")
                    failed += 1
                else:
                    latest = load_latest_snapshot(code)
                    if latest:
                        print(
                            f"  [valuation] 兜底 id={snap_id} date={latest['snapshot_date']} "
                            f"close={latest['close_price']} PE={latest['pe_ratio']} "
                            f"PB={latest['pb_ratio']} cap={latest['total_market_cap']} "
                            f"src={latest['source']}"
                        )

        # 日线
        if args.with_price or args.price_only:
            res = fetch_and_save_daily_prices(
                code, start_date=args.start, end_date=args.end, adjust=args.adjust,
            )
            nrows = len(load_daily_prices(code, args.start, args.end))
            if res["inserted"] == 0 and res["updated"] == 0:
                failed += 1
            else:
                print(
                    f"  [price] 插入 {res['inserted']} / 更新 {res['updated']}; "
                    f"stock_daily_price 现共 {nrows} 行"
                )

    fail_label = "估值或日线至少一次失败" if (
        not args.price_only or args.with_price
    ) else "日线失败"
    print(f"\n完成。失败: {failed}, 成功: {len(args.codes) - failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
