"""PE / PB / 总市值估值快照抓取与持久化。

## 为什么不用 akshare 原有的估值接口

dividend skill 早期用 ``ak.stock_zh_valuation_baidu``(百度股市通)取 PE/PB,
2026-09 起该接口频繁 RemoteDisconnected,导致估值段长期 N/A。

``ak.stock_value_em``(东财个股估值)是另一条链路,实测可用:
单次调用即返回该股**全历史**(老股可达 2000+ 个交易日),
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

def _percentile_of(sorted_vals: List[float], current: float) -> float:
    """返回 current 在 sorted_vals 中的分位(%)。

    用「<= current 的比例」而非插值法,理由:PE/PB 的分位是「历史多少天
    比现在便宜」的直觉口径,读者看到 "28% 分位" 会理解为「历史上 72% 的
    时间估值比现在贵」。插值法(如 numpy.percentileofscore 的
    'midpoint')会给出 27.4% 这种小数,与直觉脱节。
    """
    if not sorted_vals:
        return 0.0
    return sum(1 for v in sorted_vals if v <= current) / len(sorted_vals) * 100


def compute_valuation_percentile(
    history: Dict[str, Any],
    current: Dict[str, Any],
    min_samples: int = 3,
) -> Dict[str, Dict[str, Any]]:
    """算 PE / PB 当前值在历史区间中的分位。

    回答「现在贵不贵」:分位低 = 相对历史便宜,分位高 = 相对历史贵。

    Args:
        history: ``load_valuation_history`` 的返回值(每个 key 是 list,
            元素可能是 None — 亏损股无 PE)。
        current: 当前值 ``{"pe_ratio": ..., "pb_ratio": ...}``。
        min_samples: 样本数下限,少于该值不给分位(样本太少分位数没意义),
            但仍返回 min / max / median 供读者参考区间。

    Returns:
        ``{field: {"percentile": float|None, "min": float|None,
                   "max": float|None, "median": float|None,
                   "count": int}}``,无数据的字段不出现。

    示例(某医药股,近 243 个交易日):
        PE 14.92 → 28.0% 分位(历史区间 13.55~16.88)
        PB  3.60 → 53.9% 分位(历史区间  3.01~4.12)

    解读:28% 分位 = 历史上 72% 的时间 PE 比现在高,即相对便宜。
    """
    out: Dict[str, Dict[str, Any]] = {}
    for field in ("pe_ratio", "pb_ratio"):
        raw_series = history.get(field) or []
        vals = sorted(
            float(v) for v in raw_series if v is not None and _to_number(v) is not None
        )
        if not vals:
            continue
        cur = _to_number(current.get(field))
        count = len(vals)
        mid = count // 2
        median = vals[mid] if count % 2 else (vals[mid - 1] + vals[mid]) / 2
        out[field] = {
            "percentile": (
                _percentile_of(vals, cur) if (cur is not None and count >= min_samples) else None
            ),
            "min": vals[0],
            "max": vals[-1],
            "median": round(median, 4),
            "count": count,
        }
    return out


def load_valuation_percentile(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_samples: int = 3,
) -> Dict[str, Dict[str, Any]]:
    """一站式:读 ``stock_market_snapshot`` 历史 → 算 PE/PB 分位。

    ``end_date`` 默认取表里最新一条,所以「当前值」始终是最近有数据的
    那天,而不是今天 —— 停牌 / 非交易日时也拿得到分位。
    """
    rows = load_valuation_history(stock_code, start_date=start_date, end_date=end_date)
    if not rows:
        return {}
    current = {
        "pe_ratio": rows[-1].get("pe_ratio"),
        "pb_ratio": rows[-1].get("pb_ratio"),
    }
    history: Dict[str, Any] = {
        "pe_ratio": [r.get("pe_ratio") for r in rows],
        "pb_ratio": [r.get("pb_ratio") for r in rows],
    }
    return compute_valuation_percentile(history, current, min_samples=min_samples)
