"""stock_market_snapshot 抓取与读取工具。

设计动机：akshare 行情接口（雪球 stock_individual_basic_info_xq、
东财 stock_zh_a_hist、百度 stock_zh_valuation_baidu）在 2026-09 频繁断连，
导致 skill 端 market_data 全为 None。把每次成功抓到的「最新一个交易日」
的收盘价 / PE / PB / 总市值落到 stock_market_snapshot 表里，skill 在外网挂
掉时仍然能读到最近一次缓存的估值。

本模块只负责「单一股票、单一交易日」级别的写入，多股票批量由
scripts/refresh_stock_market_snapshot.py 调用。
"""
from __future__ import annotations

import datetime
import logging
import traceback
from typing import Any, Dict, Optional

import akshare as ak
import pandas as pd

from src.db.db_connector import get_db
from src.db.models import StockMarketSnapshot

logger = logging.getLogger("Tools.MarketSnapshot")

# akshare 字段对应：
# - stock_zh_a_spot_em 的列：代码/名称/最新价/市盈率-动态/市净率/总市值/...
# - 注意 "市盈率-动态" 是 TTM，PB 是动态 PB，与历史日线对齐


def _normalize_code(stock_code: str) -> str:
    code = stock_code.strip().upper()
    for prefix in ("SH", "SZ", "BJ", "SH.", "SZ.", "BJ."):
        if code.startswith(prefix):
            code = code[len(prefix):]
    return code.zfill(6)


def _fetch_from_spot_em(stock_code: str) -> Optional[Dict[str, Any]]:
    """东财全 A 实时快照 — 一次拉全部，最快的方式。

    返回字段：close_price / pe_ratio / pb_ratio / total_market_cap(元) / snapshot_date
    """
    code = _normalize_code(stock_code)
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        return None
    # 列名因 akshare 版本可能略有差异，做容错
    code_col = next((c for c in df.columns if c in ("代码", "股票代码")), None)
    if not code_col:
        return None
    row = df[df[code_col].astype(str).str.zfill(6) == code]
    if row.empty:
        return None
    r = row.iloc[0]
    close = r.get("最新价")
    pe = r.get("市盈率-动态") if "市盈率-动态" in df.columns else r.get("市盈率")
    pb = r.get("市净率")
    cap = r.get("总市值")  # 单位：元
    return {
        "close_price": float(close) if pd.notna(close) else None,
        "pe_ratio": float(pe) if pd.notna(pe) else None,
        "pb_ratio": float(pb) if pd.notna(pb) else None,
        "total_market_cap": float(cap) if pd.notna(cap) else None,
        "snapshot_date": datetime.date.today(),
    }


def _fetch_from_baidu_valuation(
    stock_code: str, indicator: str,
) -> Optional[Dict[str, Any]]:
    """百度股市通估值接口兜底：取「最近一年」序列的最后一行。

    indicator 取值: "总市值" / "市盈率(TTM)" / "市净率"。
    """
    code = _normalize_code(stock_code)
    df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period="近一年")
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    val = None
    for col in ("value", "市值", "市盈率(TTM)", "市净率"):
        if col in df.columns and pd.notna(last.get(col)):
            try:
                val = float(last.get(col))
                break
            except (TypeError, ValueError):
                continue
    if val is None:
        return None
    date_val = last.get("date")
    sdate = datetime.date.today()
    if pd.notna(date_val):
        try:
            sdate = pd.to_datetime(date_val).date()
        except Exception:
            pass
    return {"value": val, "snapshot_date": sdate}


def fetch_snapshot(stock_code: str) -> Optional[Dict[str, Any]]:
    """抓取单个 stock_code 的最新估值快照；多个数据源依次尝试。

    优先级：东财 spot_em（一次拉全部，速度最快且字段最全）→ 百度估值兜底。
    全部失败返回 None，不抛异常。
    """
    try:
        snap = _fetch_from_spot_em(stock_code)
        if snap and snap.get("close_price") is not None:
            snap["source"] = "akshare_em"
            return snap
    except Exception as exc:
        logger.warning("akshare spot_em 抓取失败 %s: %s", stock_code, exc)

    # 百度兜底：每个字段单独一次拉取（接口不允许多 indicator 一次拉）。
    # 注意：stock_zh_valuation_baidu 的"总市值"列单位是「亿元」，PE/PB 本身是比率（无量纲）。
    # 为统一语义，存库前把市值 ×1e8 换算成「元」，与 stock_zh_a_spot_em 的"总市值"列对齐。
    snap = {
        "close_price": None, "pe_ratio": None, "pb_ratio": None,
        "total_market_cap": None, "snapshot_date": datetime.date.today(),
    }
    got = False
    for ind, key, scale in [
        ("总市值", "total_market_cap", 1e8),  # 亿元 → 元
        ("市盈率(TTM)", "pe_ratio", 1.0),
        ("市净率", "pb_ratio", 1.0),
    ]:
        try:
            r = _fetch_from_baidu_valuation(stock_code, ind)
            if r:
                snap[key] = r["value"] * scale
                snap["snapshot_date"] = r["snapshot_date"]
                got = True
        except Exception as exc:
            logger.warning("百度估值 %s 抓取失败 %s: %s", ind, stock_code, exc)
    if got:
        snap["source"] = "baidu_valuation"
        return snap

    return None


