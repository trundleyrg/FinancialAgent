"""result_persister 测试:主报告整合 dividend_analysis 数据情况 + 判断结果。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.graph.result_persister import (
    build_markdown_report,
    extract_analysis_results,
    load_dividend_data,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_trace_entries():
    """模拟主图 jsonl trace 内容(cyclical + fundamental + summary)。"""
    return [
        {"event_type": "session_start",
         "data": {"company": "东阿阿胶", "stock_code": "000423", "report_year": 2024}},
        {"event_type": "intent_classification",
         "data": {"stock_types": ["defensive"]}},
        {"event_type": "analysis_result", "node_name": "run_cyclical_analysis",
         "data": {"cycle_position": "成熟期", "investment_rating": "HOLD",
                    "reasoning": "周期股分析:稳定", "risk_factors": []}},
        {"event_type": "analysis_result", "node_name": "run_fundamental_analysis",
         "data": {"profitability": {"gross_margin": 70, "net_margin": 25, "roe": 15},
                    "investment_rating": "BUY", "reasoning": "基本面稳健",
                    "risk_factors": []}},
        {"event_type": "summary_result",
         "data": {"final_rating": "BUY", "key_highlights": ["毛利率提升"],
                    "risk_factors": [], "investment_suggestion": "中长期持有"}},
    ]


@pytest.fixture
def dividend_md(tmp_path):
    """制造一份标准的 dividend markdown,return 路径。"""
    md = """# 红利股分析报告 - 测试公司 (999999) 2024年报

## 一、关键指标趋势

![测试公司 红利股关键指标趋势](charts/dividend_trend_2024.png)

| period | 营业收入(亿元) | 归母净利润(亿元) | 分红总金额(亿元) | 拆股情况 | 分红率(%) |
|------|------|------|------|------|------|
| 2022 | 50.00 | 8.00 | 4.50 | 无 | 56.25 |
| 2023 | 55.00 | 10.00 | 7.20 | 无 | 72.00 |
| 2024 | 60.00 | 12.00 | 9.60 | 无 | 80.00 |

> **口径说明**:分红率(%) = 现金分红总额 / 归母净利润 × 100。

---

## 二、关键指标

| 指标 | 数值 |
|------|------|
| 股息率(%) | 4.50 |
| 分红率(%) | 80.00 |
| 连续分红年限(年) | 8 |
| 自由现金流对分红覆盖率(倍) | 1.80 |
| 财务健康度评分(0-100) | 82 |

## 六、风险因素

- 2024 年分红率达 80%,需关注盈利下降时的可持续性
- 高分红可能影响资本支出节奏

## 七、投资评级与理由

**投资评级: BUY**

公司连续 8 年分红,2024 分红率 80% 处于健康水平...
"""
    md_file = tmp_path / "分析报告_分红_测试公司_999999_2024.md"
    md_file.write_text(md, encoding="utf-8")
    return tmp_path


# ──────────────────────────────────────────────────────────────────────────────
# load_dividend_data 测试
# ──────────────────────────────────────────────────────────────────────────────

def test_load_dividend_data_returns_none_when_no_md(tmp_path, monkeypatch):
    """memory_dir 下没有 dividend markdown → return None。"""
    monkeypatch.chdir(tmp_path)
    data = load_dividend_data(tmp_path)
    assert data is None


def test_load_dividend_data_picks_latest_md(tmp_path, monkeypatch):
    """多个 dividend md → 取最新的(按文件名排序)。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "分析报告_分红_X_999999_2023.md").write_text("OLDER", encoding="utf-8")
    (tmp_path / "分析报告_分红_X_999999_2024.md").write_text("NEWER", encoding="utf-8")
    data = load_dividend_data(tmp_path)
    assert data is not None
    assert data["source_md_name"].endswith("_2024.md")


def test_load_dividend_data_extracts_trend_table(tmp_path, monkeypatch, dividend_md):
    """从分红报告 markdown 提取出 5 列趋势表(营业收入/净利/分红总额/拆股/分红率)。"""
    monkeypatch.chdir(dividend_md)
    data = load_dividend_data(dividend_md)

    assert data is not None
    assert "trend_table_md" in data
    assert "营业收入(亿元)" in data["trend_table_md"]
    assert "分红率(%)" in data["trend_table_md"]
    assert "2022" in data["trend_table_md"]
    assert "2024" in data["trend_table_md"]


def test_load_dividend_data_extracts_key_indicators(tmp_path, monkeypatch, dividend_md):
    """从「二、关键指标」段提取 key indicators dict。"""
    monkeypatch.chdir(dividend_md)
    data = load_dividend_data(dividend_md)

    assert "key_indicators" in data
    ind = data["key_indicators"]
    assert ind["股息率(%)"] == "4.50"
    assert ind["分红率(%)"] == "80.00"
    assert ind["连续分红年限(年)"] == "8"
    assert ind["自由现金流对分红覆盖率(倍)"] == "1.80"
    assert ind["财务健康度评分(0-100)"] == "82"


def test_load_dividend_data_extracts_risks_and_rating(tmp_path, monkeypatch, dividend_md):
    """从「六、风险因素」和「七、投资评级与理由」段提取。"""
    monkeypatch.chdir(dividend_md)
    data = load_dividend_data(dividend_md)

    assert "risk_factors" in data
    assert len(data["risk_factors"]) >= 1
    assert any("80%" in r or "分红" in r for r in data["risk_factors"])

    assert "investment_rating" in data
    assert data["investment_rating"] == "BUY"


# ──────────────────────────────────────────────────────────────────────────────
# build_markdown_report 整合 dividend section
# ──────────────────────────────────────────────────────────────────────────────

def test_build_markdown_report_embeds_dividend_section_when_available(
    tmp_path, monkeypatch, sample_trace_entries, dividend_md,
):
    """memory_dir 有 dividend md 时,主报告应在「基本面分析」和「综合投资建议」之间
    新增「红利股分析」section,包含趋势表 + 关键指标 + 评级 + 风险因素。
    """
    monkeypatch.chdir(dividend_md)
    results = extract_analysis_results(sample_trace_entries)
    md = build_markdown_report(results, memory_dir=dividend_md)

    # 1. dividend section 存在
    assert "## 四、红利股分析" in md, (
        "主报告应新增「红利股分析」section"
    )

    # 2. trend table 内容嵌入
    assert "营业收入(亿元)" in md
    assert "分红率(%)" in md
    assert "2022" in md

    # 3. 关键指标
    assert "80.00" in md or "80.0" in md  # 分红率
    assert "BUY" in md  # investment_rating(可能与 fundamental 的 BUY 重复,但至少存在)

    # 4. 位置正确:dividend section 在基本面分析之后、综合投资建议之前
    fundamental_pos = md.index("基本面分析")
    dividend_pos = md.index("红利股分析")
    summary_pos = md.index("综合投资建议")
    assert fundamental_pos < dividend_pos < summary_pos


def test_build_markdown_report_omits_dividend_when_no_data(
    tmp_path, monkeypatch, sample_trace_entries,
):
    """memory_dir 没有 dividend md → 主报告不含分红分析(向后兼容)。"""
    monkeypatch.chdir(tmp_path)
    results = extract_analysis_results(sample_trace_entries)
    md = build_markdown_report(results, memory_dir=tmp_path)

    assert "红利股分析" not in md
    # 原有 section 都还在
    assert "周期股分析" in md
    assert "基本面分析" in md
    assert "综合投资建议" in md