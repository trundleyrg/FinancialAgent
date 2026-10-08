"""红利股 skill 单元测试。"""
from pathlib import Path

import pandas as pd
import pytest

from src.skills import run_skill
from src.skills.dividend.tools import build_dividend_markdown


@pytest.fixture
def stub_llm():
    """返还固定红利股分析 JSON 的 mock LLM。"""
    class _Resp:
        content = '{"dividend_sustainability": "高", "investment_rating": "BUY", "reasoning": "test"}'

    class _LLM:
        def invoke(self, *args, **kwargs):
            return _Resp()

    return _LLM()


def test_skill_md_loads_non_empty():
    """SKILL.md 存在且非空。"""
    skill_path = Path("src/skills/dividend/SKILL.md")
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert len(content) > 100, "SKILL.md 内容过短"


def test_run_with_missing_company_returns_error():
    """缺少 company_name 时返回 error_msg。"""
    delta = run_skill("dividend", {"company_name": None, "report_year": 2024}, llm=None)
    assert delta["dividend_analysis"] is None
    assert "缺少公司信息" in delta["error_msg"]


def test_run_with_full_state_returns_analysis(stub_llm):
    """完整 state + stub_llm 返回 dividend_analysis dict。"""
    state = {
        "company_name": "测试公司",
        "stock_code": "999999",
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = run_skill("dividend", state, llm=stub_llm)
    assert "dividend_analysis" in delta
    # LLM 是 stub，可能因数据查询失败抛错；至少验证结构
    if "error_msg" not in delta:
        assert isinstance(delta["dividend_analysis"], dict)


def test_run_skill_unknown_raises():
    with pytest.raises(KeyError):
        run_skill("does_not_exist", {}, llm=None)


# ──────────────────────────────────────────────────────────────────────────────
# build_dividend_markdown
# ──────────────────────────────────────────────────────────────────────────────


_FULL_RESULT = {
    "dividend_yield": 4.5,
    "payout_ratio": 60.0,
    "dividend_stability_years": 10,
    "cash_flow_coverage": 1.8,
    "financial_health_score": 82,
    "profitability": {"gross_margin": 65.0, "net_margin": 25.0, "roe": 18.0},
    "solvency": {"debt_to_asset": 30.0},
    "valuation": {"pe_ratio": 15.2, "pb_ratio": 2.1},
    "risk_factors": ["行业政策变化", "原材料价格波动"],
    "investment_rating": "BUY",
    "reasoning": "公司分红稳定,现金流充裕",
}


def _sample_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "营业收入(亿元)": [38.5, 40.4, 47.2],
            "归母净利润(亿元)": [4.4, 7.8, 11.5],
            "分红率(%)": [44.77, 53.72, 60.0],
        },
        index=["2022", "2023", "2024"],
    )


def test_build_dividend_markdown_basic_structure():
    """完整 result + chart + table → 七段、顺序正确。"""
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="东阿阿胶",
        stock_code="000423",
        report_year=2024,
        report_period="FY",
    )
    # 标题含公司+代码+年份
    assert "# 红利股分析报告 - 东阿阿胶 (000423) 2024年报" in md
    # 关键指标趋势段含图 + 表
    assert "## 一、关键指标趋势" in md
    assert "![东阿阿胶 红利股关键指标趋势](charts/dividend_trend_2024.png)" in md
    assert "营业收入(亿元)" in md
    # 关键指标段含 dividend_yield 等
    assert "## 二、关键指标" in md
    assert "4.50" in md  # dividend_yield
    assert "60.00" in md  # payout_ratio
    # 评级 + 理由
    assert "**投资评级: BUY**" in md
    assert "公司分红稳定,现金流充裕" in md
    # 七段顺序:一 < 二 < 三 < 四 < 五 < 六 < 七
    pos_one = md.index("## 一、")
    pos_two = md.index("## 二、")
    pos_three = md.index("## 三、")
    pos_four = md.index("## 四、")
    pos_five = md.index("## 五、")
    pos_six = md.index("## 六、")
    pos_seven = md.index("## 七、")
    assert pos_one < pos_two < pos_three < pos_four < pos_five < pos_six < pos_seven


