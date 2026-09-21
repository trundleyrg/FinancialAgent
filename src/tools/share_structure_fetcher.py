"""股本结构 fetcher。

数据源优先级：
1. akshare stock_zh_a_spot_em()  实时行情（含 总股本/流通股本）
2. akshare stock_individual_basic_info_xq()  雪球基础信息
3. 本地推导：用 capital_change_events.cash_per_10_shares 与
   consolidated_cash_flow_statement.cash_for_dividend_and_interest
   反推 total_shares = cash_dividend_paid / (cash_per_10_shares / 10)

调用：
- fetch_share_structure(stock_code, year, period) -> Dict
- fetch_and_persist(stock_code, year, period) -> bool  直接写 DB
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

import pandas as pd

from src.db.db_connector import get_db
from src.db.models import ShareStructure
from src.utils.logger import manager

logger = manager.get_logger("Agent.ShareStructureFetcher", "market_data.log")


def _to_float(v: Any) -> Optional[float]:
    """兼容 pd.NA / None / 字符串数字。"""
    if v is None:
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _from_akshare_spot(stock_code: str) -> Optional[Dict[str, Any]]:
    """akshare stock_zh_a_spot_em → 取 total_shares / unrestricted_shares 等。

    列名约定（2024+）：'代码','名称','最新价','今开','昨收','最高','最低',
    '成交量','成交额','振幅','涨跌幅','涨跌额','换手率','量比','市盈率',
    '市净率','总市值','流通市值','总股本','流通股本','涨速','5分钟涨跌',
    '60日涨跌幅','年初至今涨跌幅'
    """
    try:
        import akshare as ak
    except ImportError:
        return None
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as exc:  # network / rate limit / etc
        logger.warning("akshare stock_zh_a_spot_em 失败 %s: %s", stock_code, exc)
        return None
    if df is None or df.empty:
        return None
    row = df[df["代码"] == stock_code]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "company_name": str(r.get("名称", "") or ""),
        "total_shares": _to_float(r.get("总股本")),
        "unrestricted_shares": _to_float(r.get("流通股本")),
    }


def _from_local_derivation(stock_code: str, year: int, period: str) -> Optional[Dict[str, Any]]:
    """本地推导 total_shares：用分红支出 ÷ 每股分红。

    公式：
        dividend_per_share = cash_per_10_shares / 10
        total_shares = cash_for_dividend_and_interest / dividend_per_share

    要求：
        - capital_change_events 当年有 cash_per_10_shares
        - consolidated_cash_flow_statement 当年 cash_for_dividend_and_interest > 0
    """
    conn = get_db()._duckdb_conn
    try:
        div_row = conn.execute(
            """
            SELECT cash_per_10_shares FROM capital_change_events
            WHERE stock_code = ? AND report_year = ? AND report_period = ?
              AND event_type = 'cash_dividend' AND cash_per_10_shares IS NOT NULL
            ORDER BY event_date DESC LIMIT 1
            """,
            [stock_code, year, period],
        ).fetchone()
        cf_row = conn.execute(
            """
            SELECT cash_for_dividend_and_interest FROM consolidated_cash_flow_statement
            WHERE stock_code = ? AND report_year = ? AND report_period = ?
            """,
            [stock_code, year, period],
        ).fetchone()
    except Exception as exc:
        logger.warning("本地推导查询失败: %s", exc)
        return None
    if not div_row or not cf_row:
        return None
    cash_per_10 = div_row[0]
    cash_total = cf_row[0]
    if not cash_per_10 or not cash_total or cash_per_10 <= 0 or cash_total <= 0:
        return None
    per_share = float(cash_per_10) / 10.0
    total_shares = float(cash_total) / per_share
    return {
        "company_name": None,
        "total_shares": round(total_shares, 0),
        "unrestricted_shares": None,
        "derivation": "cash_dividend_paid / (cash_per_10_shares / 10)",
    }


def fetch_share_structure(
    stock_code: str, year: int, period: str = "FY",
) -> Dict[str, Any]:
    """获取股本结构，akshare 优先，本地推导兜底。

    Returns:
        {
          "stock_code": "000423",
          "report_year": 2024,
          "report_period": "FY",
          "total_shares": float | None,           # 股
          "unrestricted_shares": float | None,    # 股
          "company_name": str | None,
          "source": "akshare_spot" | "local_derivation" | "none",
          "error": str | None,
        }
    """
    stock_code = stock_code.strip().zfill(6)
    result: Dict[str, Any] = {
        "stock_code": stock_code,
        "report_year": year,
        "report_period": period,
        "total_shares": None,
        "unrestricted_shares": None,
        "company_name": None,
        "source": "none",
        "error": None,
    }

    # 1. akshare 实时
    live = _from_akshare_spot(stock_code)
    if live and live.get("total_shares"):
        result.update({k: v for k, v in live.items() if v is not None})
        result["source"] = "akshare_spot"
        return result

    # 2. 本地推导
    derived = _from_local_derivation(stock_code, year, period)
    if derived and derived.get("total_shares"):
        result["total_shares"] = derived["total_shares"]
        result["unrestricted_shares"] = derived.get("unrestricted_shares")
        if derived.get("company_name"):
            result["company_name"] = derived["company_name"]
        result["source"] = "local_derivation"
        return result

    result["error"] = "all sources failed"
    return result


def fetch_and_persist(
    stock_code: str, year: int, period: str = "FY",
) -> bool:
    """fetch_share_structure → 写入 share_structure 表（先删旧行再插）。"""
    data = fetch_share_structure(stock_code, year, period)
    if not data.get("total_shares"):
        logger.warning(
            "未获取到 %s %s %s 股本结构: source=%s error=%s",
            stock_code, year, period, data.get("source"), data.get("error"),
        )
        return False

    db = get_db()
    company_name = data.get("company_name") or stock_code
    # 先删旧的 (stock_code, year, period)
    db._duckdb_conn.execute(
        """
        DELETE FROM share_structure
        WHERE stock_code = ? AND report_year = ? AND report_period = ?
        """,
        [stock_code, year, period],
    )
    row = {
        "company_name": company_name,
        "stock_code": stock_code,
        "report_year": year,
        "report_period": period,
        "total_shares": data["total_shares"],
        "unrestricted_shares": data.get("unrestricted_shares"),
    }
    db._duckdb_conn.execute(
        """
        INSERT INTO share_structure
            (company_name, stock_code, report_year, report_period,
             total_shares, unrestricted_shares)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            row["company_name"], row["stock_code"], row["report_year"],
            row["report_period"], row["total_shares"], row["unrestricted_shares"],
        ],
    )
    logger.info(
        "写入 share_structure: %s %s %s total_shares=%s source=%s",
        stock_code, year, period, data["total_shares"], data["source"],
    )
    return True
