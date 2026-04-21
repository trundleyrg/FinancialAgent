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


def get_dividend_history(stock_code: str) -> List[Dict[str, Any]]:
    """
    获取股票历史分红与配股数据

    Args:
        stock_code: 6 位股票代码

    Returns:
        按公告日期降序排列的事件列表，每项包含：
        - report_date:    分红/配股方案公告日
        - dividend_date:  除权除息日
        - cash_per_share: 每股分红（元，税前），仅分红事件有值
        - allotment_price: 配股价格（元），仅配股事件有值
        - allotment_ratio: 配股比例（如 10配3），仅配股事件有值
        - payout_ratio:   方案说明
        - event_type:     事件类型 ("分红" 或 "配股")
    """
    code = _normalize_stock_code(stock_code)
    records = []

    def _s(v):
        return str(v).strip() if v is not None else ""

    def _f(v, default=0.0):
        try:
            fv = float(str(v).replace(",", ""))
            return fv if fv == fv else default
        except (TypeError, ValueError):
            return default

    try:
        # 查询分红记录
        df_dividend = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
        if df_dividend is not None and not df_dividend.empty:
            for _, row in df_dividend.iterrows():
                records.append({
                    "report_date": _s(row.get("公告日期", "")),
                    "dividend_date": _s(row.get("除权除息日", "")),
                    "cash_per_share": _f(row.get("派息(税前)(元)", 0)),
                    "allotment_price": None,
                    "allotment_ratio": None,
                    "payout_ratio": _s(row.get("方案说明", "")),
                    "event_type": "分红",
                })

        # 查询配股记录
        df_allotment = ak.stock_history_dividend_detail(symbol=code, indicator="配股")
        if df_allotment is not None and not df_allotment.empty:
            for _, row in df_allotment.iterrows():
                records.append({
                    "report_date": _s(row.get("公告日期", "")),
                    "dividend_date": _s(row.get("除权除息日", "")),
                    "cash_per_share": None,
                    "allotment_price": _f(row.get("配股价格", 0)),
                    "allotment_ratio": _s(row.get("配股比例", "")),
                    "payout_ratio": _s(row.get("方案说明", "")),
                    "event_type": "配股",
                })

        if not records:
            logger.warning(f"无分红或配股历史数据: {code}")
            return []

        records.sort(key=lambda x: x["report_date"], reverse=True)
        logger.info(f"分红与配股历史获取成功: {code}, 共 {len(records)} 条")
        return records

    except Exception as e:
        logger.error(f"获取分红与配股历史失败 {code}: {e}")
        return []


def get_stock_pe_pb_history(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adjust: str = "",
) -> List[Dict[str, Any]]:
    """
    获取股票指定日期范围内的PB和PE变化

    使用 stock_zh_a_hist 获取历史行情数据（支持复权方式），
    使用 stock_zh_valuation_baidu 获取市净率(PB)历史数据。

    Args:
        stock_code: 6 位股票代码，如 "000423" 或 "600004"
        start_date: 开始日期，格式 "YYYY-MM-DD"，默认近一年
        end_date: 结束日期，格式 "YYYY-MM-DD"，默认今天
        adjust: 复权方式，""=不复权，"qfq"=前复权，"hfq"=后复权，默认不复权

    Returns:
        按日期升序排列的估值列表，每项包含：
        - date: 交易日（YYYY-MM-DD）
        - close: 收盘价
        - pb: 市净率
        - error: str | None
    """
    code = _normalize_stock_code(stock_code)
    if end_date is None:
        end_date = datetime.date.today().isoformat()
    if start_date is None:
        start_date = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()

    # 转换日期格式为 YYYYMMDD
    start_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")

    result: List[Dict[str, Any]] = []

    try:
        # 获取历史行情数据（支持复权方式）
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_str,
            end_date=end_str,
            adjust=adjust,
        )

        if df is None or df.empty:
            logger.warning(f"历史行情数据为空: {code}, adjust={adjust}")
            return result

        # 获取 PB 历史数据（来自百度估值）
        pb_df = ak.stock_zh_valuation_baidu(symbol=code, indicator="市净率", period="全部")
        pb_dict = {}
        if pb_df is not None and not pb_df.empty:
            for _, row in pb_df.iterrows():
                date_val = str(row.get("date", ""))
                pb_val = row.get("value")
                if date_val and pb_val is not None:
                    pb_dict[date_val] = float(pb_val) if not pd.isna(pb_val) else None

        # 遍历历史数据，匹配 PB
        for _, row in df.iterrows():
            date_val = str(row.get("日期", ""))
            close = float(row.get("收盘", 0))

            # 匹配 PB 数据
            pb = pb_dict.get(date_val)

            result.append({
                "date": date_val,
                "close": round(close, 2),
                "pb": pb,
            })

        logger.info(f"PE/PB历史获取成功: {code}, adjust={adjust}, 共 {len(result)} 条")

    except Exception as e:
        logger.error(f"获取PE/PB历史失败 {code}: {e}")
        logger.error(traceback.format_exc())
        return [{"error": str(e)}]

    return result


def get_market_data_tools():
    """返回所有市场数据工具函数列表"""
    return [
        get_stock_pe_pb_history,
        get_stock_valuation_history,
        get_dividend_history,
        get_stock_financial_indicator,
    ]
