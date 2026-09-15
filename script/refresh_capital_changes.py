#!/usr/bin/env python3
"""手动刷新股本变动事件。

用法：
    python script/refresh_capital_changes.py --stock-code 000423
    python script/refresh_capital_changes.py --all
    python script/refresh_capital_changes.py --stock-code 000423 --dry-run
"""
import argparse
import sys
from pathlib import Path
from typing import Optional

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.db import CapitalChangeEventRepository, ReportKey
from src.db.db_connector import get_db
from src.stock_tools.capital_change_fetcher import fetch_capital_change_events
from src.utils.logger import manager

logger = manager.get_logger("Script.RefreshCapitalChanges", "script.log")


def _list_all_companies() -> list:
    db = get_db()
    rows = db.filter_records("financial_reports")
    seen = {}
    for r in rows:
        key = (r["stock_code"], r["company_name"])
        if key not in seen:
            seen[key] = True
    return [{"stock_code": k[0], "company_name": k[1]} for k in seen]


def _company_name_from_db(stock_code: str) -> Optional[str]:
    """Resolve company_name from financial_reports for a stock_code."""
    db = get_db()
    rows = db.filter_records("financial_reports", stock_code=stock_code)
    if not rows:
        return None
    name = rows[0].get("company_name")
    return name if name else None


def _refresh_one(
    stock_code: str,
    dry_run: bool = False,
    company_name: Optional[str] = None,
) -> int:
    repo = CapitalChangeEventRepository(get_db())
    key = ReportKey(stock_code=stock_code)
    existing = repo.count_events(key)
    logger.info("[%s] 现有事件: %d 条", stock_code, existing)
    events = fetch_capital_change_events(stock_code, company_name=company_name)
    # fetcher 偶发产出含 "NaT" 字符串的事件（pandas NaT.isoformat() 漏洞）。
    # 把所有日期字段里的 "NaT" 字符串统一清洗为 None，避免 DuckDB insert 报错。
    date_fields = (
        "event_date", "ex_date", "record_date", "payment_date", "listing_date",
    )
    cleaned: list = []
    for e in events:
        if not e.get("event_date") or str(e["event_date"]) == "NaT":
            # event_date 是主键一部分，整条丢弃
            continue
        for f in date_fields:
            if str(e.get(f) or "") == "NaT":
                e[f] = None
        cleaned.append(e)
    events = cleaned
    if dry_run:
        logger.info("[%s] dry-run: 将拉取 %d 条", stock_code, len(events))
        return 0
    if existing > 0:
        rows = repo.list_events(key)
        db = get_db()
        for r in rows:
            db.delete_records(
                "capital_change_events",
                stock_code=stock_code, event_date=str(r["event_date"]),
                event_type=r["event_type"],
            )
    written = repo.upsert_many(events)
    logger.info("[%s] 重拉并入库: %d 条", stock_code, written)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stock-code", help="单股刷新，例如 000423")
    group.add_argument("--all", action="store_true", help="刷新库内全部公司")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写库")
    parser.add_argument(
        "--company-name",
        default=None,
        help="可选：传入公司名称，否则按 stock_code 查库补齐",
    )
    args = parser.parse_args()

    if args.stock_code:
        cn = args.company_name or _company_name_from_db(args.stock_code)
        _refresh_one(
            args.stock_code, dry_run=args.dry_run, company_name=cn,
        )
    else:
        for c in _list_all_companies():
            _refresh_one(
                c["stock_code"], dry_run=args.dry_run,
                company_name=c.get("company_name"),
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())