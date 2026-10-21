"""stock_daily_price 日线持久化 fetcher。

设计动机:dividend_skill 与估值分析需要看历史价位(PE 分位、PB 分位、
年度收盘价),akshare 日线接口(stock_zh_a_hist)在网络挂掉时无法读到。
本模块把一次成功抓到的全量历史日线持久化到 stock_daily_price,
表设计为一行 = 一个交易日,精度 trade_date DATE 准确到年月日,
UNIQUE (stock_code, trade_date) 冲突时 UPSERT 实现增量刷新。

与 stock_market_snapshot 的分工:
- stock_daily_price: 每日价格(OHLCV),全量历史
- stock_market_snapshot: 估值快照(PE/PB/总市值),按接口实际频率

字段极简:开盘/最高/最低/收盘/成交量五列,
够 dividend_skill 用;再加 source/created_at/updated_at。
"""
from __future__ import annotations

import datetime
import logging
import traceback
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.db.db_connector import get_db

logger = logging.getLogger("Tools.DailyPriceFetcher")


def _normalize_code(stock_code: str) -> str:
    code = stock_code.strip().upper()
    for prefix in ("SH", "SZ", "BJ", "SH.", "SZ.", "BJ."):
        if code.startswith(prefix):
            code = code[len(prefix):]
    return code.zfill(6)


def _fetch_daily_prices_from_akshare(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "qfq",
) -> Optional[pd.DataFrame]:
    """从 akshare stock_zh_a_hist 拉日线。

    Args:
        stock_code: 6 位股票代码
        start_date: YYYYMMDD / YYYY-MM-DD / None(全量)
        end_date: 同上
        adjust: 复权方式;"qfq"=前复权(默认,股息分析按前复权算总收益
                更准确),"hfq"=后复权,""=不复权。
                不传默认全量全 A 上市以来。

    Returns:
        DataFrame(列含「日期」「开盘」「收盘」「最高」「最低」「成交量」...)
        或 None(网络失败)。
    """
    code = _normalize_code(stock_code)
    kwargs: Dict[str, Any] = {
        "symbol": code,
        "period": "daily",
        "adjust": adjust,
    }
    if start_date:
        kwargs["start_date"] = start_date.replace("-", "") if "-" in start_date else start_date
    if end_date:
        kwargs["end_date"] = end_date.replace("-", "") if "-" in end_date else end_date

    try:
        df = ak.stock_zh_a_hist(**kwargs)
    except Exception as exc:
        logger.warning("akshare 日线拉取失败 %s: %s", code, exc)
        logger.debug(traceback.format_exc())
        return None
    if df is None or df.empty:
        return None
    return df


def fetch_daily_prices(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "qfq",
) -> List[Dict[str, Any]]:
    """拉日线(纯函数,不落库)。

    返回 [{trade_date, open, high, low, close, volume}],已是 DuckDB 友好的
    Python 原生类型。
    """
    df = _fetch_daily_prices_from_akshare(stock_code, start_date, end_date, adjust)
    if df is None:
        return []
    # 列名因 akshare 版本可能略有差异,容错
    date_col = next((c for c in df.columns if c in ("日期", "date")), None)
    open_col = next((c for c in df.columns if c in ("开盘", "开盘价")), None)
    close_col = next((c for c in df.columns if c in ("收盘", "收盘价")), None)
    high_col = next((c for c in df.columns if c in ("最高", "最高价")), None)
    low_col = next((c for c in df.columns if c in ("最低", "最低价")), None)
    vol_col = next((c for c in df.columns if c in ("成交量",)), None)

    if not (date_col and close_col):
        logger.warning("akshare 日线返回缺少关键列: %s;cols=%s", stock_code, list(df.columns))
        return []

    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        d_raw = row.get(date_col)
        try:
            d_obj = pd.to_datetime(d_raw).date()
        except (ValueError, TypeError):
            continue

        def _f(col: Optional[str]) -> Optional[float]:
            if not col:
                return None
            v = row.get(col)
            if pd.isna(v):
                return None
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return None
            # 防御:akshare 前复权算法在 IPO 早期偶发算出负价,
            # 这类异常行不入库,避免污染估值/趋势计算。
            if fv < 0:
                return None
            return fv

        out.append({
            "trade_date": d_obj,
            "open_price": _f(open_col),
            "high_price": _f(high_col),
            "low_price": _f(low_col),
            "close_price": _f(close_col),
            "volume": _f(vol_col),
        })
    return out


