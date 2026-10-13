"""_parse_table_data_to_model_data 匹配逻辑的回归测试。

关键场景:子串匹配宽松导致 A:「负债合计」错配到 total_current_liabilities。
修复:help_text 应作为 item_name 的**后缀**匹配(item.endswith(help_text)),
而非字符串 reverse。
"""
import sys
sys.path.insert(0, '.')

import pytest

from src.db.db_connector import _parse_table_data_to_model_data
from src.db.models import ConsolidatedBalanceSheet


def test_match_liab_total_to_total_liabilities_not_current():
    """row[0]='负债合计' 应匹配 total_liabilities(而非 total_current_liabilities)。

    bug 复现:
        旧匹配:`'负债合计' in '流动负债合计'` → True → 错把"负债合计"27.55亿
        存到 total_current_liabilities。total_liabilities 永远 None。
    期望:精确匹配 → total_liabilities 拿到 27.55亿,total_current_liabilities 留 None。
    """
    # 模拟 row[88] 的实际 PDF 行
    table_data = [
        # header 行
        ["项目", "本期金额", "上期金额"],
        # row[73] 流动负债合计(模拟实际)
        ["流动负债合计", "2,611,416,360.92", "2,406,763,444.39"],
        # row[88] 负债合计(关键测试行)
        ["负债合计", "2,755,244,398.98", "2,565,744,617.42"],
    ]

    result = _parse_table_data_to_model_data(
        table_data,
        ConsolidatedBalanceSheet,
        unit_str="元",
    )

    assert result.get("total_liabilities") == 2_755_244_398.98, (
        f"total_liabilities 应拿 27.55亿, 实际 {result.get('total_liabilities')}"
    )
    # total_current_liabilities 应被单独赋值(来自流动负债合计行),与 total_liabilities 不冲突
    assert result.get("total_current_liabilities") == 2_611_416_360.92


def test_match_total_assets_exact():
    """'资产总计' 匹配 total_assets(财会标准用法,000423 实际 PDF)。"""
    table_data = [
        ["项目", "本期金额"],
        ["资产总计", "13,087,136,728.33"],
    ]
    result = _parse_table_data_to_model_data(
        table_data, ConsolidatedBalanceSheet, unit_str="元",
    )
    assert result.get("total_assets") == 13_087_136_728.33


def test_match_leave_liab_suffix_unmatched():
    """未识别的项目名(无对应 help_text)→ 不写入 model_data,也不报错。"""
    table_data = [
        ["项目", "本期金额"],
        ["完全没见过的科目", "999,999,999"],
    ]
    result = _parse_table_data_to_model_data(
        table_data, ConsolidatedBalanceSheet, unit_str="元",
    )
    assert "完全没见过的科目" not in str(result)
    assert result == {} or all(
        v is None for v in result.values()
    ) or all(
        k.startswith("total_") is False for k in result.keys()
    )


def test_part_extract_with_unit_factor():
    """单位换算:万元 → 元(乘 10000)。"""
    table_data = [
        ["项目", "本期金额"],
        ["资产总计", "1,308,713.67"],
    ]
    result = _parse_table_data_to_model_data(
        table_data, ConsolidatedBalanceSheet, unit_str="万元",
    )
    # 1,308,713.67 万 = 13,087,136,700 元(允许浮点误差)
    assert abs(result["total_assets"] - 13_087_136_700) < 100


def test_partial_sums_unaffected_by_robust_match():
    """修复后,负债合计 与 流动负债合计 不应互相覆盖。"""
    table_data = [
        ["流动负债合计", "100"],
        ["非流动负债合计", "200"],
        ["负债合计", "300"],  # = 100+200
    ]
    result = _parse_table_data_to_model_data(
        table_data, ConsolidatedBalanceSheet, unit_str="元",
    )
    assert result.get("total_current_liabilities") == 100
    assert result.get("total_non_current_liabilities") == 200
    assert result.get("total_liabilities") == 300