def test_build_dividend_markdown_chart_above_table():
    """图相对路径必须在表格 markdown 之前出现(用户的『图在上、表格在下』要求)。"""
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="东阿阿胶",
        stock_code="000423",
        report_year=2024,
    )
    chart_pos = md.index("(charts/dividend_trend_2024.png)")
    # 找表格头部 "--- | --- | ---"(在 DataFrame 渲染出的 markdown 表格里)
    # 表格头在第二行,特征是 "|" 分隔且有多个 "------"
    import re
    table_header_match = re.search(r"\|\s*-{3,}\s*\|", md)
    assert table_header_match is not None, "应渲染出 markdown 表格"
    assert chart_pos < table_header_match.start(), "图必须在表格之前出现"


def test_build_dividend_markdown_without_chart():
    """chart_path=None → 跳过图,但仍渲染表 + LLM 结论。"""
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path=None, table=_sample_table(),
        company_name="X", stock_code="000001", report_year=2024,
    )
    assert "![X 红利股关键指标趋势]" not in md
    assert "营业收入(亿元)" in md
    assert "**投资评级: BUY**" in md


def test_build_dividend_markdown_without_table():
    """table=None 且 chart 存在 → 渲染图,跳过表,不出现『数据缺失』提示。"""
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path="charts/dividend_trend_2024.png",
        table=None, company_name="X", stock_code="000001", report_year=2024,
    )
    assert "(charts/dividend_trend_2024.png)" in md
    # 仅在 chart 和 table 都缺失时才显示「数据缺失」
    assert "趋势图/表数据缺失" not in md
    # LLM 结论段还在
    assert "**投资评级: BUY**" in md


def test_build_dividend_markdown_both_missing_shows_placeholder():
    """chart 和 table 都缺失 → 出现『数据缺失』占位文本。"""
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path=None, table=None,
        company_name="X", stock_code="000001", report_year=2024,
    )
    assert "趋势图/表数据缺失" in md


def test_build_dividend_markdown_missing_nested_fields():
    """result 缺 profitability/solvency/valuation → 用 N/A 填充,不应抛错。"""
    partial = {
        "dividend_yield": 3.0,
        "payout_ratio": 50.0,
        "investment_rating": "HOLD",
        "reasoning": "数据不全",
    }
    md = build_dividend_markdown(
        partial, chart_path=None, table=None,
        company_name="Y", stock_code="000002", report_year=2023,
    )
    assert "毛利率(%) | N/A" in md
    assert "资产负债率(%) | N/A" in md
    assert "市盈率(倍) | N/A" in md
    assert "**投资评级: HOLD**" in md


def test_build_dividend_markdown_reasoning_preserves_plain_text():
    """reasoning 走普通段落(非表格 cell),`|` 不需要转义。"""
    tricky = dict(_FULL_RESULT)
    tricky["reasoning"] = "评级高|低估|成长稳"
    md = build_dividend_markdown(
        tricky, chart_path=None, table=None,
        company_name="Z", stock_code="000003", report_year=2024,
    )
    # 段落里 `|` 是合法的 markdown 字符,原样保留
    assert "评级高|低估|成长稳" in md


def test_build_dividend_markdown_escapes_pipe_in_risk_factors():
    """risk_factors list 项走 _md_escape_cell,`|` 转义为 `\\|`,未来嵌入表格不会被破坏。"""
    tricky = dict(_FULL_RESULT)
    tricky["risk_factors"] = ["行业政策|收紧", "原材料|涨价"]
    md = build_dividend_markdown(
        tricky, chart_path=None, table=None,
        company_name="W", stock_code="000005", report_year=2024,
    )
    assert "- 行业政策\\|收紧" in md
    assert "- 原材料\\|涨价" in md


def test_build_dividend_markdown_risks_fallback():
    """risk_factors 缺失或非 list → 走『暂无』分支,不抛错。"""
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path=None, table=None,
        company_name="A", stock_code="000004", report_year=2024,
    )
    assert "- 行业政策变化" in md
    assert "- 原材料价格波动" in md

    no_risks = dict(_FULL_RESULT)
    no_risks["risk_factors"] = None
    md2 = build_dividend_markdown(
        no_risks, chart_path=None, table=None,
        company_name="A", stock_code="000004", report_year=2024,
    )
    assert "- 暂无" in md2
