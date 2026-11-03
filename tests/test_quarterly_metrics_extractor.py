"""季报 KPI 抽取器。"""
from pathlib import Path

import pytest

from src.tools.quarterly_metrics_extractor import (
    QuarterlyMetricsExtractor,
    normalize_metric_label,
    parse_metric_value,
)

Q1_PDF = Path("data/600285/羚锐制药_600285_2025Q1.pdf")
Q3_PDF = Path("data/600285/羚锐制药_600285_2025Q3.pdf")
H1_PDF = Path("data/600285/羚锐制药_600285_2025H1.pdf")


# ── 纯函数 ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("营业收入", "营业收入"),
        ("归属于上市公司股东的\n净利润", "归属于上市公司股东的净利润"),
        ("归属于上市公司股东的扣除非 经常性损益的净利润",
         "归属于上市公司股东的扣除非经常性损益的净利润"),
        ("基本每股收益（元/股）", "基本每股收益"),
        ("基本每股收益（元／股）", "基本每股收益"),
        ("加权平均净资产收益率 （%）", "加权平均净资产收益率"),
        ("  归属于上市公司股东的所有者 权益 ", "归属于上市公司股东的所有者权益"),
    ],
)
def test_normalize_metric_label(raw, expected):
    assert normalize_metric_label(raw) == expected


def test_normalize_keeps_deducted_eps_distinct():
    """扣非 EPS 不能被误认成基本 EPS。"""
    a = normalize_metric_label("基本每股收益（元/股）")
    b = normalize_metric_label("扣除非经常性损益后的基本每股收益（元/股）")
    assert a != b


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,020,755,870.55", 1020755870.55),
        ("-785,773,789.02", -785773789.02),
        ("0.383", 0.383),
        ("不适用", None),
        ("", None),
        ("增加0.22 个百分点", None),
        ("减少0.17 个 百分点", None),
    ],
)
def test_parse_metric_value(raw, expected):
    assert parse_metric_value(raw) == expected


# ── 真实 PDF ────────────────────────────────────────────────────

@pytest.mark.skipif(not Q1_PDF.exists(), reason="缺 Q1 夹具")
def test_extract_q1():
    data = QuarterlyMetricsExtractor(str(Q1_PDF)).extract()
    cur = data["CURRENT"]
    assert cur["operating_revenue"] == 1020755870.55
    assert cur["net_profit_attributable_to_parent"] == 216817540.12
    assert cur["net_profit_deducted_non_recurring"] == 203920717.25
    assert cur["net_cash_from_operations"] == 117615900.12
    assert cur["basic_eps"] == 0.383
    assert cur["diluted_eps"] == 0.382
    assert cur["weighted_roe"] == 6.81
    assert cur["total_assets"] == 5410895780.92
    assert cur["total_equity_attributable_to_parent"] == 3311522505.91
    # 一季报没有「年初至报告期末」块
    assert "YTD" not in data


@pytest.mark.skipif(not Q3_PDF.exists(), reason="缺 Q3 夹具")
def test_extract_q3_has_current_and_ytd():
    data = QuarterlyMetricsExtractor(str(Q3_PDF)).extract()
    cur, ytd = data["CURRENT"], data["YTD"]
    # 本报告期 = 7-9 月单季
    assert cur["operating_revenue"] == 942156123.36
    assert cur["net_profit_attributable_to_parent"] == 176546803.24
    # 年初至报告期末 = 1-9 月累计
    assert ytd["operating_revenue"] == 3041361639.17
    assert ytd["net_profit_attributable_to_parent"] == 650932609.77
    assert ytd["net_cash_from_operations"] == 490387656.36
    assert ytd["basic_eps"] == 1.148
    assert ytd["weighted_roe"] == 20.40
    # 期末指标进 CURRENT
    assert cur["total_assets"] == 5755687724.88
    assert cur["total_equity_attributable_to_parent"] == 3248239730.07


@pytest.mark.skipif(not H1_PDF.exists(), reason="缺 H1 夹具")
def test_extract_h1():
    data = QuarterlyMetricsExtractor(str(H1_PDF)).extract()
    cur = data["CURRENT"]
    assert cur["operating_revenue"] == 2099205515.81
    assert cur["total_profit"] == 551547542.75
    assert cur["net_profit_attributable_to_parent"] == 474385806.53
    assert cur["net_cash_from_operations"] == 355587506.75
    assert cur["basic_eps"] == 0.836
    assert cur["weighted_roe"] == 14.65
    assert cur["total_assets"] == 5572227469.60
    assert cur["total_equity_attributable_to_parent"] == 3066393164.32
