"""股本变动事件 fetcher。

数据源：
- 主：东方财富 stock_history_dividend_detail (indicator='分红'/'配股')
- 补：巨潮 stock_dividend_cninfo + stock_allotment_cninfo

合并规则：
- key = (stock_code, event_date, event_type)
- 巨潮提供「分红类型」「报告时间」等元信息
- 巨潮没匹配到时，event_type 由字段推断：
    cash>0 且 bonus+capitalized==0 → cash_dividend
    cash==0 且 bonus>0           → bonus_share
    cash==0 且 capitalized>0     → capitalized_share
    都有                          → combination
"""
from datetime import date
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.utils.logger import manager

logger = manager.get_logger("Agent.CapitalChangeFetcher", "market_data.log")


def _normalize_stock_code(stock_code: str) -> str:
    code = stock_code.strip().upper()
    for prefix in ("SH", "SZ", "BJ", "SH.", "SZ.", "BJ."):
        if code.startswith(prefix):
            code = code[len(prefix):]
    return code.zfill(6)


def _to_date(v: Any) -> Optional[date]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s or s in ("NaT", "nan"):
        return None
    return date.fromisoformat(s[:10])


def _report_year_from_cninfo(report_time: Any, fallback_date: Optional[date]) -> int:
    if report_time:
        m = str(report_time)
        for token in m.replace("年报", "年").replace("中报", "年").split("年"):
            if token.isdigit() and len(token) == 4:
                return int(token)
    return fallback_date.year if fallback_date else 0


def _infer_event_type(cash: float, bonus: float, capitalized: float) -> str:
    has_cash = (cash or 0) > 0
    has_bonus = (bonus or 0) > 0
    has_capitalized = (capitalized or 0) > 0
    if has_cash and not has_bonus and not has_capitalized:
        return "cash_dividend"
    if not has_cash and has_bonus and not has_capitalized:
        return "bonus_share"
    if not has_cash and not has_bonus and has_capitalized:
        return "capitalized_share"
    if has_cash or has_bonus or has_capitalized:
        return "combination"
    return "cash_dividend"


def fetch_capital_change_events(stock_code: str) -> List[Dict[str, Any]]:
    code = _normalize_stock_code(stock_code)
    company_name = ""
    try:
        df_em_div = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
    except Exception as e:
        logger.warning("东财分红接口失败 %s: %s", code, e)
        df_em_div = pd.DataFrame()
    try:
        df_em_allot = ak.stock_history_dividend_detail(symbol=code, indicator="配股")
    except Exception as e:
        logger.warning("东财配股接口失败 %s: %s", code, e)
        df_em_allot = pd.DataFrame()
    try:
        df_cn_div = ak.stock_dividend_cninfo(symbol=code)
    except Exception as e:
        logger.warning("巨潮分红接口失败 %s: %s", code, e)
        df_cn_div = pd.DataFrame()
    try:
        df_cn_allot = ak.stock_allotment_cninfo(symbol=code)
    except Exception as e:
        logger.warning("巨潮配股接口失败 %s: %s", code, e)
        df_cn_allot = pd.DataFrame()

    events: List[Dict[str, Any]] = []

    for _, row in df_em_div.iterrows():
        ev_date = _to_date(row.get("公告日期"))
        if not ev_date:
            continue
        cash = float(row.get("派息") or 0)
        bonus = float(row.get("送股") or 0)
        capitalized = float(row.get("转增") or 0)
        events.append({
            "company_name": company_name,
            "stock_code": code,
            "report_year": ev_date.year,
            "report_period": "FY",
            "event_type": _infer_event_type(cash, bonus, capitalized),
            "event_date": ev_date.isoformat(),
            "ex_date": _to_date(row.get("除权除息日")).isoformat() if _to_date(row.get("除权除息日")) else None,
            "record_date": _to_date(row.get("股权登记日")).isoformat() if _to_date(row.get("股权登记日")) else None,
            "payment_date": None,
            "listing_date": _to_date(row.get("红股上市日")).isoformat() if _to_date(row.get("红股上市日")) else None,
            "status": str(row.get("进度") or "").strip() or None,
            "cash_per_10_shares": cash if cash > 0 else None,
            "bonus_shares_per_10": bonus if bonus > 0 else None,
            "capitalized_shares_per_10": capitalized if capitalized > 0 else None,
            "allotment_ratio_per_10": None,
            "allotment_price": None,
            "allotment_shares": None,
            "source": "eastmoney",
            "scheme_description": None,
        })

    cn_lookup: Dict[tuple, Dict[str, Any]] = {}
    for _, row in df_cn_div.iterrows():
        ev_date = _to_date(row.get("实施方案公告日期"))
        if not ev_date:
            continue
        cn_lookup[(code, ev_date)] = {
            "派息比例": row.get("派息比例"),
            "送股比例": row.get("送股比例"),
            "转增比例": row.get("转增比例"),
            "分红类型": row.get("分红类型"),
            "报告时间": row.get("报告时间"),
            "派息日": row.get("派息日"),
            "股权登记日": row.get("股权登记日"),
            "实施方案分红说明": row.get("实施方案分红说明"),
        }

    for ev in events:
        ev_date = date.fromisoformat(ev["event_date"])
        cn_match = cn_lookup.get((code, ev_date))
        if cn_match:
            ev["report_year"] = _report_year_from_cninfo(
                cn_match["报告时间"], ev_date,
            )
            if cn_match["实施方案分红说明"]:
                ev["scheme_description"] = str(cn_match["实施方案分红说明"])
            pay = _to_date(cn_match["派息日"])
            if pay:
                ev["payment_date"] = pay.isoformat()
            rec = _to_date(cn_match["股权登记日"])
            if rec and not ev["record_date"]:
                ev["record_date"] = rec.isoformat()
            ev["source"] = "merged"

    for _, row in df_em_allot.iterrows():
        ev_date = _to_date(row.get("公告日期"))
        if not ev_date:
            continue
        ratio_str = str(row.get("配股比例") or "")
        ratio_num = 0.0
        for part in ratio_str.replace(":", "").split("配"):
            if part.isdigit():
                ratio_num = float(part)
                break
        events.append({
            "company_name": company_name,
            "stock_code": code,
            "report_year": ev_date.year,
            "report_period": "FY",
            "event_type": "allotment",
            "event_date": ev_date.isoformat(),
            "ex_date": _to_date(row.get("除权除息日")).isoformat() if _to_date(row.get("除权除息日")) else None,
            "record_date": _to_date(row.get("股权登记日")).isoformat() if _to_date(row.get("股权登记日")) else None,
            "payment_date": None,
            "listing_date": None,
            "status": str(row.get("进度") or "").strip() or None,
            "cash_per_10_shares": None,
            "bonus_shares_per_10": None,
            "capitalized_shares_per_10": None,
            "allotment_ratio_per_10": ratio_num if ratio_num > 0 else None,
            "allotment_price": float(row.get("配股价格") or 0) or None,
            "allotment_shares": None,
            "source": "eastmoney",
            "scheme_description": None,
        })

    logger.info("股本变动事件拉取完成 %s: %d 条", code, len(events))
    return events
