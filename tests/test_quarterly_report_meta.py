"""报告元信息解析：(report_year, report_period)。

覆盖年报 / 半年报 / 一季报 / 三季报四种首页标题。
"""

import pytest

from src.tools.chapter_extractor import parse_report_period


@pytest.mark.parametrize(
    "text,expected",
    [
        # 年报：首页首行是 "河南羚锐制药股份有限公司2024 年年度报告"
        (
            "河南羚锐制药股份有限公司2024 年年度报告\n1 / 222\n公司代码：600285\n"
            "河南羚锐制药股份有限公司\n2024 年年度报告\n",
            (2024, "FY"),
        ),
        # 半年报：旧逻辑会误判成 FY（"半年度报告" 命中 "年度报告"）
        (
            "河南羚锐制药股份有限公司2025 年半年度报告\n1 / 175\n公司代码：600285\n"
            "河南羚锐制药股份有限公司\n2025 年半年度报告\n",
            (2025, "H1"),
        ),
        # 一季报：旧逻辑 year=0
        (
            "河南羚锐制药股份有限公司2025 年第一季度报告\n1 / 12\n证券代码：600285\n"
            "河南羚锐制药股份有限公司\n2025 年第一季度报告\n",
            (2025, "Q1"),
        ),
        # 三季报：旧逻辑 year=0
        (
            "河南羚锐制药股份有限公司2025 年第三季度报告\n1 / 12\n证券代码：600285\n"
            "河南羚锐制药股份有限公司\n2025 年第三季度报告\n",
            (2025, "Q3"),
        ),
    ],
)
def test_parse_report_period_by_title_line(text, expected):
    assert parse_report_period(text) == expected


def test_parse_report_period_prefers_first_title_line():
    """正文里出现其他年份时，仍以首页第一个标题行为准。"""
    text = (
        "羚锐制药2025 年第三季度报告\n"
        "公司代码：600285\n"
        "上年同期 2024 年第三季度报告营业收入对比\n"
    )
    assert parse_report_period(text) == (2025, "Q3")


def test_parse_report_period_returns_zero_when_absent():
    assert parse_report_period("没有任何报告标题的文本") == (0, None)


def test_parse_report_period_fallback_without_year_in_title():
    """标题行没有年份时回退到关键词判定，半年报仍必须是 H1。"""
    text = "半年度报告\n主要会计数据\n"
    assert parse_report_period(text) == (0, "H1")


def test_parse_report_period_fallback_extracts_year_from_keyword_line():
    text = "羚锐制药2023年年度报告（更正后）\n"
    assert parse_report_period(text) == (2023, "FY")