def save_daily_prices(
    stock_code: str, prices: List[Dict[str, Any]],
    source: str = "akshare_hist",
) -> Dict[str, int]:
    """批量 UPSERT 日线到 stock_daily_price。

    - 主键 (stock_code, trade_date) 冲突时 UPDATE;
    - 返回 {"inserted": N, "updated": M}。
    - 走 DuckDB 原生 SQL,绕开 peewee ORM(项目里 peewee bind 到 SQLite 而非 DuckDB)。
    """
    if not prices:
        return {"inserted": 0, "updated": 0}

    db = get_db()
    conn = db._duckdb_conn
    code = _normalize_code(stock_code)

    # 先 SELECT 既有 (stock_code, trade_date) 集合,bulk upsert
    trade_dates = [p["trade_date"] for p in prices]
    placeholders = ",".join(["?"] * len(trade_dates))
    existing = conn.execute(
        f"SELECT trade_date FROM stock_daily_price "
        f"WHERE stock_code=? AND trade_date IN ({placeholders})",
        [code] + trade_dates,
    ).fetchall()
    existing_dates = {str(r[0]) for r in existing}

    inserted = 0
    updated = 0
    for p in prices:
        td_str = str(p["trade_date"])
        if td_str in existing_dates:
            conn.execute(
                "UPDATE stock_daily_price SET "
                "open_price=?, high_price=?, low_price=?, close_price=?, "
                "volume=?, source=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE stock_code=? AND trade_date=?",
                [
                    p.get("open_price"), p.get("high_price"), p.get("low_price"),
                    p.get("close_price"), p.get("volume"), source,
                    code, p["trade_date"],
                ],
            )
            updated += 1
        else:
            conn.execute(
                "INSERT INTO stock_daily_price "
                "(stock_code, trade_date, open_price, high_price, low_price, "
                " close_price, volume, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    code, p["trade_date"],
                    p.get("open_price"), p.get("high_price"), p.get("low_price"),
                    p.get("close_price"), p.get("volume"), source,
                ],
            )
            inserted += 1
    return {"inserted": inserted, "updated": updated}


def fetch_and_save_daily_prices(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "qfq",
    source: str = "akshare_hist",
) -> Dict[str, int]:
    """一站式:拉日线 + UPSERT。返回 {"inserted": N, "updated": M} 或 {全零表示失败}。"""
    prices = fetch_daily_prices(stock_code, start_date, end_date, adjust)
    if not prices:
        logger.warning("未拉到日线数据: %s", stock_code)
        return {"inserted": 0, "updated": 0}
    result = save_daily_prices(stock_code, prices, source=source)
    logger.info(
        "日线落库 %s: 拉取 %d 行, 插入 %d / 更新 %d",
        stock_code, len(prices), result["inserted"], result["updated"],
    )
    return result


def load_daily_prices(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """从 stock_daily_price 读历史日线(日期升序)。

    skill 端在网络挂掉时,可用本函数从 DB 读 close 历史做估值分位等计算。
    """
    db = get_db()
    conn = db._duckdb_conn
    code = _normalize_code(stock_code)
    sql = (
        "SELECT trade_date, open_price, high_price, low_price, close_price, volume "
        "FROM stock_daily_price WHERE stock_code=?"
    )
    params: List[Any] = [code]
    if start_date:
        sql += " AND trade_date >= ?"
        params.append(start_date if "-" in str(start_date) else str(start_date))
    if end_date:
        sql += " AND trade_date <= ?"
        params.append(end_date if "-" in str(end_date) else str(end_date))
    sql += " ORDER BY trade_date"
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "trade_date": str(r[0]),
            "open_price": r[1],
            "high_price": r[2],
            "low_price": r[3],
            "close_price": r[4],
            "volume": r[5],
        }
        for r in rows
    ]


def get_latest_close_price(stock_code: str) -> Optional[float]:
    """读最近一日收盘价(供 skill 取 current_price fallback)。"""
    db = get_db()
    conn = db._duckdb_conn
    row = conn.execute(
        "SELECT close_price FROM stock_daily_price "
        "WHERE stock_code=? AND close_price IS NOT NULL "
        "ORDER BY trade_date DESC LIMIT 1",
        [_normalize_code(stock_code)],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None
