"""红利股 skill 单元测试。"""
from pathlib import Path

import pandas as pd
import pytest

from src.skills import run_skill
from src.skills.dividend.tools import (
    _round_half_up,
    build_dividend_markdown,
)


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


# ──────────────────────────────────────────────────────────────────────────────
# 数字四舍五入(ROUND_HALF_UP)与表格 cell 格式化
# ──────────────────────────────────────────────────────────────────────────────


def test_round_half_up_standard_rounding():
    """标准数学四舍五入:0.5 一律往上入,不是银行家舍入。"""
    # 银行家舍入会得到 0 / 2;四舍五入得到 1 / 2
    assert _round_half_up(0.5, 0) == 1
    assert _round_half_up(1.5, 0) == 2
    assert _round_half_up(2.5, 0) == 3
    assert _round_half_up(0.25, 1) == 0.3
    assert _round_half_up(0.125, 2) == 0.13
    # 常规情况
    assert _round_half_up(1.234, 2) == 1.23
    assert _round_half_up(1.235, 2) == 1.24
    assert _round_half_up(1.236, 2) == 1.24
    # 整数
    assert _round_half_up(10, 2) == 10
    # NaN / inf 保持原样
    assert _round_half_up(float("nan"), 2) != _round_half_up(float("nan"), 2)
    assert _round_half_up(float("inf"), 2) == float("inf")


def test_trend_table_values_rounded_to_two_decimals():
    """趋势表数字 cell 四舍五入到 2 位小数。"""
    table = pd.DataFrame(
        {
            "营业收入(亿元)": [38.51234, 40.455, 47.2],
            "归母净利润(亿元)": [4.4321, 7.855, 11.50001],
            "分红率(%)": [44.765, 53.725, 60.0],
        },
        index=["2022", "2023", "2024"],
    )
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path=None, table=table,
        company_name="X", stock_code="000001", report_year=2024,
    )
    # 全部按四舍五入保留 2 位
    assert "38.51" in md
    assert "40.46" in md   # 40.455 四舍五入到 40.46(标准)
    assert "47.20" in md
    assert "4.43" in md
    assert "7.86" in md   # 7.855 四舍五入到 7.86
    assert "11.50" in md  # 11.50001 四舍五入到 11.50
    assert "44.77" in md  # 44.765 标准四舍五入到 44.77
    assert "53.73" in md
    assert "60.00" in md


def test_trend_table_uses_bankers_rounding_correctly_differs():
    """对比:同样输入下标准四舍五入 vs 银行家舍入;确保实现用 ROUND_HALF_UP。

    f"{1.235:.2f}" 银行家舍入 → "1.23"(5 前面是奇数 3 往偶数 2 方向)
    ROUND_HALF_UP 一律往上 → "1.24"
    """
    table = pd.DataFrame(
        {"x(%)": [1.235, 2.345]},
        index=["2024", "2025"],
    )
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path=None, table=table,
        company_name="X", stock_code="000001", report_year=2024,
    )
    # 1.235 标准四舍五入 → 1.24(不是银行家的 1.23)
    assert "| 1.24 |" in md
    # 2.345 → 2.35(银行家舍入 5 前面是 4 偶数 → 2.34;标准四舍五入 → 2.35)
    assert "| 2.35 |" in md


def test_llm_result_metrics_rounded_to_two_decimals():
    """LLM 结论表(float 字段)也走四舍五入 2 位。"""
    tricky = {
        "dividend_yield": 4.555,        # → 4.56(标准)/ 4.56(银行家也入)
        "payout_ratio": 60.005,          # → 60.01
        "dividend_stability_years": 10,  # int,保持 10
        "cash_flow_coverage": 1.555,     # → 1.56
        "financial_health_score": 82,    # int
        "profitability": {
            "gross_margin": 65.555,      # → 65.56
            "net_margin": 25.0,          # → 25.00
            "roe": 18.004,               # → 18.00
        },
        "solvency": {"debt_to_asset": 30.0},
        "valuation": {"pe_ratio": 15.205, "pb_ratio": 2.1},
        "risk_factors": [],
        "investment_rating": "BUY",
        "reasoning": "ok",
    }
    md = build_dividend_markdown(
        tricky, chart_path=None, table=None,
        company_name="Y", stock_code="000002", report_year=2024,
    )
    assert "4.56" in md   # dividend_yield
    assert "60.01" in md  # payout_ratio
    assert "1.56" in md   # cash_flow_coverage
    assert "65.56" in md  # gross_margin
    assert "25.00" in md  # net_margin
    assert "18.00" in md  # roe
    assert "15.21" in md  # pe_ratio: 银行家 5 前面奇数 0 → 15.20;标准 5 往上 → 15.21
    assert "2.10" in md   # pb_ratio: 2.1 → 2.10
    # int 字段保持原样,不要变成 "10.00" / "82.00"
    assert "| 10 |" in md
    assert "| 82 |" in md


