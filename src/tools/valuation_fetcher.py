"""PE / PB / 总市值估值快照抓取与持久化。

## 为什么不用 akshare 原有的估值接口

dividend skill 早期用 ``ak.stock_zh_valuation_baidu``(百度股市通)取 PE/PB,
2026-09 起该接口频繁 RemoteDisconnected,导致估值段长期 N/A。

``ak.stock_value_em``(东财个股估值)是另一条链路,实测可用:
单次调用即返回全历史,实测 600285 有 2134 行(2000 年上市至今),
列含:

    数据日期 / 当日收盘价 / 总市值 / 总股本 /
    PE(TTM) / PE(静) / 市净率 / PEG值 / 市现率 / 市销率

因此本模块作为 PE/PB 的**首选数据源**,写入既有
``stock_market_snapshot`` 表(``snapshot_date`` DATE 精度,
与 ``(stock_code, snapshot_date)`` UNIQUE 索引天然兼容),
不新增表 —— 估值快照语义与日线(OHLCV)本就不同,分表存放。

## 与其它 fetcher 的关系

- ``stock_daily_price_fetcher``      — 每日 OHLCV(价格序列)
- ``stock_market_snapshot_fetcher``  — 估值快照(旧链路:东财 spot / 百度)
- ``valuation_fetcher``(本模块)      — 估值快照(新链路:东财 stock_value_em,
  带历史序列,支持 PE/PB 历史分位计算)

三者都写同一张 ``stock_market_snapshot`` 表,靠 ``source`` 字段区分来源。
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.db.db_connector import get_db

logger = logging.getLogger("Tools.ValuationFetcher")

# akshare 列名 → 本模块字段名。列名可能随版本变动,故列名候选写成 tuple。
_COL_CANDIDATES: Dict[str, tuple[str, ...]] = {
    "snapshot_date": ("数据日期",),
    "close_price": ("当日收盘价", "收盘价", "收盘"),
    "total_market_cap": ("总市值",),
    "total_shares": ("总股本",),
    "pe_ratio": ("PE(TTM)", "市盈率(TTM)", "PE_TTM"),
    "pe_static": ("PE(静)", "市盈率(静)"),
    "pb_ratio": ("市净率",),
}

# 数字列的小数位舍入(避免把 float32 精度误差写进 DOUBLE)
_PRECISION: Dict[str, int] = {
    "close_price": 4,
    "total_market_cap": 2,
    "total_shares": 2,
    "pe_ratio": 4,
    "pe_static": 4,
    "pb_ratio": 4,
}

SOURCE = "akshare_value_em"


def _normalize_code(stock_code: str) -> str:
    """'sh600285' / 'SZ.000001' / ' 600285 ' → 6 位纯数字代码。"""
    code = stock_code.strip().upper()
    for prefix in ("SH.", "SZ.", "BJ.", "SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[len(prefix):]
            break
    return code.zfill(6)


def _pick_column(df: pd.DataFrame, field: str) -> Optional[str]:
    for cand in _COL_CANDIDATES.get(field, ()):
        if cand in df.columns:
            return cand
    return None


def _to_number(value: Any) -> Optional[float]:
    """NaN / None / 非数字 → None;<= 0 → None(估值指标 0 无意义)。

    PE/PB 为 0 通常意味着亏损或净资产为负(银行股常见),写进库里
    会污染后续 percentile / median 计算,所以统一转 None。
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    return num


