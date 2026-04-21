from src.stock_tools.market_data_tool import (
    get_stock_basic_info,
    get_stock_financial_indicator,
    get_stock_valuation_history,
    get_dividend_history,
    get_dividend_stats,
    get_market_data_tools,
)

stock_market_data_tools = get_stock_financial_indicator("000423", "2023")
print(stock_market_data_tools)
