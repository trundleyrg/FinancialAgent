"""
Agent 工具模块

提供 Agent 使用的各种工具，包括数据库查询、财务计算和市场数据
"""
from .db_tools import (
    get_db_tools,
    get_all_financial_data,
    get_multi_year_financial_data,
    get_balance_sheet,
    get_income_statement,
    get_cash_flow,
    check_company_data_availability,
)
from .calculation_tools import (
    get_calculation_tools,
    calculate_profitability,
    calculate_liquidity,
    calculate_solvency,
    calculate_growth,
    calculate_cyclical_metrics,
)
from src.stock_tools.market_data_tool import (
    get_market_data_tools,
    get_stock_market_data,
    get_stock_valuation_history,
    get_dividend_history,
    get_dividend_stats,
)

__all__ = [
    # DB tools
    "get_db_tools",
    "get_all_financial_data",
    "get_multi_year_financial_data",
    "get_balance_sheet",
    "get_income_statement",
    "get_cash_flow",
    "check_company_data_availability",
    # Calculation tools
    "get_calculation_tools",
    "calculate_profitability",
    "calculate_liquidity",
    "calculate_solvency",
    "calculate_growth",
    "calculate_cyclical_metrics",
    # Market data tools
    "get_market_data_tools",
    "get_stock_market_data",
    "get_stock_valuation_history",
    "get_dividend_history",
    "get_dividend_stats",
]
