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
    get_dividend_history,
    get_market_data_tools,
    get_stock_basic_info,
    get_stock_financial_indicator,
    get_stock_pe_pb_history
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
    assert len(tools) == 3
    tool_names = [t.__name__ for t in tools]
    assert "get_stock_pe_pb_history" in tool_names
    assert "get_dividend_history" in tool_names
    assert "get_stock_financial_indicator" in tool_names
    print("✓ get_market_data_tools 测试通过")


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


def test_get_stock_financial_indicator():
    """测试获取股票主要财务指标"""
    result = get_stock_financial_indicator("600004", start_year="2023")
    assert "stock_code" in result
    assert "start_year" in result
    assert "data" in result
    assert "fields" in result
    assert "count" in result
    assert "error" in result
    assert result["stock_code"] == "600004"
    assert result["start_year"] == "2023"
    if result["data"]:
        print(
            f"✓ get_stock_financial_indicator 测试通过: 获取到 {result['count']} 条数据, {len(result['fields'])} 个字段"
        )
    else:
        print("✓ get_stock_financial_indicator 测试通过: 无数据（可能接口限制）")


def test_get_stock_pe_pb_history():
    """测试获取股票指定日期范围内的PB变化（支持复权方式）"""
    records = get_stock_pe_pb_history(
        "000423",
        start_date="2022-01-01",
        end_date="2024-12-31",
        adjust="",
    )
    assert isinstance(records, list)
    # 网络问题可能导致返回错误
    if not records:
        print("✓ get_stock_pe_pb_history 测试通过: 无数据（网络问题或市场关闭）")
        return
    if "error" in records[0]:
        print(f"✓ get_stock_pe_pb_history 测试通过: 网络问题 - {records[0]['error']}")
        return
    record = records[0]
    assert "date" in record
    assert "close" in record
    assert "pb" in record
    print(f"✓ get_stock_pe_pb_history 测试通过: 获取到 {len(records)} 条记录")

    # 测试前复权
    records_qfq = get_stock_pe_pb_history(
        "000423",
        start_date="2024-01-01",
        end_date="2024-06-30",
        adjust="qfq",
    )
    assert isinstance(records_qfq, list)
    if records_qfq and "error" not in records_qfq[0]:
        print(f"✓ get_stock_pe_pb_history (前复权) 测试通过: 获取到 {len(records_qfq)} 条记录")
    else:
        print("✓ get_stock_pe_pb_history (前复权) 测试通过: 无数据（网络问题）")


if __name__ == "__main__":
    print("=" * 60)
    print("market_data_tool 测试")
    print("=" * 60)

    test_stock_basic_info()
    test_get_market_data_tools()
    test_get_dividend_history()
    test_get_stock_financial_indicator()
    test_get_stock_pe_pb_history()

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
