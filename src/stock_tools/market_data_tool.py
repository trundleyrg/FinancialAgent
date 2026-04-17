"""
市场数据工具

通过 akshare 获取 A 股实时行情、估值指标（PE/PB）和分红历史
"""

import datetime
import traceback
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.utils.logger import manager

logger = manager.get_logger("Agent.MarketData", "market_data.log")


def _normalize_stock_code(stock_code: str) -> str:
    """标准化股票代码（去除市场前缀，保留 6 位数字）"""
    code = stock_code.strip().upper()
    for prefix in ("SH", "SZ", "BJ", "SH.", "SZ.", "BJ."):
        if code.startswith(prefix):
            code = code[len(prefix) :]
    return code.zfill(6)


def _ensure_market_prefix(stock_code: str) -> str:
    """
    确保股票代码带有市场前缀

    根据代码范围自动判断交易所并补充前缀：
    - SZ (深圳): 000xxx, 001xxx, 002xxx, 003xxx, 200xxx
    - SH (上海): 600xxx, 601xxx, 603xxx, 605xxx, 688xxx
    - BJ (北京): 830xxx, 870xxx, 889xxx

    Args:
        stock_code: 6 位股票代码，如 "000423" 或 "SZ000423"

    Returns:
        带市场前缀的股票代码，如 "SZ000423"
    """
    code = _normalize_stock_code(stock_code)

    # 已在外部做了标准化，此时 code 一定是 6 位纯数字
    if code.startswith(("000", "001", "002", "003", "200")):
        return "SZ" + code
    elif code.startswith(("600", "601", "603", "605", "688")):
        return "SH" + code
    elif code.startswith(("830", "870", "889")):
        return "BJ" + code
    else:
        # 未知代码，默认深交所
        logger.warning(f"未知股票代码 {code}，默认使用深交所")
        return "SZ" + code


def get_stock_basic_info(stock_code: str) -> Dict[str, Any]:
    """
    获取股票基础信息（名称、行业、地区、上市日期等）

    使用 akshare 获取股票基础信息，只返回 xq.md 中标记为"是否返回"=1 的字段。

    Args:
        stock_code: 6 位股票代码，如 "000423" 或 "SZ000423"

    Returns:
        {
            "org_name_cn": str,              # 公司中文全称
            "org_short_name_cn": str,        # 公司中文简称
            "main_operation_business": str,  # 主营业务
            "operating_scope": str,          # 经营范围
            "org_cn_introduction": str,      # 公司简介
            "org_website": str,              # 官网
            "listed_date": str,              # 上市日期（时间戳）
            "provincial_name": str,          # 所在省份
            "classi_name": str,              # 分类名称
            "affiliate_industry": dict,      # 所属行业 {"ind_code": str, "ind_name": str}
            "error": str | None
        }
    """
    RETURN_FIELDS = {
        "org_name_cn",
        "org_short_name_cn",
        "main_operation_business",
        "operating_scope",
        "org_cn_introduction",
        "org_website",
        "listed_date",
        "provincial_name",
        "classi_name",
        "affiliate_industry",
    }

    try:
        # 从雪球获取股票基础信息
        # 标准化股票代码并添加市场前缀（xq API 需要前缀如 SZ000423）
        code = _ensure_market_prefix(stock_code)

        stock_individual_basic_info_xq_df = ak.stock_individual_basic_info_xq(symbol=code)
        result = {
            row["item"]: row["value"]
            for _, row in stock_individual_basic_info_xq_df.iterrows()
            if row["item"] in RETURN_FIELDS
        }
        return result
    except Exception:
        logger.error(traceback.format_exc())
        return {"error": traceback.format_exc()}


