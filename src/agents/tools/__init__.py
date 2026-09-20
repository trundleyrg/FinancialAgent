"""兼容 shim：原 src/agents/tools/ 内容已迁移至 src/tools/。

此模块将在 Task 3 完成后删除。
"""
from src.tools.db_tools import (  # noqa: F401
    get_db_tools,
    get_all_financial_data,
    get_multi_year_financial_data,
    get_balance_sheet,
    get_income_statement,
    get_cash_flow,
    check_company_data_availability,
)
from src.tools.calculation_tools import (  # noqa: F401
    get_calculation_tools,
    calculate_profitability,
    calculate_liquidity,
    calculate_solvency,
    calculate_growth,
    calculate_cyclical_metrics,
)

__all__ = [
    # db_tools
    "get_db_tools",
    "get_all_financial_data",
    "get_multi_year_financial_data",
    "get_balance_sheet",
    "get_income_statement",
    "get_cash_flow",
    "check_company_data_availability",
    # calculation_tools
    "get_calculation_tools",
    "calculate_profitability",
    "calculate_liquidity",
    "calculate_solvency",
    "calculate_growth",
    "calculate_cyclical_metrics",
]