# ──────────────────────────────────────────────────────────────────────────────
# skill 集成:验证 dividend skill run() 成功后写独立 markdown 报告
# ──────────────────────────────────────────────────────────────────────────────


def test_skill_writes_dividend_markdown_report(tmp_path, monkeypatch):
    """端到端:mock 数据抓取 + LLM,跑通 run(),验证:
    1. markdown 文件被写入 data/{stock}/memory/
    2. 报告里图在上、表格在下
    3. input_context.markdown_path 被回填
    """
    import json
    from unittest.mock import MagicMock

    # 把 data/{stock}/memory 临时重定向到 tmp_path
    stock_code = "999999"
    company_name = "测试公司"

    monkeypatch.chdir(tmp_path)
    memory_dir = tmp_path / "data" / stock_code / "memory"
    memory_dir.mkdir(parents=True)

    # ── mock 数据抓取 ──
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_all_financial_data",
        lambda **kw: {
            "balance_sheet": {"total_assets": 1e10},
            "income_statement": {"net_profit": 1e8, "operating_revenue": 5e8},
            "cash_flow": {
                "net_cash_from_operations": 1.2e8,
                "cash_for_dividend_and_interest": 5e7,
            },
        },
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_multi_year_financial_data",
        lambda **kw: {
            "2022": {
                "consolidated_income_statement": {"operating_revenue": 4e8, "net_profit": 8e7},
                "consolidated_cash_flow_statement": {"net_cash_from_operations": 1e8, "cash_for_dividend_and_interest": 4e7},
                "consolidated_balance_sheet": {"total_assets": 9e9},
            },
            "2023": {
                "consolidated_income_statement": {"operating_revenue": 5e8, "net_profit": 1e8},
                "consolidated_cash_flow_statement": {"net_cash_from_operations": 1.2e8, "cash_for_dividend_and_interest": 5e7},
                "consolidated_balance_sheet": {"total_assets": 1e10},
            },
        },
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.calculate_profitability",
        lambda inc, bs: {"gross_margin": 60, "net_margin": 20, "roe": 15},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.calculate_liquidity",
        lambda bs: {"current_ratio": 2.0},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.calculate_solvency",
        lambda bs, inc: {"debt_to_asset": 30},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_stock_market_data",
        lambda code: {"pe_pb_history": []},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_dividend_stats_with_fallback",
        lambda code, years=5: {"avg_dividend_yield": 4.0},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.compute_dividend_stability_years",
        lambda *a, **k: 5,
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill._fetch_total_shares",
        lambda *a, **k: 1e9,
    )

    # ── mock LLM 链 ──
    llm_result = dict(_FULL_RESULT, investment_rating="BUY", reasoning="分红稳")
    captured_ctx: dict = {}

    def fake_save(name, state, result, input_context=None):
        captured_ctx.update(input_context or {})
        return True

    monkeypatch.setattr("src.skills.dividend.skill.save_skill_result", fake_save)

    fake_chain = MagicMock()
    fake_chain.invoke.return_value = llm_result
    # 链式语法 `prompt | llm | JsonOutputParser()` 会调 __or__,
    # MagicMock 默认不支持 → 用真类包一层。
    class _Chain:
        def __init__(self, inner):
            self._inner = inner
        def __or__(self, other):
            return self
        def invoke(self, x):
            return self._inner.invoke(x)

    monkeypatch.setattr(
        "src.skills.dividend.skill.ChatPromptTemplate.from_messages",
        lambda msgs: _Chain(fake_chain),
    )

    from src.skills import run_skill
    state = {
        "company_name": company_name,
        "stock_code": stock_code,
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = run_skill("dividend", state, llm=MagicMock())

    # 1. skill 没失败
    assert "error_msg" not in delta, f"skill 失败: {delta.get('error_msg')}"

    # 2. markdown 文件被写入
    md_path = captured_ctx.get("markdown_path")
    assert md_path is not None, "input_context.markdown_path 未回填"
    md_file = Path(md_path).resolve()
    assert md_file.exists(), f"markdown 文件不存在: {md_file}"
    assert md_file.parent.resolve() == memory_dir.resolve(), (
        f"markdown 目录不对: {md_file.parent} vs {memory_dir}"
    )

    # 3. 文件名格式
    assert md_file.name == f"分析报告_分红_{company_name}_{stock_code}_2024.md"

    # 4. 报告里图在上、表格在下
    content = md_file.read_text(encoding="utf-8")
    assert "(charts/dividend_trend_2024.png)" in content, "图相对路径应在 markdown 中"
    # 相对路径,不是绝对路径
    assert "/data/999999/memory/charts/" not in content, "应该是相对路径,不是绝对路径"

    chart_pos = content.find("(charts/dividend_trend_2024.png)")
    import re
    table_header = re.search(r"\|\s*-{3,}\s*\|", content)
    assert table_header is not None
    assert chart_pos < table_header.start(), "图必须在上、表格在下"

    # 5. LLM 结论段存在
    assert "**投资评级: BUY**" in content
    assert "分红稳" in content
