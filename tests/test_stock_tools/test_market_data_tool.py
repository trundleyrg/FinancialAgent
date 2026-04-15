"""
market_data_tool 测试

测试 src/stock_tools/market_data_tool.py 中注册的工具函数
"""
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.stock_tools.market_data_tool import (
    get_stock_market_data,
    get_stock_valuation_history,
    get_dividend_history,
    get_dividend_stats,
    get_market_data_tools,
    get_stock_basic_info
)

def test_stock_basic_info():
    """测试获取股票基本信息（返回 xq.md 中标记为"是否返回"=1 的字段）"""
    info = get_stock_basic_info("SZ000423")
    # 检查 xq.md 中"是否返回"=1 的字段
    assert "org_name_cn" in info
    assert "org_short_name_cn" in info
    assert "main_operation_business" in info
    assert "operating_scope" in info
    assert "org_cn_introduction" in info
    assert "org_website" in info
    assert "listed_date" in info
    assert "provincial_name" in info
    assert "classi_name" in info
    assert "affiliate_industry" in info
    assert info["org_short_name_cn"] == "东阿阿胶"
    print(f"✓ get_stock_basic_info 测试通过: {info['org_short_name_cn']}")



def test_get_market_data_tools():
    """测试 get_market_data_tools 返回正确的函数列表"""
    tools = get_market_data_tools()
    assert len(tools) == 4
    tool_names = [t.__name__ for t in tools]
    assert "get_stock_market_data" in tool_names
    assert "get_stock_valuation_history" in tool_names
    assert "get_dividend_history" in tool_names
    assert "get_dividend_stats" in tool_names
    print("✓ get_market_data_tools 测试通过")


def test_get_stock_market_data():
    """测试获取股票实时市场数据"""
    result = get_stock_market_data("000423")
    assert "stock_code" in result
    assert "stock_name" in result
    assert "current_price" in result
    assert "market_cap" in result
    assert "pe_ratio" in result
    assert "pb_ratio" in result
    assert "error" in result
    assert result["stock_code"] == "000423"
    print(f"✓ get_stock_market_data 测试通过: {result['stock_name']}, 价格={result['current_price']}, PE={result['pe_ratio']}, PB={result['pb_ratio']}")


def test_get_stock_valuation_history():
    """测试获取股票历史估值数据（近5年）"""
    records = get_stock_valuation_history("000423")
    # 允许为空数据（节假日等因素），但返回应该是列表
    assert isinstance(records, list)
    if records:
        record = records[0]
        assert "date" in record
        assert "pe" in record
        assert "pb" in record
        print(f"✓ get_stock_valuation_history 测试通过: 获取到 {len(records)} 条记录")
    else:
        print("✓ get_stock_valuation_history 测试通过: 无历史数据（可能市场关闭）")


def test_get_dividend_history():
    """测试获取股票历史分红数据"""
    history = get_dividend_history("000423")
    assert isinstance(history, list)
    if history:
        record = history[0]
        assert "report_date" in record
        assert "dividend_date" in record
        assert "cash_per_share" in record
        print(f"✓ get_dividend_history 测试通过: 获取到 {len(history)} 条分红记录")
    else:
        print("✓ get_dividend_history 测试通过: 无分红记录")


def test_get_dividend_stats():
    """测试分红统计（近5年）"""
    stats = get_dividend_stats("000423", years=5)
    assert "total_dividends" in stats
    assert "consecutive_years" in stats
    assert "avg_cash_per_share" in stats
    assert "max_cash_per_share" in stats
    assert "dividend_years" in stats
    assert "latest_cash_per_share" in stats
    print(f"✓ get_dividend_stats 测试通过: 总分红次数={stats['total_dividends']}, 连续年数={stats['consecutive_years']}, 平均每股分红={stats['avg_cash_per_share']}")


if __name__ == "__main__":
    print("=" * 60)
    print("market_data_tool 测试")
    print("=" * 60)

    test_stock_basic_info()
    test_get_market_data_tools()
    test_get_stock_market_data()
    test_get_stock_valuation_history()
    test_get_dividend_history()
    test_get_dividend_stats()

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