def extract_valuation_rows(
    stock_code: str,
    lookback_days: Optional[int] = 365,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """从 ``ak.stock_value_em`` 拉估值序列,返回按日期升序的行列表。

    Args:
        stock_code: 6 位股票代码(带 sh/sz 前缀也能识别)。
        lookback_days: 回溯天数,None 表示全量历史,默认 365 天。
            默认限窗是因为估值分位分析通常看近 1 年;要全历史传 None。
        start_date / end_date: 显式日期区间(YYYY-MM-DD),优先于 lookback_days。

    Returns:
        ``[{snapshot_date, close_price, pe_ratio, pb_ratio, total_market_cap,
           total_shares, source}, ...]``,按 snapshot_date 升序。
        接口失败或返回空 → ``[]``(不抛异常,由调用方降级)。
    """
    code = _normalize_code(stock_code)
    try:
        df = ak.stock_value_em(symbol=code)
    except Exception as exc:
        logger.warning("stock_value_em 抓取失败 %s: %s", code, exc)
        return []
    if df is None or df.empty:
        logger.warning("stock_value_em 返回空 %s", code)
        return []

    col_date = _pick_column(df, "snapshot_date")
    if not col_date:
        logger.warning("stock_value_em 缺少日期列,cols=%s", list(df.columns))
        return []

    # 过滤窗口
    if start_date or end_date:
        lo = pd.to_datetime(start_date) if start_date else None
        hi = pd.to_datetime(end_date) if end_date else None
    elif lookback_days:
        hi = pd.Timestamp(datetime.date.today())
        lo = hi - pd.Timedelta(days=lookback_days)
    else:
        lo = hi = None

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        raw_date = r.get(col_date)
        if pd.isna(raw_date):
            continue
        try:
            snap_date = pd.to_datetime(raw_date).date()
        except (ValueError, TypeError):
            continue
        if lo is not None and snap_date < lo.date():
            continue
        if hi is not None and snap_date > hi.date():
            continue

        row: Dict[str, Any] = {"snapshot_date": snap_date, "source": SOURCE}
        for field in ("close_price", "total_market_cap", "total_shares",
                      "pe_ratio", "pe_static", "pb_ratio"):
            col = _pick_column(df, field)
            raw = r.get(col) if col else None
            num = _to_number(raw)
            if num is not None and field in _PRECISION:
                num = round(num, _PRECISION[field])
            row[field] = num
        rows.append(row)

    rows.sort(key=lambda x: x["snapshot_date"])
    return rows


def save_valuation_snapshots(
    stock_code: str,
    rows: List[Dict[str, Any]],
) -> Dict[str, int]:
    """把估值行 UPSERT 进 ``stock_market_snapshot``。

    - 冲突键 ``(stock_code, snapshot_date)`` → UPDATE
    - 返回 ``{"inserted": N, "updated": M}``
    - 走 DuckDB 原生 SQL(项目里 peewee bind 到 SQLite 而非 DuckDB)
    """
    if not rows:
        return {"inserted": 0, "updated": 0}

    db = get_db()
    conn = db._duckdb_conn
    code = _normalize_code(stock_code)

    dates = [r["snapshot_date"] for r in rows]
    placeholders = ",".join(["?"] * len(dates))
    existing = conn.execute(
        f"SELECT snapshot_date FROM stock_market_snapshot "
        f"WHERE stock_code=? AND snapshot_date IN ({placeholders})",
        [code] + dates,
    ).fetchall()
    existing_dates = {str(r[0]) for r in existing}

    inserted = updated = 0
    for r in rows:
        fields = [
            ("close_price", r.get("close_price")),
            ("pe_ratio", r.get("pe_ratio")),
            ("pb_ratio", r.get("pb_ratio")),
            ("total_market_cap", r.get("total_market_cap")),
            ("source", r.get("source") or SOURCE),
        ]
        if str(r["snapshot_date"]) in existing_dates:
            sets = ", ".join(f"{n}=?" for n, _ in fields)
            conn.execute(
                f"UPDATE stock_market_snapshot SET {sets}, updated_at=CURRENT_TIMESTAMP "
                f"WHERE stock_code=? AND snapshot_date=?",
                [v for _, v in fields] + [code, r["snapshot_date"]],
            )
            updated += 1
        else:
            cols = ["stock_code", "snapshot_date"] + [n for n, _ in fields]
            conn.execute(
                f"INSERT INTO stock_market_snapshot ({', '.join(cols)}) "
                f"VALUES ({', '.join(['?'] * len(cols))})",
                [code, r["snapshot_date"]] + [v for _, v in fields],
            )
            inserted += 1

    logger.info(
        "估值快照落库 %s: 插入 %d / 更新 %d",
        code, inserted, updated,
    )
    return {"inserted": inserted, "updated": updated}


def fetch_and_save_valuation(
    stock_code: str,
    lookback_days: Optional[int] = 365,
) -> Dict[str, int]:
    """一站式:抓取 + UPSERT。返回 ``{"inserted": N, "updated": M}``。"""
    rows = extract_valuation_rows(stock_code, lookback_days=lookback_days)
    if not rows:
        logger.warning("未抓到估值数据: %s", stock_code)
        return {"inserted": 0, "updated": 0}
    return save_valuation_snapshots(stock_code, rows)


def load_valuation_history(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """读 ``stock_market_snapshot`` 里的 PE/PB 历史序列(日期升序)。

    供 skill 计算「当前 PE 在历史区间的分位」这类指标。
    """
    db = get_db()
    conn = db._duckdb_conn
    code = _normalize_code(stock_code)
    sql = (
        "SELECT snapshot_date, close_price, pe_ratio, pb_ratio, "
        "total_market_cap, source FROM stock_market_snapshot "
        "WHERE stock_code = ?"
    )
    params: List[Any] = [code]
    if start_date:
        sql += " AND snapshot_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND snapshot_date <= ?"
        params.append(end_date)
    sql += " ORDER BY snapshot_date"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [
        {
            "snapshot_date": str(r[0]),
            "close_price": r[1],
            "pe_ratio": r[2],
            "pb_ratio": r[3],
            "total_market_cap": r[4],
            "source": r[5],
        }
        for r in conn.execute(sql, params).fetchall()
    ]


def get_latest_valuation(stock_code: str) -> Optional[Dict[str, Any]]:
    """读最近一条估值快照(含 PE/PB),供 skill 直接填估值段。"""
    db = get_db()
    conn = db._duckdb_conn
    row = conn.execute(
        "SELECT snapshot_date, close_price, pe_ratio, pb_ratio, "
        "total_market_cap, source FROM stock_market_snapshot "
        "WHERE stock_code=? ORDER BY snapshot_date DESC LIMIT 1",
        [_normalize_code(stock_code)],
    ).fetchone()
    if not row:
        return None
    return {
        "snapshot_date": str(row[0]) if row[0] else None,
        "close_price": row[1],
        "pe_ratio": row[2],
        "pb_ratio": row[3],
        "total_market_cap": row[4],
        "source": row[5],
    }