def get_stock_financial_indicator(
    stock_code: str,
    start_year: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取股票主要财务指标

    使用 akshare 的 stock_financial_analysis_indicator 接口，
    数据来源：新浪财经-财务分析-财务指标

    Args:
        stock_code: 6 位股票代码，如 "000423" 或 "600004"
        start_year: 开始查询的年份，默认近 5 年

    Returns:
        {
            "stock_code": str,
            "start_year": str,
            "data": List[Dict],  # 每行数据，key 为字段名，value 为值
            "fields": List[str],  # 所有字段名列表
            "count": int,         # 数据行数
            "error": str | None
        }
    """
    code = _normalize_stock_code(stock_code)
    if start_year is None:
        start_year = str(datetime.date.today().year - 5)

    result: Dict[str, Any] = {
        "stock_code": code,
        "start_year": start_year,
        "data": [],
        "fields": [],
        "count": 0,
        "error": None,
    }

    try:
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
        if df is None or df.empty:
            logger.warning(f"财务指标数据为空: {code}")
            return result

        # 字段名列表
        result["fields"] = list(df.columns)

        # 数据行
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                val = row[col]
                # 转换 numpy/pandas 类型为 Python 原生类型
                if hasattr(val, "item"):
                    val = val.item()
                elif hasattr(val, "to_pydatetime"):
                    val = str(val.to_pydatetime()) if not pd.isna(val) else None
                record[col] = (
                    None if (val is None or (isinstance(val, float) and val != val)) else val
                )
            result["data"].append(record)

        result["count"] = len(result["data"])
        logger.info(
            f"财务指标获取成功: {code}, {result['count']} 条, {len(result['fields'])} 个字段"
        )

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"获取财务指标失败 {code}: {e}")
        logger.error(traceback.format_exc())

    return result


def get_stock_valuation_history(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    存在问题，需要修改
    获取股票历史估值数据（每日 PE/PB）

    数据来源：乐咕乐股（涵盖近 10 年日频 PE/PB）

    Args:
        stock_code: 6 位股票代码
        start_date: 开始日期，格式 "YYYY-MM-DD"，默认近一年
        end_date:   结束日期，格式 "YYYY-MM-DD"，默认今天

    Returns:
        按日期升序排列的估值列表，每项包含 date / pe / pb
    """
    code = _normalize_stock_code(stock_code)
    if end_date is None:
        end_date = datetime.date.today().isoformat()
    if start_date is None:
        start_date = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()

    try:
        import akshare as ak

        df = ak.stock_a_indicator_lg(symbol=code)
        # 列名：trade_date, pe, pb, ps, dv_ratio, dv_ttm, total_mv
        if df is None or df.empty:
            logger.warning(f"估值历史数据为空: {code}")
            return []

        df = df.rename(columns={"trade_date": "date"})
        df["date"] = df["date"].astype(str)
        df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
        df = df.sort_values("date")

        records = []
        for _, row in df.iterrows():

            def _f(v):
                try:
                    fv = float(v)
                    return fv if fv == fv else 0.0
                except (TypeError, ValueError):
                    return 0.0

            records.append({
                "date": str(row.get("date", "")),
                "pe": _f(row.get("pe")),
                "pb": _f(row.get("pb")),
                "ps": _f(row.get("ps", 0)),
                "dv_ratio": _f(row.get("dv_ratio", 0)),  # 股息率（%）
                "total_mv": _f(row.get("total_mv", 0)),  # 总市值（万元）
            })

        logger.info(f"估值历史获取成功: {code}, 共 {len(records)} 条")
        return records

    except Exception as e:
        logger.error(f"获取估值历史失败 {code}: {e}")
        return []


def get_dividend_history(stock_code: str) -> List[Dict[str, Any]]:
    """
    获取股票历史分红数据

    Args:
        stock_code: 6 位股票代码

    Returns:
        按公告日期降序排列的分红列表，每项包含：
        - report_date:    分红方案公告日
        - dividend_date:  除权除息日
        - cash_per_share: 每股分红（元，税前）
        - shares_before:  分红前股本（万股）
        - payout_ratio:   分红方案描述
    """
    code = _normalize_stock_code(stock_code)
    try:
        import akshare as ak

        df = ak.stock_history_dividend_detail(symbol=code, indicator={"分红", "配股"})
        if df is None or df.empty:
            logger.warning(f"无分红历史数据: {code}")
            return []

        records = []
        for _, row in df.iterrows():

            def _s(v):
                return str(v).strip() if v is not None else ""

            def _f(v, default=0.0):
                try:
                    fv = float(str(v).replace(",", ""))
                    return fv if fv == fv else default
                except (TypeError, ValueError):
                    return default

            records.append({
                "report_date": _s(row.get("公告日期", "")),
                "dividend_date": _s(row.get("除权除息日", "")),
                "cash_per_share": _f(row.get("派息(税前)(元)", row.get("每股送转", 0))),
                "payout_ratio": _s(row.get("方案说明", "")),
            })

        records.sort(key=lambda x: x["report_date"], reverse=True)
        logger.info(f"分红历史获取成功: {code}, 共 {len(records)} 条")
        return records
    except Exception as e:
        logger.error(f"获取分红历史失败 {code}: {e}")
        return []


def get_market_data_tools():
    """返回所有市场数据工具函数列表"""
    return [
        get_stock_valuation_history,
        get_dividend_history,
        get_stock_financial_indicator,
    ]