def save_snapshot(snap: Dict[str, Any]) -> int:
    """把 fetch_snapshot() 的结果 upsert 到 stock_market_snapshot 表。

    - 主键 (stock_code, snapshot_date) 冲突时 UPDATE。
    - 返回写入的记录 id。

    注意：项目里 peewee 绑定到 SQLite `:memory:`，跟实际存储 DuckDB 不一致，
    所以这里直接走 DuckDB SQL；用 `INSERT ... RETURNING id` / `UPDATE ... RETURNING id`
    拿到 id。
    """
    from datetime import date as _date

    db = get_db()
    conn = db._duckdb_conn

    code = _normalize_code(snap["stock_code"])
    sdate = snap["snapshot_date"]
    if isinstance(sdate, str):
        sdate = _date.fromisoformat(sdate)

    existing = conn.execute(
        "SELECT id FROM stock_market_snapshot WHERE stock_code=? AND snapshot_date=?",
        [code, sdate],
    ).fetchone()

    fields = [
        ("close_price", snap.get("close_price")),
        ("pe_ratio", snap.get("pe_ratio")),
        ("pb_ratio", snap.get("pb_ratio")),
        ("total_market_cap", snap.get("total_market_cap")),
        ("source", snap.get("source") or "manual"),
    ]

    if existing:
        row_id = existing[0]
        sets = ", ".join([f"{name}=?" for name, _ in fields]) + ", created_at=CURRENT_TIMESTAMP"
        params = [v for _, v in fields] + [row_id]
        conn.execute(
            f"UPDATE stock_market_snapshot SET {sets} WHERE id=?",
            params,
        )
        logger.info("更新行情快照 %s @ %s id=%s", code, sdate, row_id)
        return row_id

    cols = ["stock_code", "snapshot_date"] + [name for name, _ in fields]
    placeholders = ", ".join(["?"] * len(cols))
    params = [code, sdate] + [v for _, v in fields]
    cur = conn.execute(
        f"INSERT INTO stock_market_snapshot ({', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING id",
        params,
    )
    row_id = cur.fetchone()[0]
    logger.info("新增行情快照 %s @ %s id=%s", code, sdate, row_id)
    return row_id


def fetch_and_save(stock_code: str) -> Optional[int]:
    """一站式：抓取并保存，返回 id 或 None（抓取失败）。"""
    snap = fetch_snapshot(stock_code)
    if not snap:
        return None
    snap["stock_code"] = stock_code
    return save_snapshot(snap)


def load_latest_snapshot(stock_code: str) -> Optional[Dict[str, Any]]:
    """读 stock_code 最近一次写入的快照（按 created_at DESC）。

    供 skill 在 akshare 挂掉时 fallback 用。
    """
    db = get_db()
    conn = db._duckdb_conn
    rows = conn.execute(
        """
        SELECT stock_code, snapshot_date, close_price, pe_ratio,
               pb_ratio, total_market_cap, source, created_at
        FROM stock_market_snapshot
        WHERE stock_code=?
        ORDER BY created_at DESC, snapshot_date DESC
        LIMIT 1
        """,
        [_normalize_code(stock_code)],
    ).fetchall()
    if not rows:
        return None
    r = rows[0]
    return {
        "stock_code": r[0],
        "snapshot_date": str(r[1]) if r[1] else None,
        "close_price": r[2],
        "pe_ratio": r[3],
        "pb_ratio": r[4],
        "total_market_cap": r[5],
        "source": r[6],
        "created_at": str(r[7]) if r[7] else None,
    }
