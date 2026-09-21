"""红利股 skill 专属工具：从财务数据提取分红信息，DB 优先读分红统计。"""
from __future__ import annotations

import logging
from typing import Any, Dict

from src.tools.market_data_tool import get_dividend_stats

logger = logging.getLogger("Skills.Dividend")


def extract_dividend_info(financial_data: Dict[str, Any]) -> Dict[str, Any]:
    """从财务数据中提取分红相关信息。

    数据来源优先级：
    1. 现金流量表 cash_for_dividend_and_interest（实际现金分红支出）
    2. 计算自由现金流 = 经营活动现金流 - 购建固定资产现金支出

    Args:
        financial_data: 财务数据字典（含 balance_sheet / income_statement / cash_flow）

    Returns:
        分红信息字典
    """
    income_statement = financial_data.get("income_statement", {})
    cash_flow = financial_data.get("cash_flow", {})

    net_profit = income_statement.get("net_profit", 0) or 0
    operating_cash_flow = (
        cash_flow.get("net_cash_from_operations", 0)
        or cash_flow.get("operating_cash_flow", 0)
        or 0
    )

    # 实际现金分红支出（来自现金流量表"分配股利、利润或偿付利息支付的现金"）
    cash_dividend_paid = cash_flow.get("cash_for_dividend_and_interest", 0) or 0

    # 自由现金流 = 经营现金流 - 购建固定资产等资本支出
    capex = cash_flow.get("cash_for_fixed_assets", 0) or 0
    free_cash_flow = operating_cash_flow - capex

    payout_ratio = (cash_dividend_paid / net_profit * 100) if net_profit > 0 else 0
    fcf_coverage = (free_cash_flow / cash_dividend_paid) if cash_dividend_paid > 0 else 0

    return {
        "net_profit": net_profit,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
        "cash_dividend_paid": cash_dividend_paid,   # 实际现金分红支出（元）
        "payout_ratio": round(payout_ratio, 2),      # 分红率（%）
        "fcf_coverage": round(fcf_coverage, 2),      # 自由现金流对分红覆盖倍数
    }


def get_dividend_stats_with_fallback(
    stock_code: str, years: int = 5,
) -> Dict[str, Any]:
    """DB 优先读 CapitalChangeEventRepository；空时退到 akshare 实时拉取。"""
    try:
        from src.db import CapitalChangeEventRepository, ReportKey
        from src.db.db_connector import get_db
        repo = CapitalChangeEventRepository(get_db())
        events = repo.list_events(ReportKey(stock_code=stock_code))
        if events:
            stats = repo.aggregate_dividend_stats(
                ReportKey(stock_code=stock_code), years=years,
            )
            stats["source"] = "db"
            stats["total_event_count"] = len(events)
            return stats
    except Exception as exc:
        logger.warning(
            "DB 分红读取失败 (%s): %s — fallback 到实时拉取",
            stock_code, exc,
        )
    stats = get_dividend_stats(stock_code, years=years)
    if isinstance(stats, dict):
        stats["source"] = "live"
    return stats