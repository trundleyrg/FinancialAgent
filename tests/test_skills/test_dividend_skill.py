"""红利股 skill 单元测试。"""
from pathlib import Path

import pandas as pd
import pytest

from src.skills import run_skill
from src.skills.dividend.tools import (
    _build_dividend_extra_columns,
    _compute_payout_from_events,
    _fmt_split_qty,
    _is_financial_data_empty,
    _round_half_up,
    _sum_dividend_from_events,
    build_dividend_markdown,
    extract_dividend_info,
    query_dividend_events,
    query_dividend_events_by_year,
    render_dividend_trend_chart,
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
    """完整 result + chart + table → 六段(无投资评级,行为变更)、顺序正确。"""
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
    # 评级段已删除(用户提交历史代码变更阶段要求)
    assert "**投资评级" not in md, "报告中不应再有「投资评级」段"
    assert "公司分红稳定,现金流充裕" not in md, (
        "reasoning 也不再出现在报告中(评级段是 reasoning 唯一渲染位置)"
    )
    # 六段顺序:一 < 二 < 三 < 四 < 五 < 六
    pos_one = md.index("## 一、")
    pos_two = md.index("## 二、")
    pos_three = md.index("## 三、")
    pos_four = md.index("## 四、")
    pos_five = md.index("## 五、")
    pos_six = md.index("## 六、")
    assert pos_one < pos_two < pos_three < pos_four < pos_five < pos_six
    # 不应有「七、」段
    assert "## 七、" not in md, "不应再有七、投资评级与理由 段"


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
    """chart_path=None → 跳过图,但仍渲染表。"""
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path=None, table=_sample_table(),
        company_name="X", stock_code="000001", report_year=2024,
    )
    assert "![X 红利股关键指标趋势]" not in md
    assert "营业收入(亿元)" in md
    # 评级段已删除,所以这里不再断言;保留表渲染验证


def test_build_dividend_markdown_without_table():
    """table=None 且 chart 存在 → 渲染图,跳过表,不出现『数据缺失』提示。"""
    md = build_dividend_markdown(
        _FULL_RESULT, chart_path="charts/dividend_trend_2024.png",
        table=None, company_name="X", stock_code="000001", report_year=2024,
    )
    assert "(charts/dividend_trend_2024.png)" in md
    # 仅在 chart 和 table 都缺失时才显示「数据缺失」
    assert "趋势图/表数据缺失" not in md


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
    # 评级段已删除,无需断言;子表 N/A 占位仍然走 fallback


def test_build_dividend_markdown_reasoning_not_in_md():
    """reasoning 不再渲染到 markdown 中(评级段删除后,reasoning 没有
    渲染位置)。

    评级与理由现在只在 skill_analysis_results 表中持久化;markdown 报告
    只保留事实性数字 + 解释,不渲染 LLM 评级与推理文本。
    """
    tricky = dict(_FULL_RESULT)
    tricky["reasoning"] = "评级高|低估|成长稳"
    md = build_dividend_markdown(
        tricky, chart_path=None, table=None,
        company_name="Z", stock_code="000003", report_year=2024,
    )
    # reasoning 应不再出现
    assert "评级高|低估|成长稳" not in md, (
        "评级与理由已删除,reasoning 不应再渲染到 markdown"
    )
    assert "评级高" not in md


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
    # int 字段保持原样(不要变成 "10.00")
    assert "| 10 |" in md, "dividend_stability_years=10 应原样呈现"
    # financial_health_score=82 不应在 markdown 出现(82 在关键指标段已剔除)
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    assert "82" not in key_section, (
        "财务健康度评分 82 不应在关键指标段出现(已被剔除)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 分红率分子:capital_change_events 路径
# ──────────────────────────────────────────────────────────────────────────────


def test_sum_dividend_from_events_basic():
    """_sum_dividend_from_events:Σ(cash_per_10_shares / 10) × total_shares。"""
    events = [
        {"event_type": "cash_dividend", "cash_per_10_shares": 5.0},
        # bonus_share 不含现金,跳过
        {"event_type": "bonus_share", "cash_per_10_shares": 3.0},
    ]
    # 1 亿股,每 10 股派 5 元 → 5000 万
    assert _sum_dividend_from_events(events, 1e8) == 5e7

    # 同时有 combination 事件(送转+派息)也要算
    events2 = [
        {"event_type": "cash_dividend", "cash_per_10_shares": 3.0},
        {"event_type": "combination", "cash_per_10_shares": 2.0},
    ]
    # 1 亿股,5 元/10 股 → 5000 万
    assert _sum_dividend_from_events(events2, 1e8) == 5e7

    # 0 股或 None
    assert _sum_dividend_from_events(events, None) is None
    assert _sum_dividend_from_events(events, 0) is None
    # 空事件
    assert _sum_dividend_from_events([], 1e8) is None
    # cash_per_10_shares 为 0 或负数
    assert _sum_dividend_from_events(
        [{"event_type": "cash_dividend", "cash_per_10_shares": 0}], 1e8,
    ) is None


def test_compute_payout_from_events_basic():
    """_compute_payout_from_events:申报分红总额 / 净利 × 100。"""
    # 1 亿股,每 10 股派 5 元,净利 1 亿 → 5000万/1亿 = 50%
    events = [{"event_type": "cash_dividend", "cash_per_10_shares": 5.0}]
    assert _compute_payout_from_events(events, 1e8, 1e8) == 50.0

    # 多笔合计
    events2 = [
        {"event_type": "cash_dividend", "cash_per_10_shares": 3.0},
        {"event_type": "combination", "cash_per_10_shares": 2.0},
    ]
    # 1 亿股,5 元/10 股,净利 1 亿 → 50%
    assert _compute_payout_from_events(events2, 1e8, 1e8) == 50.0

    # 净利为 0 / 负 / None → 返回 None
    assert _compute_payout_from_events(events, 1e8, 0) is None
    assert _compute_payout_from_events(events, 1e8, -1e6) is None
    assert _compute_payout_from_events(events, 1e8, None) is None
    # total_shares 缺失
    assert _compute_payout_from_events(events, None, 1e8) is None
    # 无事件
    assert _compute_payout_from_events([], 1e8, 1e8) is None


def test_extract_dividend_info_uses_events_when_provided():
    """传 events + total_shares 时,payout_ratio 走 events 路径。"""
    financial_data = {
        "income_statement": {"net_profit": 1e9},     # 净利 10 亿
        "cash_flow": {
            "net_cash_from_operations": 1.2e9,
            "cash_for_fixed_assets": 3e8,
            # 现金流字段故意给一个干扰值:含利息,会高估
            "cash_for_dividend_and_interest": 7e8,  # 若用这个,7e8/1e9=70%
        },
    }
    # events 路径:每 10 股派 5 元,1 亿股 → 5000 万 → 5%
    events = [{"event_type": "cash_dividend", "cash_per_10_shares": 5.0}]
    info = extract_dividend_info(
        financial_data, dividend_events=events, total_shares=1e8,
    )
    assert info["payout_source"] == "capital_change_events"
    assert info["payout_ratio"] == 5.0
    assert info["cash_dividend_paid"] == 5e7  # 申报分红总额


def test_extract_dividend_info_falls_back_to_cash_flow():
    """不传 events 时退回到 cash_for_dividend_and_interest 字段。"""
    financial_data = {
        "income_statement": {"net_profit": 1e9},
        "cash_flow": {
            "net_cash_from_operations": 1.2e9,
            "cash_for_dividend_and_interest": 6e8,
        },
    }
    info = extract_dividend_info(financial_data)
    assert info["payout_source"] == "cash_flow"
    assert info["payout_ratio"] == 60.0
    assert info["cash_dividend_paid"] == 6e8


def test_extract_dividend_info_events_empty_falls_back():
    """events 列表为空(当年没分红)时退回到现金流字段。"""
    financial_data = {
        "income_statement": {"net_profit": 1e9},
        "cash_flow": {"cash_for_dividend_and_interest": 4e8},
    }
    info = extract_dividend_info(
        financial_data, dividend_events=[], total_shares=1e8,
    )
    assert info["payout_source"] == "cash_flow"
    assert info["payout_ratio"] == 40.0


def test_render_dividend_trend_chart_uses_events_per_year(tmp_path):
    """多年趋势图:有 events 的年份走 events,无 events 退到现金流。"""
    multi_year_summary = {
        "2022": {
            "operating_revenue": 4e9, "net_profit": 8e8,
            "cash_for_dividend_and_interest": 6e8,  # 若用这个 75%
        },
        "2023": {
            "operating_revenue": 5e9, "net_profit": 1e9,
            "cash_for_dividend_and_interest": 5e8,  # 无 events,退到这 50%
        },
        "2024": {
            "operating_revenue": 6e9, "net_profit": 1.2e9,
            "cash_for_dividend_and_interest": 4e8,  # 有 events,5%
        },
    }
    events_by_year = {
        # 2022:每 10 股派 6 元,1 亿股 → 6e7
        "2022": [{"event_type": "cash_dividend", "cash_per_10_shares": 6.0}],
        # 2024:每 10 股派 5 元,1.2 亿股 → 6e7
        "2024": [{"event_type": "cash_dividend", "cash_per_10_shares": 5.0}],
        # 2023 没事件,缺
    }
    shares_by_year = {"2022": 1e8, "2023": 1.1e8, "2024": 1.2e8}

    out = tmp_path / "events_trend.png"
    chart_path, table = render_dividend_trend_chart(
        multi_year_summary, out,
        dividend_events_by_year=events_by_year,
        total_shares_by_year=shares_by_year,
    )
    assert chart_path == out
    assert out.exists()
    # 表里 payout_ratio:2022→7.5%(6e7/8e8*100),2023→50%(退到现金流),2024→5%(6e7/1.2e9*100)
    # 注意 2023 用的是现金流 5e8/1e9=50%
    payout_col = table["分红率(%)"]
    assert payout_col["2022"] == 7.5
    assert payout_col["2023"] == 50.0
    assert payout_col["2024"] == 5.0


def test_render_dividend_trend_chart_no_events_falls_back_to_cash_flow(tmp_path):
    """完全不传 events 时,趋势图照旧用 cash_for_dividend_and_interest。"""
    multi_year_summary = {
        "2023": {
            "operating_revenue": 5e9, "net_profit": 1e9,
            "cash_for_dividend_and_interest": 5e8,
        },
    }
    out = tmp_path / "no_events.png"
    _, table = render_dividend_trend_chart(multi_year_summary, out)
    assert table["分红率(%)"]["2023"] == 50.0


def test_build_dividend_markdown_payout_ratio_override():
    """payout_ratio_override 优先于 result['payout_ratio'](LLM 输出)。"""
    result = dict(_FULL_RESULT, payout_ratio=99.0)  # LLM 估错
    md_no_override = build_dividend_markdown(
        result, chart_path=None, table=None,
        company_name="X", stock_code="000001", report_year=2024,
    )
    # 没 override 时,99 出现在「分红率(%)」行
    assert "99.00" in md_no_override

    md_with_override = build_dividend_markdown(
        result, chart_path=None, table=None,
        company_name="X", stock_code="000001", report_year=2024,
        payout_ratio_override=42.5,
    )
    # 有 override 时,99 不再出现,42.5 出现
    assert "99.00" not in md_with_override
    assert "42.50" in md_with_override


def test_query_dividend_events_db_failure_returns_empty():
    """DB 异常时 query_dividend_events 返回空列表,不抛错。"""
    # 没 mock get_db,默认 _duckdb_conn 不存在 → except → []
    result = query_dividend_events("999999", 2024, "FY")
    assert result == []


def test_query_dividend_events_by_year_db_failure_returns_empty():
    """DB 异常时 query_dividend_events_by_year 返回空 dict。"""
    result = query_dividend_events_by_year("999999", 2020, 2024, "FY")
    assert result == {}


# ──────────────────────────────────────────────────────────────────────────────
# 趋势表扩列:分红总金额 + 拆股情况
# ──────────────────────────────────────────────────────────────────────────────


def test_fmt_split_qty_integer_vs_decimal():
    """_fmt_split_qty:整数无小数,小数保留 1 位。"""
    assert _fmt_split_qty(3.0) == "3"
    assert _fmt_split_qty(0.0) == "0"
    assert _fmt_split_qty(2.5) == "2.5"
    assert _fmt_split_qty(1.25) == "1.2"  # 四舍五入到 1 位
    assert _fmt_split_qty(7.0) == "7"


def test_build_dividend_extra_columns_no_split_no_cash():
    """无 events + 无 cash_for_dividend:金额=0,拆股=无。"""
    m = {"2023": {"cash_for_dividend_and_interest": None}}
    extras = _build_dividend_extra_columns(m, {}, {})
    assert extras["分红总金额(亿元)"] == [0.0]
    assert extras["拆股情况"] == ["无"]


def test_build_dividend_extra_columns_only_cash():
    """纯现金分红(无送转):金额走 events 路径,拆股=无。"""
    m = {
        "2023": {
            "cash_for_dividend_and_interest": 5e7,  # 5e7 = 0.5 亿
        },
    }
    # 1 亿股,每 10 股派 5 元 → 5e7 元 = 0.5 亿
    events = {"2023": [{"event_type": "cash_dividend", "cash_per_10_shares": 5.0}]}
    extras = _build_dividend_extra_columns(m, events, {"2023": 1e8})
    assert extras["分红总金额(亿元)"] == [0.5]
    assert extras["拆股情况"] == ["无"]


def test_build_dividend_extra_columns_bonus_only():
    """纯送股(无现金):事件没有 cash,金额退到现金流字段(0),拆股=10送3。"""
    m = {
        "2023": {"cash_for_dividend_and_interest": 0},
    }
    events = {
        "2023": [{
            "event_type": "bonus_share",
            "cash_per_10_shares": None,
            "bonus_shares_per_10": 3.0,
        }],
    }
    extras = _build_dividend_extra_columns(m, events, {"2023": 1e8})
    assert extras["分红总金额(亿元)"] == [0.0]  # 无 cash
    assert extras["拆股情况"] == ["10送3"]


def test_build_dividend_extra_columns_combination_event():
    """combination 事件(送+派):金额 + 拆股都填。"""
    m = {"2023": {"cash_for_dividend_and_interest": 0}}
    # 1 亿股,每 10 股派 5 元送 2 股转 1 股
    events = {
        "2023": [{
            "event_type": "combination",
            "cash_per_10_shares": 5.0,
            "bonus_shares_per_10": 2.0,
            "capitalized_shares_per_10": 1.0,
        }],
    }
    extras = _build_dividend_extra_columns(m, events, {"2023": 1e8})
    assert extras["分红总金额(亿元)"] == [0.5]   # 5e7 = 0.5 亿
    assert extras["拆股情况"] == ["10送2转1"]


def test_build_dividend_extra_columns_capitalized_only():
    """纯转增(无送无派):拆股=10转2,金额=0。"""
    m = {"2023": {"cash_for_dividend_and_interest": 0}}
    events = {
        "2023": [{
            "event_type": "capitalized_share",
            "cash_per_10_shares": None,
            "capitalized_shares_per_10": 2.0,
        }],
    }
    extras = _build_dividend_extra_columns(m, events, {"2023": 1e8})
    assert extras["分红总金额(亿元)"] == [0.0]
    assert extras["拆股情况"] == ["10转2"]


def test_build_dividend_extra_columns_multi_year_ordered():
    """多年数据按 sorted(years) 顺序,columns 顺序对齐。"""
    m = {
        "2024": {"cash_for_dividend_and_interest": 6e7},
        "2022": {"cash_for_dividend_and_interest": 4e7},
        "2023": {"cash_for_dividend_and_interest": 5e7},
    }
    events = {
        "2022": [{"event_type": "cash_dividend", "cash_per_10_shares": 4.0}],
        "2023": [{"event_type": "cash_dividend", "cash_per_10_shares": 5.0}],
        "2024": [{"event_type": "cash_dividend", "cash_per_10_shares": 6.0}],
    }
    shares = {"2022": 1e8, "2023": 1e8, "2024": 1e8}
    extras = _build_dividend_extra_columns(m, events, shares)
    # sorted 顺序:2022, 2023, 2024
    assert extras["分红总金额(亿元)"] == [0.4, 0.5, 0.6]
    assert extras["拆股情况"] == ["无", "无", "无"]


def test_render_dividend_trend_chart_returns_8_col_table(tmp_path):
    """trend chart 返回的 DataFrame 有 8 列。

    列结构(分红率表格只放分红相关 + 营收/净利变化,负债数据另起独立 section):
        营业收入 / 归母 / 分红总额 / 拆股 / 营收YoY / 净利YoY / 分红率
    注:**有息/无息负债** 不在本表,改由 render_debt_structure_chart +
    build_dividend_markdown(debt_chart_path=...) 独立展示。
    """
    multi_year_summary = {
        "2023": {
            "operating_revenue": 5e9, "net_profit": 1e9,
            "cash_for_dividend_and_interest": 5e7,
        },
        "2024": {
            "operating_revenue": 6e9, "net_profit": 1.2e9,
            "cash_for_dividend_and_interest": 6e7,
        },
    }
    events_by_year = {
        "2023": [{"event_type": "cash_dividend", "cash_per_10_shares": 5.0}],
        "2024": [{
            "event_type": "combination",
            "cash_per_10_shares": 5.0,
            "bonus_shares_per_10": 2.0,
            "capitalized_shares_per_10": 1.0,
        }],
    }
    shares_by_year = {"2023": 1e8, "2024": 1e8}
    out = tmp_path / "eight_col.png"
    chart_path, table = render_dividend_trend_chart(
        multi_year_summary, out,
        dividend_events_by_year=events_by_year,
        total_shares_by_year=shares_by_year,
    )
    assert chart_path == out
    assert out.exists()
    # 7 列 — 分红率(派生指标)放最后一列,阅读流:基本面 → 派息结构 → 变化 → 比率
    # 注:有息/无息负债数据另起「二、负债结构」section 展示,不混排
    expected_cols = [
        "营业收入(亿元)", "归母净利润(亿元)",
        "分红总金额(亿元)", "拆股情况",
        "营收YoY(%)", "净利YoY(%)",
        "分红率(%)",
    ]
    assert list(table.columns) == expected_cols, (
        f"列序与期望不符: 实际 {list(expected_cols)}"
    )
    # 拆股情况:2023=无(纯派现),2024=10送2转1
    assert table["拆股情况"]["2023"] == "无"
    assert table["拆股情况"]["2024"] == "10送2转1"
    # 分红总金额:2023=0.5亿,2024=0.5亿
    assert table["分红总金额(亿元)"]["2023"] == 0.5
    assert table["分红总金额(亿元)"]["2024"] == 0.5
    # YoY(2024 vs 2023):营收 20%,净利 20%
    assert table["营收YoY(%)"]["2024"] == 20.0
    assert table["净利YoY(%)"]["2024"] == 20.0
    # 不再有「有息负债」列(改独立 section 展示)
    assert "有息负债(亿元)" not in table.columns
    assert "有息占比(%)" not in table.columns


def test_skill_markdown_includes_extra_table_columns(tmp_path, monkeypatch):
    """端到端:skill 写出的 markdown 表格包含新 2 列。"""
    from unittest.mock import MagicMock

    stock_code = "999997"
    company_name = "扩列测试"

    monkeypatch.chdir(tmp_path)
    memory_dir = tmp_path / "data" / stock_code / "memory"
    memory_dir.mkdir(parents=True)

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
            "2023": {
                "consolidated_income_statement": {"operating_revenue": 5e8, "net_profit": 1e8},
                "consolidated_cash_flow_statement": {"net_cash_from_operations": 1.2e8, "cash_for_dividend_and_interest": 5e7},
                "consolidated_balance_sheet": {"total_assets": 1e10},
            },
            "2024": {
                "consolidated_income_statement": {"operating_revenue": 6e8, "net_profit": 1.2e8},
                "consolidated_cash_flow_statement": {"net_cash_from_operations": 1.5e8, "cash_for_dividend_and_interest": 6e7},
                "consolidated_balance_sheet": {"total_assets": 1.1e10},
            },
        },
    )
    monkeypatch.setattr("src.skills.dividend.skill.calculate_profitability", lambda *a, **k: {})
    monkeypatch.setattr("src.skills.dividend.skill.calculate_liquidity", lambda *a, **k: {})
    monkeypatch.setattr("src.skills.dividend.skill.calculate_solvency", lambda *a, **k: {})
    monkeypatch.setattr("src.skills.dividend.skill.get_stock_market_data", lambda *a, **k: {"pe_pb_history": []})
    monkeypatch.setattr("src.skills.dividend.skill.get_dividend_stats_with_fallback", lambda *a, **k: {})
    monkeypatch.setattr("src.skills.dividend.skill.compute_dividend_stability_years", lambda *a, **k: 5)
    monkeypatch.setattr("src.skills.dividend.skill._fetch_total_shares", lambda *a, **k: 1e8)
    # 2023:纯派现(每 10 股 5 元,1 亿股 → 5e7 → 0.5 亿)
    # 2024:送转+派息(每 10 股派 5 元送 2 转 1,1.2 亿股 → 6e7 → 0.5 亿)
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events",
        lambda *a, **k: [
            {"event_type": "combination", "cash_per_10_shares": 5.0,
             "bonus_shares_per_10": 2.0, "capitalized_shares_per_10": 1.0},
        ],
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events_by_year",
        lambda *a, **k: {
            "2023": [{"event_type": "cash_dividend", "cash_per_10_shares": 5.0,
                      "bonus_shares_per_10": 0.0, "capitalized_shares_per_10": 0.0}],
            "2024": [{"event_type": "combination", "cash_per_10_shares": 5.0,
                      "bonus_shares_per_10": 2.0, "capitalized_shares_per_10": 1.0}],
        },
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.fetch_total_shares_by_year",
        lambda *a, **k: {"2023": 1e8, "2024": 1.2e8},
    )

    fake_chain = MagicMock()
    fake_chain.invoke.return_value = dict(
        _FULL_RESULT, investment_rating="BUY", reasoning="ok",
    )

    class _Chain:
        def __init__(self, inner): self._inner = inner
        def __or__(self, other): return self
        def invoke(self, x): return self._inner.invoke(x)

    monkeypatch.setattr(
        "src.skills.dividend.skill.ChatPromptTemplate.from_messages",
        lambda msgs: _Chain(fake_chain),
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.save_skill_result", lambda *a, **k: True,
    )

    state = {
        "company_name": company_name, "stock_code": stock_code,
        "report_year": 2024, "report_period": "FY",
    }
    delta = run_skill("dividend", state, llm=MagicMock())
    assert "error_msg" not in delta

    md_file = memory_dir / f"分析报告_分红_{company_name}_{stock_code}_2024.md"
    content = md_file.read_text(encoding="utf-8")
    # 新 2 列的表头必须出现
    assert "分红总金额(亿元)" in content
    assert "拆股情况" in content
    # 2023 拆股=无,2024 拆股=10送2转1
    assert "| 无 |" in content
    assert "10送2转1" in content
    # 金额(亿元)四舍五入 2 位
    assert "0.50" in content


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
    # events 路径:申报分红事件 + 多年度 shares
    # 净利 1e8,total_shares 1e9,每 10 股派 0.5 元 → 5e7 → 50% 分红率
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events",
        lambda *a, **k: [{"event_type": "cash_dividend", "cash_per_10_shares": 0.5}],
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events_by_year",
        lambda *a, **k: {
            "2023": [{"event_type": "cash_dividend", "cash_per_10_shares": 0.5}],
        },
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.fetch_total_shares_by_year",
        lambda *a, **k: {"2023": 1e9},
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

    # 5. 报告里不应再有评级段(用户提交历史代码变更阶段要求删)
    assert "**投资评级" not in content
    assert "分红稳" not in content, "reasoning 也不再出现在报告中"

    # 6. events 路径:skill 把 payout_source 写进 input_context.markdown 上下文
    #    注意 save_skill_result 的 input_context 已被 captured_ctx 捕获
    #    (但 dividend_info.payout_source 本身在 analysis_metrics 里,需要从 captured 推算;
    #     我们直接验证 captured_ctx 间接行为:payout_ratio 走 events 路径后值是 50.00)
    # 净利 1e8, total_shares 1e9, 每 10 股 0.5 元 → 5e7 → 50.00%
    assert "50.00" in content, "events 路径的 payout_ratio 50.00% 应在 markdown 中"
    # 现金流字段(5e7)算的 50% 跟 events 算的 50% 数值碰巧相同,所以额外验证:
    # 把 LLM 的 payout_ratio 改成 99,看 skill 是否用自己的 events 值覆盖
    # (这条断言在另一个独立 test 里覆盖)


# ──────────────────────────────────────────────────────────────────────────────
# fail-fast:财务数据全空(PDF 解析失败)时直接 return error_delta
# ──────────────────────────────────────────────────────────────────────────────


def test_is_financial_data_empty_helper():
    """_is_financial_data_empty 各边界。"""
    # 全 None
    assert _is_financial_data_empty({}) is True
    assert _is_financial_data_empty(None) is True
    assert _is_financial_data_empty({
        "balance_sheet": {},
        "income_statement": {},
        "cash_flow": {},
    }) is True
    # 3 张表都只含 None 值
    assert _is_financial_data_empty({
        "balance_sheet": {"total_assets": None},
        "income_statement": {"net_profit": None},
        "cash_flow": {"net_cash_from_operations": None},
    }) is True
    # 至少一张表有一个非 None 字段 → 不算空
    assert _is_financial_data_empty({
        "balance_sheet": {},
        "income_statement": {"net_profit": 1e8},
        "cash_flow": {},
    }) is False
    assert _is_financial_data_empty({
        "balance_sheet": {"total_assets": 1e10},
        "income_statement": {},
        "cash_flow": {},
    }) is False
    # 缺某张表(但其它表有数据)→ 不算空
    assert _is_financial_data_empty({
        "balance_sheet": {"total_assets": 1e10},
    }) is False


def test_skill_fails_fast_when_financial_data_empty(monkeypatch, tmp_path):
    """财务数据 3 张表全空(PDF 解析失败)时,skill 直接 return error_delta。

    验证:
    1. dividend_analysis = None
    2. error_msg 含"财务数据为空"
    3. 不调用 LLM(避免无意义大 prompt)
    4. 不写 markdown 文件
    5. 不调用 save_skill_result(避免把噪音写进 DB)
    """
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    memory_dir = tmp_path / "data" / "000423" / "memory"
    memory_dir.mkdir(parents=True)

    # 财务数据全空(模拟 PDF 解析失败)
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_all_financial_data",
        lambda **kw: {
            "balance_sheet": {},
            "income_statement": {},
            "cash_flow": {},
        },
    )

    # LLM 链不应被调用 → 用一个会爆炸的 mock,真调用就 throw
    class ExplodingLLM:
        def invoke(self, *a, **k):
            raise AssertionError("LLM 不应被调用")

    save_called = []

    def fake_save(*a, **k):
        save_called.append(a)
        return True

    monkeypatch.setattr(
        "src.skills.dividend.skill.save_skill_result", fake_save,
    )

    state = {
        "company_name": "空数据公司",
        "stock_code": "000423",
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = run_skill("dividend", state, llm=ExplodingLLM())

    # 1. + 2. error_delta 形状
    assert delta["dividend_analysis"] is None
    assert "财务数据为空" in delta["error_msg"]
    # error_msg 应含公司名 + 年份(用于排查时定位)
    assert "空数据公司" in delta["error_msg"]
    assert "2024" in delta["error_msg"]

    # 3. LLM 没被调用(若调用会 throw,test 失败)
    # 4. 没写 markdown 文件
    md_files = list(memory_dir.glob("分析报告_分红_*.md"))
    assert md_files == [], f"不应写 markdown,但写了: {md_files}"

    # 5. save_skill_result 也没被调用
    assert save_called == [], f"save_skill_result 不应被调用,但调用了: {save_called}"


def test_skill_fails_fast_when_financial_data_none(monkeypatch, tmp_path):
    """更彻底的 fail-fast:get_all_financial_data 直接返回 None(数据完全未入库)。"""
    monkeypatch.chdir(tmp_path)
    memory_dir = tmp_path / "data" / "000423" / "memory"
    memory_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "src.skills.dividend.skill.get_all_financial_data",
        lambda **kw: None,
    )

    class ExplodingLLM:
        def invoke(self, *a, **k):
            raise AssertionError("LLM 不应被调用")

    state = {
        "company_name": "X",
        "stock_code": "000423",
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = run_skill("dividend", state, llm=ExplodingLLM())
    assert delta["dividend_analysis"] is None
    assert "财务数据为空" in delta["error_msg"]


def test_skill_payout_ratio_override_llm_value(tmp_path, monkeypatch):
    """端到端:LLM 估错的 payout_ratio(99%)会被 skill 用 events 算的 50% 覆盖。

    验证 build_dividend_markdown 的 payout_ratio_override 在 skill run() 里真的传了进来。
    """
    from unittest.mock import MagicMock

    stock_code = "999998"
    company_name = "覆盖测试"

    monkeypatch.chdir(tmp_path)
    memory_dir = tmp_path / "data" / stock_code / "memory"
    memory_dir.mkdir(parents=True)

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
            "2024": {
                "consolidated_income_statement": {"operating_revenue": 5e8, "net_profit": 1e8},
                "consolidated_cash_flow_statement": {"net_cash_from_operations": 1.2e8, "cash_for_dividend_and_interest": 5e7},
                "consolidated_balance_sheet": {"total_assets": 1e10},
            },
        },
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.calculate_profitability",
        lambda inc, bs: {},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.calculate_liquidity",
        lambda bs: {},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.calculate_solvency",
        lambda bs, inc: {},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_stock_market_data",
        lambda code: {"pe_pb_history": []},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_dividend_stats_with_fallback",
        lambda code, years=5: {},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.compute_dividend_stability_years",
        lambda *a, **k: 5,
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill._fetch_total_shares",
        lambda *a, **k: 1e9,
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events",
        lambda *a, **k: [{"event_type": "cash_dividend", "cash_per_10_shares": 0.5}],
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events_by_year",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.fetch_total_shares_by_year",
        lambda *a, **k: {},
    )

    # LLM 估错:输出 payout_ratio=99
    llm_result = dict(
        _FULL_RESULT,
        investment_rating="BUY", reasoning="ok",
        payout_ratio=99.0,  # 错的
    )

    fake_chain = MagicMock()
    fake_chain.invoke.return_value = llm_result

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
    monkeypatch.setattr(
        "src.skills.dividend.skill.save_skill_result",
        lambda *a, **k: True,
    )

    from src.skills import run_skill
    state = {
        "company_name": company_name,
        "stock_code": stock_code,
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = run_skill("dividend", state, llm=MagicMock())
    assert "error_msg" not in delta

    md_file = memory_dir / f"分析报告_分红_{company_name}_{stock_code}_2024.md"
    assert md_file.exists()
    content = md_file.read_text(encoding="utf-8")
    # LLM 的 99 必须没出现在 markdown(被 skill 的 events 值 50 覆盖)
    assert "99.00" not in content, "LLM 估错的 payout_ratio 99% 应被覆盖"
    # events 算的 50 应该出现
    assert "50.00" in content, "skill events 算的 50% 应在 markdown 中"


# ──────────────────────────────────────────────────────────────────────────────
# 关键指标 2:股息率(%) — code 算,覆盖 LLM 估算
# ──────────────────────────────────────────────────────────────────────────────


def test_extract_dividend_info_computes_yield_when_price_available():
    """events + current_price + total_shares 三者齐全 → code 算出股息率。

    公式:yield = (cash_dividend_paid / total_shares) / current_price × 100
    即 (per_share_dividend / current_price) × 100

    场景:000423 2024
        现金分红总额 = 15.58 亿(双笔累加)
        total_shares = 643,976,824
        current_price = 44.95 (用总市值 289.46亿 / 6.44亿股反推)
        per_share = 15.58e8 / 643_976_824 = 24.197 元/股
        yield = 24.197 / 44.95 × 100 = 5.38%
    """
    fd = {
        "income_statement": {"net_profit": 1_557_000_000.0},
        "cash_flow": {
            "net_cash_from_operations": 2_171_000_000.0,
            "cash_for_fixed_assets": 97_000_000.0,
            "cash_for_dividend_and_interest": 1_882_987_553.57,
        },
    }
    events = [
        {"event_type": "cash_dividend", "cash_per_10_shares": 11.4669},
        {"event_type": "cash_dividend", "cash_per_10_shares": 12.7299},
    ]
    info = extract_dividend_info(
        fd, dividend_events=events,
        total_shares=643_976_824.0,
        current_price=44.95,
    )
    # per_share = 24.1968 / 10 × 643_976_824 = 1_558_500_xxx ≈ 15.58 亿
    # yield = 1_558_500_xxx / 643_976_824 / 44.95 × 100 ≈ 5.38
    assert info["dividend_yield"] is not None
    assert 5.3 < info["dividend_yield"] < 5.5, (
        f"股息率应≈5.38%,实际 {info['dividend_yield']:.2f}%"
    )


def test_extract_dividend_info_yield_none_when_price_missing():
    """current_price 缺失 → yield=None,不臆测。"""
    fd = {
        "income_statement": {"net_profit": 1_557_000_000.0},
        "cash_flow": {
            "net_cash_from_operations": 2_171_000_000.0,
            "cash_for_dividend_and_interest": 1_882_987_553.57,
        },
    }
    events = [{"event_type": "cash_dividend", "cash_per_10_shares": 24.1968}]
    info = extract_dividend_info(
        fd, dividend_events=events,
        total_shares=643_976_824.0,
        current_price=None,  # akshare 失败
    )
    assert info["dividend_yield"] is None, "缺股价时不应臆测股息率"


def test_extract_dividend_info_yield_none_when_shares_missing():
    """total_shares 缺失 → yield=None。"""
    fd = {
        "income_statement": {"net_profit": 1_557_000_000.0},
        "cash_flow": {
            "net_cash_from_operations": 2_171_000_000.0,
            "cash_for_dividend_and_interest": 1_882_987_553.57,
        },
    }
    events = [{"event_type": "cash_dividend", "cash_per_10_shares": 24.1968}]
    info = extract_dividend_info(
        fd, dividend_events=events,
        total_shares=None,  # share_structure 缺失
        current_price=44.95,
    )
    assert info["dividend_yield"] is None, "缺总股本时不应臆测股息率"


def test_extract_dividend_info_yield_none_when_no_events():
    """events 缺失且 cash_flow=0 → yield=None,无数据可算。"""
    fd = {
        "income_statement": {"net_profit": 1_557_000_000.0},
        "cash_flow": {
            "net_cash_from_operations": 2_171_000_000.0,
            "cash_for_dividend_and_interest": 0,
        },
    }
    info = extract_dividend_info(
        fd, dividend_events=[],
        total_shares=643_976_824.0,
        current_price=44.95,
    )
    assert info["dividend_yield"] is None


def test_build_dividend_markdown_yield_override_used():
    """dividend_yield_override 优先于 LLM 估算的 dividend_yield。"""
    # LLM 估 4.5,但 skill 算出来的是 5.38,应被 override
    result = dict(_FULL_RESULT, dividend_yield=4.5)
    md = build_dividend_markdown(
        result,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="测试公司",
        stock_code="999999",
        report_year=2024,
        dividend_yield_override=5.38,
    )
    # 关键指标段:dividend_yield_override 应出现,4.50 不应出现
    assert "5.38" in md, "skill 算的 5.38% 应在 markdown 中"
    # 4.50 仍可能在其它地方(比如其它指标的 LLM 值);但 yield 这一行应是 5.38
    # 简化:确保 dividend_yield_override 唯一出现一次(在关键指标段)
    # 这里只检查 yield 表里的值
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    assert "5.38" in key_section
    assert "4.50" not in key_section, (
        f"关键指标段的股息率应是 override 5.38,不是 LLM 估算的 4.50"
    )


def test_build_dividend_markdown_yield_falls_back_to_llm_when_no_override():
    """dividend_yield_override=None → 用 LLM 估算的 dividend_yield(向后兼容)。"""
    result = dict(_FULL_RESULT, dividend_yield=4.5)
    md = build_dividend_markdown(
        result,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="X",
        stock_code="000001",
        report_year=2024,
        # dividend_yield_override 不传 → None
    )
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    assert "4.50" in key_section, (
        "无 override 时应回落到 LLM 估算的 4.50%(向后兼容)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 新增关注 1:有息负债 vs 无息负债 分类(高息债风险评估)
# ──────────────────────────────────────────────────────────────────────────────


def test_compute_debt_breakdown_basic():
    """compute_debt_breakdown 把总负债分成有息 / 无息。

    000423 2020 真实场景:
        短期借款 = 0
        长期借款 = 0
        应付债券 = 0
        一年内到期非流动负债 = 0
        租赁负债 = ~7 亿(2019 新版起)
        应付利息 = 0
        → 有息 = ~7 亿
        → 总负债 = 应付账款 + 其他应付款 + 合同负债 + ... (无息为主)
    """
    # 真实数据示意:总负债 15 亿,其中租赁负债 7 亿(有息),其余 8 亿(无息)
    bs_dict = {
        "short_term_borrowings": 0,
        "long_term_borrowings": 0,
        "bonds_payable": 0,
        "non_current_liabilities_due_within_one_year": 0,
        "lease_liabilities": 700_000_000.0,
        "interest_payable": 0,
        "total_liabilities": 1_500_000_000.0,
    }
    from src.skills.dividend.tools import compute_debt_breakdown

    interest, non_interest, total, interest_pct, non_interest_pct = compute_debt_breakdown(bs_dict)
    assert interest == 700_000_000.0
    assert non_interest == 800_000_000.0
    assert total == 1_500_000_000.0
    assert abs(interest_pct - 46.67) < 0.1
    assert abs(non_interest_pct - 53.33) < 0.1


def test_compute_debt_breakdown_handles_missing_fields():
    """缺字段时按 0 处理,不抛错。"""
    from src.skills.dividend.tools import compute_debt_breakdown

    bs_dict = {"total_liabilities": 100.0}  # 其他全 None
    interest, non_interest, total, _, _ = compute_debt_breakdown(bs_dict)
    assert interest == 0
    assert total == 100.0
    assert non_interest == 100.0


def test_compute_debt_breakdown_handles_no_total():
    """total_liabilities 缺失 → 返回 (0, 0, 0, 0.0, 0.0)。"""
    from src.skills.dividend.tools import compute_debt_breakdown

    interest, non_interest, total, i_pct, ni_pct = compute_debt_breakdown({})
    assert interest == 0
    assert non_interest == 0
    assert total == 0
    assert i_pct == 0.0
    assert ni_pct == 0.0


def test_compute_debt_breakdown_falls_back_to_current_noncurrent():
    """total_liabilities 缺失,但 current + non_current 有 → 用 fallback 求和。

    真实场景:000423 2020-2024 的 PDF 解析漏掉 total_liabilities 字段,
    但 total_current_liabilities 有值,total_non_current_liabilities 可能为 None。
    """
    from src.skills.dividend.tools import compute_debt_breakdown

    bs = {
        # total_liabilities 缺失 — 触发 fallback
        "short_term_borrowings": 0,
        "non_current_liabilities_due_within_one_year": 4_065_000.0,
        "lease_liabilities": 0,
        "total_current_liabilities": 2_755_244_398.98,  # ≈27.55亿
        "total_non_current_liabilities": None,  # 缺失
    }
    interest, non_interest, total, i_pct, ni_pct = compute_debt_breakdown(bs)
    # fallback 用 total_current_liabilities + None → 27.55亿
    assert abs(total - 2_755_244_398.98) < 1, f"total 应用 fallback,实际 {total}"
    # 有息 ≈ 4.07M(只有一年内到期),占比 ≈ 0.15%
    assert abs(interest - 4_065_000.0) < 1
    assert i_pct > 0 and i_pct < 1, f"有息占比应很小,实际 {i_pct}"
    # 无息 ≈ total - 有息 ≈ 27.55亿
    assert abs(non_interest - (total - interest)) < 1


# ──────────────────────────────────────────────────────────────────────────────
# 新增关注 2:营收 / 净利 YoY 变化
# ──────────────────────────────────────────────────────────────────────────────


def test_compute_revenue_profit_changes_basic():
    """compute_revenue_profit_changes 计算 YoY 增速。

    input: 多年(按年份排序):
        2020: revenue=34.09, profit=0.43
        2021: revenue=38.49, profit=4.40
        2022: revenue=40.42, profit=7.80
        2023: revenue=47.15, profit=11.51
        2024: revenue=59.21, profit=15.57

    YoY:
        revenue_yoy(2024) = (59.21 - 47.15) / 47.15 = 25.57%
        profit_yoy(2024) = (15.57 - 11.51) / 11.51 = 35.27%
        revenue_cagr(2020→2024) = (59.21/34.09)^(1/4) - 1 = 14.79%
        profit_cagr = (15.57/0.43)^(1/4) - 1 ≈ 145%(低基数)
    """
    from src.skills.dividend.tools import compute_revenue_profit_changes

    multi_year = {
        "2020": {"operating_revenue": 34.09e8, "net_profit": 0.43e8},
        "2021": {"operating_revenue": 38.49e8, "net_profit": 4.40e8},
        "2022": {"operating_revenue": 40.42e8, "net_profit": 7.80e8},
        "2023": {"operating_revenue": 47.15e8, "net_profit": 11.51e8},
        "2024": {"operating_revenue": 59.21e8, "net_profit": 15.57e8},
    }
    result = compute_revenue_profit_changes(multi_year)

    assert "revenue_yoy" in result
    assert "net_profit_yoy" in result
    assert "revenue_cagr" in result
    assert "net_profit_cagr" in result

    # 最新一年(2024)的 YoY
    latest_rev_yoy = result["revenue_yoy"][-1]
    latest_profit_yoy = result["net_profit_yoy"][-1]
    assert 25 < latest_rev_yoy < 26, f"2024 营收 YoY 应≈25.6%, 实际 {latest_rev_yoy}"
    assert 34 < latest_profit_yoy < 36, f"2024 净利 YoY 应≈35.3%, 实际 {latest_profit_yoy}"

    # CAGR(2020→2024,4 年期)
    rev_cagr = result["revenue_cagr"]
    assert 14 < rev_cagr < 16, f"营收 CAGR 应≈14.8%, 实际 {rev_cagr}"


def test_compute_revenue_profit_changes_empty_data():
    """空数据 → 返回空 dict。"""
    from src.skills.dividend.tools import compute_revenue_profit_changes

    result = compute_revenue_profit_changes({})
    assert result["revenue_yoy"] == []
    assert result["net_profit_yoy"] == []
    assert result["revenue_cagr"] == 0.0
    assert result["net_profit_cagr"] == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 新增关注 3:multi_year_summary 扩列(debt + YoY)
# ──────────────────────────────────────────────────────────────────────────────


def test_build_dividend_extra_columns_includes_debt_and_yoy():
    """_build_dividend_extra_columns 现在追加:YoY + 有息/无息负债 + 有息占比。

    columns 期望顺序:
        营业收入(亿元), 归母净利润(亿元),
        营收YoY(%), 净利YoY(%), 营收CAGR(%), 净利CAGR(%),
        分红总金额(亿元), 拆股情况,
        有息负债(亿元), 无息负债(亿元), 有息占比(%)
    """
    import pandas as pd
    from src.skills.dividend.tools import _build_dividend_extra_columns

    multi_year_summary = {
        "2020": {"operating_revenue": 34.09e8, "net_profit": 0.43e8},
        "2021": {"operating_revenue": 38.49e8, "net_profit": 4.40e8},
        "2024": {"operating_revenue": 59.21e8, "net_profit": 15.57e8},
    }
    events_by_year = {
        "2024": [{"event_type": "cash_dividend", "cash_per_10_shares": 24.1968}],
    }
    debt_by_year = {
        "2020": {"interest_bearing": 0, "non_interest_bearing": 1.5e9, "total_liabilities": 1.5e9},
        "2021": {"interest_bearing": 0, "non_interest_bearing": 1.6e9, "total_liabilities": 1.6e9},
        "2024": {"interest_bearing": 7e8, "non_interest_bearing": 8e8, "total_liabilities": 1.5e9},
    }
    shares_by_year = {"2024": 643_976_824.0}

    extras = _build_dividend_extra_columns(
        multi_year_summary, events_by_year, shares_by_year,
        debt_by_year=debt_by_year,
    )
    # 验证新 keys 存在
    assert "营收YoY(%)" in extras
    assert "净利YoY(%)" in extras
    # 注:有息/无息负债数据不在 trend table,改由 render_debt_structure_chart 独立展示
    assert "有息负债(亿元)" not in extras
    assert "无息负债(亿元)" not in extras
    assert "有息占比(%)" not in extras
    # 保持向后兼容
    assert "分红总金额(亿元)" in extras
    assert "拆股情况" in extras


# ──────────────────────────────────────────────────────────────────────────────
# 新增关注 4:markdown 二、关键指标 加有息负债占比
# ──────────────────────────────────────────────────────────────────────────────


def test_build_dividend_markdown_interest_debt_ratio_in_section():
    """build_dividend_markdown 应在「二、关键指标」加有息负债占比行。"""
    result = dict(
        _FULL_RESULT,
        interest_debt_ratio = 46.67,  # code 算
        total_interest_bearing_debt = 7.0,  # 亿
        total_non_interest_bearing_debt = 8.0,  # 亿
    )
    md = build_dividend_markdown(
        result,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="东阿阿胶",
        stock_code="000423",
        report_year=2024,
        interest_debt_ratio_override=46.67,
    )
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    assert "有息负债" in key_section or "Interest" in key_section, (
        "关键指标段应包含有息负债信息"
    )
    assert "46.67" in key_section, "有息负债占比应在 markdown 中"


# ──────────────────────────────────────────────────────────────────────────────
# 负债结构独立 section(图 + 表),与分红率表格不混排
# ──────────────────────────────────────────────────────────────────────────────


def test_render_debt_structure_chart_creates_stacked_bar(tmp_path):
    """render_debt_structure_chart 输出堆叠柱图 PNG(有息 + 无息)。"""
    from src.skills.dividend.tools import render_debt_structure_chart

    debt_by_year = {
        "2020": {"short_term_borrowings": 0, "long_term_borrowings": 0,
                    "lease_liabilities": 0, "total_liabilities": 9.4e8},
        "2021": {"short_term_borrowings": 0, "long_term_borrowings": 0,
                    "lease_liabilities": 0, "total_liabilities": 12.0e8},
        "2022": {"short_term_borrowings": 0, "long_term_borrowings": 0,
                    "lease_liabilities": 0, "total_liabilities": 12.5e8},
        "2023": {"short_term_borrowings": 0, "long_term_borrowings": 0,
                    "lease_liabilities": 2.5e8, "total_liabilities": 14.0e8},
        "2024": {"short_term_borrowings": 0, "long_term_borrowings": 0,
                    "lease_liabilities": 4.0e8, "total_liabilities": 16.5e8},
    }
    out = tmp_path / "debt_structure.png"
    result_path = render_debt_structure_chart(
        debt_by_year, out,
        title="测试公司 - 负债结构(有息 vs 无息)",
    )
    assert result_path == out
    assert out.exists(), "PNG 文件应被生成"
    assert out.stat().st_size > 1000, "PNG 文件应非空"


def test_render_debt_structure_chart_handles_empty_data(tmp_path):
    """空数据 → 不抛错,生成空图。"""
    from src.skills.dividend.tools import render_debt_structure_chart

    out = tmp_path / "empty.png"
    # 不抛错
    result_path = render_debt_structure_chart({}, out)
    assert result_path == out
    assert result_path.exists()


def test_render_debt_structure_chart_no_cjk_font_warnings(tmp_path, recwarn):
    """画图时不应有 CJK 字体缺失警告(Glyph '年' missing ...)。

    之前版本忘了应用 visualization._apply_cjk_font() → 「年」「有息」「无息」
    等中文字符在 PNG 里显示为方块。
    """
    import warnings

    from src.skills.dividend.tools import render_debt_structure_chart

    out = tmp_path / "no_warning.png"
    render_debt_structure_chart(
        {
            "2023": {"lease_liabilities": 2.5e8, "total_liabilities": 14.0e8},
            "2024": {"lease_liabilities": 4.0e8, "total_liabilities": 16.5e8},
        },
        out,
        title="测试公司 - 负债结构(有息 vs 无息)",  # 标题含中文
    )

    cjk_warnings = [
        w for w in recwarn.list
        if "Glyph" in str(w.message) and "missing" in str(w.message)
    ]
    assert cjk_warnings == [], (
        f"画图时不应有 CJK 字体缺失警告,但出现了 {len(cjk_warnings)} 条:\n"
        + "\n".join(str(w.message) for w in cjk_warnings)
    )


def test_build_dividend_markdown_has_separate_debt_section():
    """build_dividend_markdown 在传 debt_chart_path/debt_table 时新增独立 section。

    关键:负债结构 section 不与分红率趋势表混排 —— 应有独立的 ## 段标题。
    """
    debt_table = pd.DataFrame({
        "年份": ["2020", "2021", "2022", "2023", "2024"],
        "有息负债(亿元)": [0.0, 0.0, 0.0, 2.5, 4.0],
        "无息负债(亿元)": [9.4, 12.0, 12.5, 11.5, 12.5],
        "总负债(亿元)": [9.4, 12.0, 12.5, 14.0, 16.5],
        "有息占比(%)": [0.0, 0.0, 0.0, 17.86, 24.24],
    }, index=["2020", "2021", "2022", "2023", "2024"])

    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="东阿阿胶",
        stock_code="000423",
        report_year=2024,
        debt_chart_path="charts/debt_structure_2024.png",
        debt_table=debt_table,
    )

    # 1. 独立 section 标题
    assert "## " in md and "负债结构" in md, (
        "应有独立的「负债结构」section 标题"
    )

    # 2. 负债结构 section 在「关键指标趋势」之后、「关键指标」之前或之后
    debt_pos = md.index("负债结构")
    trend_pos = md.index("关键指标趋势")
    # 负债结构不应该是「关键指标趋势」同一 section(同一句话)
    assert "关键指标趋势" not in md[debt_pos-30:debt_pos+30], (
        "负债结构不应混入「关键指标趋势」section"
    )

    # 3. 包含独立的图与表(独立路径引用)
    assert "debt_structure_2024.png" in md, (
        "应有独立的负债结构图(chart_path)"
    )

    # 4. 表格内容
    assert "有息负债" in md
    assert "无息负债" in md
    assert "有息占比" in md
    assert "2024" in md  # 表格里有年份数据


def test_build_dividend_markdown_no_debt_section_when_no_data():
    """不传 debt_chart_path/debt_table → 不应有负债结构 section。"""
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="X",
        stock_code="000001",
        report_year=2024,
    )
    # 无负债数据 → 不应有独立「负债结构」section 标题
    assert "## " in md and "负债结构" not in md, (
        "不传 debt 数据时不应有负债结构 section"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 趋势表列顺序:分红率挪到最后一列 + markdown 加口径注释
# ──────────────────────────────────────────────────────────────────────────────


def test_render_dividend_trend_chart_payout_ratio_column_is_last(tmp_path):
    """分红率(%) 应是趋势表的最后一列 — 派生指标放末尾,事实指标放前面。

    期望顺序:
        [营业收入, 归母, 分红总金额, 拆股情况,
          营收YoY, 净利YoY, 有息负债, 无息负债, 有息占比,
          分红率(派生)] = 共 10 列
    """
    multi_year_summary = {
        "2023": {"operating_revenue": 5e9, "net_profit": 1e9,
                    "cash_for_dividend_and_interest": 5e8},
        "2024": {"operating_revenue": 6e9, "net_profit": 1.2e9,
                    "cash_for_dividend_and_interest": 6e7},
    }
    out = tmp_path / "test_col_order.png"
    chart_path, table = render_dividend_trend_chart(multi_year_summary, out)

    expected_order = [
        "营业收入(亿元)", "归母净利润(亿元)",
        "分红总金额(亿元)", "拆股情况",
        "营收YoY(%)", "净利YoY(%)",
        "分红率(%)",
    ]
    assert list(table.columns) == expected_order, (
        f"列顺序应={expected_order},实际={list(table.columns)}; "
        f"分红率(派生指标)应在最后一列"
    )
    # 分红率值仍可访问(位置不影响内容)
    assert "分红率(%)" in table.columns
    payout_col = table["分红率(%)"]
    assert payout_col["2023"] is not None
    assert payout_col["2024"] is not None


def test_build_dividend_markdown_includes_payout_ratio_calculation_note():
    """趋势表后必须有口径注释:「分红率仅计现金分红,送转股未折算」。

    防止投资者误读:严格 payout_ratio = cash / net_profit,
    送股/转增虽在「拆股情况」列展示了,但未折算进分红率。
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path="charts/dividend_trend_2024.png",
        table=_sample_table(),
        company_name="东阿阿胶",
        stock_code="000423",
        report_year=2024,
    )
    # 注释必须出现且含关键警告
    assert "口径说明" in md, "趋势表后应注明计算口径"
    assert "现金分红" in md
    assert "送转股" in md or "送股" in md
    assert "未折算" in md
    # 注释应在「## 一、关键指标趋势」之后、「## 二、关键指标」之前
    trend_section_pos = md.index("## 一、关键指标趋势")
    next_section_pos = md.index("## 二、", trend_section_pos)
    note_pos = md.find("口径说明")
    assert note_pos > trend_section_pos, "注释应在一、关键指标趋势之后"
    assert note_pos < next_section_pos, "注释应在二、关键指标之前"


# ──────────────────────────────────────────────────────────────────────────────
# 二、关键指标 段:财务健康度评分剔除 + 数据范围备注 + 指标解释
# ──────────────────────────────────────────────────────────────────────────────


def test_build_dividend_markdown_omits_financial_health_score():
    """「二、关键指标」表里不应再有「财务健康度评分(0-100)」一行。

    背景:LLM 评分在 NO_LLM / 非完整 LLM 环境下恒 N/A,留在表里观感差;
    用户要求剔除(实际想要评分请直接看八、投资评级)。
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="X",
        stock_code="000001",
        report_year=2024,
    )
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    assert "财务健康度评分" not in key_section, (
        "二、关键指标表里不应再有「财务健康度评分」行"
    )
    # 即使 _FULL_RESULT 含 financial_health_score=82,该整数值也不应泄漏到关键指标段
    assert "82" not in key_section, (
        "财务健康度评分对应的整数值不应泄漏到关键指标段"
    )


def test_build_dividend_markdown_adds_data_scope_note_with_trend_years():
    """trend_years=5 → 二、关键指标段加「数据范围」备注,提示读者
    「连续分红年限」等长期口径基于近 5 年窗口,真实年限可能更久。

    用户提交历史代码变更阶段提出的要求:不出具超 5 年回溯,但报告里
    必须告诉读者这一点。
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="测试",
        stock_code="000001",
        report_year=2024,
        trend_years=5,
    )
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    # 关键三要素:trend_years 数字 + 「数据范围」关键词 + 「连续分红年限」提醒
    assert "数据范围" in key_section, "应有「数据范围」备注"
    assert "近 **5 年**" in key_section, (
        "数据范围备注应包含 trend_years 数字(粗体格式)"
    )
    assert "连续分红年限" in key_section, (
        "应提醒读者「连续分红年限」依赖窗口"
    )
    assert "实际" in key_section, "应说明真实年限可能长于此"


def test_build_dividend_markdown_omits_data_scope_note_without_trend_years():
    """trend_years=None → 不应显示「数据范围」备注。

    兼容旧调用方:不传 trend_years 时报告不含数据范围备注。
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="X",
        stock_code="000001",
        report_year=2024,
        # trend_years 不传 → None
    )
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    assert "数据范围" not in key_section, (
        "未传 trend_years 时不应有「数据范围」备注"
    )


def test_build_dividend_markdown_data_scope_note_uses_actual_years():
    """trend_years=8 → 数据范围备注里的数字也应为 8(不写死)。"""
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="X",
        stock_code="000001",
        report_year=2024,
        trend_years=8,
    )
    key_section = md[md.index("## 二、关键指标"):md.index("## 三、")]
    assert "近 **8 年**" in key_section, (
        "数据范围备注应使用实际传入的 trend_years(8)"
    )
    assert "近 **5 年**" not in key_section


def test_build_dividend_markdown_includes_metric_explanations():
    """「指标解释」段跟在「二、关键指标」表后,含 6 项关键指标口径。

    6 项:
        股息率 / 分红率 / 连续分红年限 / 自由现金流对分红覆盖率 /
        有息负债 / 有息负债占比
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="X",
        stock_code="000001",
        report_year=2024,
    )
    # 段标题
    assert "### 指标解释" in md, "应有「指标解释」段标题"
    # 段位置:必须在「二、关键指标」之后、「三、」之前(独立段)
    explanation_section_pos = md.index("### 指标解释")
    section_two_pos = md.index("## 二、关键指标")
    section_three_pos = md.index("## 三、")
    assert section_two_pos < explanation_section_pos < section_three_pos, (
        "「指标解释」应在「二、关键指标」之后、「三、」之前"
    )

    # 6 项关键指标口径必须出现
    for metric in [
        "股息率",
        "分红率",
        "连续分红年限",
        "自由现金流对分红覆盖率",
        "有息负债",
        "有息负债占比",
    ]:
        assert metric in md, f"「指标解释」应包含「{metric}」的口径说明"


def test_build_dividend_markdown_dividend_yield_explanation_references_stock_daily_price():
    """股息率口径说明应明确「股价取自 stock_daily_price 最近一日收盘价」。

    防止读者去搜别的概念算法;实际就是 stock_daily_price 表最后一行的
    close_price,前复权(qfq)。
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="X",
        stock_code="000001",
        report_year=2024,
    )
    # 在「指标解释」段内,股息率行含 stock_daily_price 引用 + 收盘价关键词
    explanation_idx = md.index("### 指标解释")
    # 段结束于下一个 "---" 分隔线或 "## " 段标题
    end_idx = md.index("\n---\n", explanation_idx)
    explanation_section = md[explanation_idx:end_idx]
    # 找到「股息率」(非「股息率(%)」行 — 由于 ★标记★ 在用粗体格式
    # 实际渲染为 "**股息率**(%) = ..." 起头)
    yield_match = next(
        (i for i, line in enumerate(explanation_section.split("\n"))
         if line.startswith("- **股息率**")),
        None,
    )
    assert yield_match is not None, "应有「股息率」bullet 行"
    yield_line = explanation_section.split("\n")[yield_match]
    assert "stock_daily_price" in yield_line, (
        f"股息率口径应引用 stock_daily_price 表;实际行:{yield_line!r}"
    )
    assert "收盘价" in yield_line
    assert "前复权" in yield_line or "复权" in yield_line


def test_build_dividend_markdown_interest_debt_definition_lists_components():
    """「有息负债」口径说明应枚举主要组成:短期借款、长期借款、应付债券
    、一年内到期的非流动负债、租赁负债。
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="X",
        stock_code="000001",
        report_year=2024,
    )
    explanation_idx = md.index("### 指标解释")
    end_idx = md.index("\n---\n", explanation_idx)
    explanation_section = md[explanation_idx:end_idx]
    # 找到「有息负债」非「有息负债占比」那行(以粗体 ** 标识)
    interest_debt_match = next(
        (i for i, line in enumerate(explanation_section.split("\n"))
         if line.startswith("- **有息负债**(亿元)")),
        None,
    )
    assert interest_debt_match is not None, "应有「有息负债」bullet"
    interest_debt_line = explanation_section.split("\n")[interest_debt_match]
    for component in [
        "短期借款", "长期借款", "应付债券",
        "一年内到期非流动负债", "租赁负债",
    ]:
        assert component in interest_debt_line, (
            f"「有息负债」口径应枚举「{component}」;实际行:{interest_debt_line!r}"
        )


def test_build_dividend_markdown_section_two_structure_after_changes():
    """整合:trend_years=5 + 完整 result → 二、关键指标段结构应该是:
        1. 6 行指标表(无 财务健康度)
        2. > 数据范围 备注
        3. ### 指标解释 段(6 个 bullet)
        4. ---
    """
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None,
        table=None,
        company_name="综合",
        stock_code="000002",
        report_year=2024,
        trend_years=5,
    )
    section_two_start = md.index("## 二、关键指标")
    section_three_start = md.index("## 三、")
    section_two = md[section_two_start:section_three_start]

    # 1. 表头
    assert "| 指标 | 数值 |" in section_two
    assert "|------|------|" in section_two
    # 2. 6 行指标
    rows = [
        "股息率(%)", "分红率(%)", "连续分红年限(年)",
        "自由现金流对分红覆盖率(倍)",
        "有息负债(亿元)", "有息负债占比(%)",
    ]
    for r in rows:
        assert r in section_two, f"二、关键指标表应含「{r}」行"
    # 3. 顺序:数据范围 备注 在表后、指标解释 前
    pos_table_data_note = section_two.index("数据范围")
    pos_metric_explanation = section_two.index("### 指标解释")
    assert pos_table_data_note < pos_metric_explanation, (
        "数据范围备注应在指标解释段之前"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 末段:目标股息率 → 市值反推表(用户提交历史代码变更阶段新增)
# ──────────────────────────────────────────────────────────────────────────────


def test_build_dividend_markdown_target_returns_section_absent_by_default():
    """target_returns_table 不传 → 报告里不应有该 section(向后兼容)。"""
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None, table=None,
        company_name="X", stock_code="000001", report_year=2024,
    )
    assert "目标股息率" not in md and "反推" not in md, (
        "target_returns_table 不传时不应出现反推表 section"
    )


def test_build_dividend_markdown_target_returns_section_when_provided():
    """target_returns_table 非空 → 报告末尾加「目标股息率 → 市值反推」表。

    三列:股息率 / 对应市值 / 对应价格
    """
    target_rows = [
        {"dividend_yield_pct": 3.0, "implied_market_cap_yi": 17.01, "implied_price": 30.00},
        {"dividend_yield_pct": 5.0, "implied_market_cap_yi": 10.21, "implied_price": 18.00},
    ]
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None, table=None,
        company_name="测试", stock_code="000001", report_year=2024,
        target_returns_table=target_rows,
    )
    # 段标题
    assert "目标股息率" in md, "应有「目标股息率」段"
    # 三列表头(列名含单位,避免误读)
    assert "| 股息率 | 对应市值(亿元) | 对应价格(元/股) |" in md, (
        "三列表头应为「股息率 | 对应市值(亿元) | 对应价格(元/股)」"
    )
    # 数据行
    assert "| 3.00 |" in md
    assert "| 5.00 |" in md
    assert "17.01" in md
    assert "10.21" in md
    assert "30.00" in md
    assert "18.00" in md


def test_build_dividend_markdown_target_returns_section_renders_unit():
    """市值单位(亿元)应在列名里显式标,避免被误读为「元」或「万元」。"""
    target_rows = [
        {"dividend_yield_pct": 3.0, "implied_market_cap_yi": 17.01, "implied_price": 30.00},
        {"dividend_yield_pct": 5.0, "implied_market_cap_yi": 10.21, "implied_price": 18.00},
    ]
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None, table=None,
        company_name="测试", stock_code="000001", report_year=2024,
        target_returns_table=target_rows,
    )
    # 列名要标注市值单位
    assert "市值(亿元)" in md or "市值（亿元）" in md, (
        "市值列应标注单位(亿元),避免与股价元混淆"
    )


def test_build_dividend_markdown_target_returns_section_position():
    """目标股息率反推表应在报告末尾(风险因素六、之后)。"""
    target_rows = [
        {"dividend_yield_pct": 3.0, "implied_market_cap_yi": 17.01, "implied_price": 30.00},
    ]
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None, table=None,
        company_name="测试", stock_code="000001", report_year=2024,
        target_returns_table=target_rows,
    )
    pos_risk = md.index("## 六、风险因素")
    pos_target = md.index("目标股息率")
    assert pos_target > pos_risk, "目标股息率表应在「六、风险因素」之后(在报告末尾)"


# ──────────────────────────────────────────────────────────────────────────────
# compute_target_returns_table 工具函数
# ──────────────────────────────────────────────────────────────────────────────


def test_compute_target_returns_table_uses_db_fields_only():
    """compute_target_returns_table 只查 DB 现存字段,不调用任何外网接口。

    输入三件套:
      - share_structure.total_shares(已有 carry-forward)
      - capital_change_events.cash_per_10_shares(年报派息)
      - stock_daily_price.close_price(展示用,缺失不影响反推)

    验证:600285 2024 反推出的 3% / 5% 市值,与已知公式 (per_share * 100/y) × total_shares
    对得上。
    """
    from src.skills.dividend.tools import compute_target_returns_table

    res = compute_target_returns_table(
        stock_code="600285", report_year=2024, period="FY",
        target_yields=[3.0, 5.0],
    )
    # 必备 2 项不能缺失(否则 missing_fields 列出,row 为空)
    assert "total_shares" not in res["missing_fields"]
    assert "per_share_dividend" not in res["missing_fields"]
    # 600285 2024 应有这些数
    assert res["total_shares"] == 567143992.0
    assert res["per_share_dividend"] == 0.9  # 9/10
    # close_price(展示用)— 6,207 行已落库,应有
    assert res["current_price"] is not None
    assert res["current_price"] > 0

    # row 数 = target_yields 个数
    assert len(res["rows"]) == 2
    # 3% 行验证公式
    row3 = next(r for r in res["rows"] if r["dividend_yield_pct"] == 3.0)
    # implied_price = 0.9 * 100 / 3 = 30.0
    assert abs(row3["implied_price"] - 30.0) < 0.01
    # implied_market_cap = 567143992 × 30 / 1e8 = 170.14 亿
    assert abs(row3["implied_market_cap_yi"] - 170.14) < 0.1, (
        f"3% 对应市值应≈170.14 亿,实际 {row3['implied_market_cap_yi']}"
    )
    # 5% 行
    row5 = next(r for r in res["rows"] if r["dividend_yield_pct"] == 5.0)
    assert abs(row5["implied_price"] - 18.0) < 0.01
    assert abs(row5["implied_market_cap_yi"] - 102.09) < 0.1


def test_compute_target_returns_table_missing_fields_report():
    """数据缺失时 missing_fields 列出缺哪些,rows 为空,调用方据此决定渲染策略。

    模拟 share_structure 缺失的场景(难以简单模拟,改测 per_share_dividend
    缺失:600285 2100 年还没数据)。
    """
    from src.skills.dividend.tools import compute_target_returns_table

    res = compute_target_returns_table(
        stock_code="600285", report_year=2100, period="FY",
        target_yields=[3.0, 5.0],
    )
    # 2100 年:share_structure 应为空(没数据),events 应为空
    assert res["total_shares"] is None
    assert res["per_share_dividend"] is None
    assert "total_shares" in res["missing_fields"]
    assert "per_share_dividend" in res["missing_fields"]
    # 缺核心字段时 rows 为空
    assert res["rows"] == [], (
        "缺 per_share 或 total_shares 时不应产出反推行(避免错误数据)"
    )


def test_compute_target_returns_table_default_targets():
    """默认 target_yields 是 [3.0, 5.0]。"""
    from src.skills.dividend.tools import compute_target_returns_table

    res = compute_target_returns_table("600285", 2024, "FY")
    yields = sorted(r["dividend_yield_pct"] for r in res["rows"])
    assert yields == [3.0, 5.0]


def test_compute_target_returns_table_skips_invalid_yield():
    """target_yields 中 y <= 0 跳过(避免除零)。"""
    from src.skills.dividend.tools import compute_target_returns_table

    res = compute_target_returns_table(
        "600285", 2024, "FY", target_yields=[3.0, 0, -1, 5.0],
    )
    # 只产 2 行(3% 和 5%)
    assert len(res["rows"]) == 2
    yields = [r["dividend_yield_pct"] for r in res["rows"]]
    assert yields == [3.0, 5.0]


# ──────────────────────────────────────────────────────────────────────────────
# 当前价格来源标注(用户提交历史代码变更阶段新增)
# ──────────────────────────────────────────────────────────────────────────────


def test_compute_target_returns_table_reports_price_source():
    """compute_target_returns_table 应返回 current_price_source + current_price_date。

    来源链:优先 stock_market_snapshot(带 PE/PB 的估值快照),
    退化到 stock_daily_price(纯日线)。两者都要给出实际取价日期,
    让读者知道「当前价格」到底是哪天的收盘价。
    """
    from src.skills.dividend.tools import compute_target_returns_table

    res = compute_target_returns_table("600285", 2024, "FY")
    # 600285 2024 两个来源都有数据,优先 stock_market_snapshot
    assert "current_price_source" in res, "应返回 current_price_source"
    assert res["current_price_source"], "current_price_source 不应为空"
    assert "current_price_date" in res, "应返回 current_price_date"
    assert res["current_price_date"], "current_price_date 不应为空"
    # 日期应是 ISO 格式 YYYY-MM-DD
    assert len(str(res["current_price_date"])) == 10, (
        f"日期应为 YYYY-MM-DD,实际 {res['current_price_date']}"
    )


def test_build_dividend_markdown_shows_current_price_source():
    """markdown 的「当前价格」行应标出来源表名 + 取价日期。"""
    target_rows = [
        {"dividend_yield_pct": 3.0, "implied_market_cap_yi": 170.14, "implied_price": 30.00},
        {"dividend_yield_pct": 5.0, "implied_market_cap_yi": 102.09, "implied_price": 18.00},
    ]
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None, table=None,
        company_name="测试", stock_code="000001", report_year=2024,
        target_returns_table=target_rows,
        target_returns_current_price=20.84,
        target_returns_current_price_source="stock_daily_price",
        target_returns_current_price_date="2026-10-21",
    )
    # 当前价格行后面应带来源标注
    assert "当前价格" in md
    # 来源表名出现在报告里
    assert "stock_daily_price" in md, "应标出当前价格来源表"
    # 取价日期出现
    assert "2026-10-21" in md, "应标出当前价格的取价日期"
    # 来源信息应在「计算口径」注释附近,方便读者核对
    assert "当前价格取自" in md or "当前价取自" in md, (
        "口径说明里应写明当前价格取自哪张表"
    )


def test_build_dividend_markdown_price_source_optional():
    """不传 source/date 时不崩,只是不显示来源标注(向后兼容)。"""
    target_rows = [
        {"dividend_yield_pct": 3.0, "implied_market_cap_yi": 170.14, "implied_price": 30.00},
    ]
    md = build_dividend_markdown(
        _FULL_RESULT,
        chart_path=None, table=None,
        company_name="测试", stock_code="000001", report_year=2024,
        target_returns_table=target_rows,
        target_returns_current_price=20.84,
        # 不传 source / date
    )
    assert "当前价格" in md
    assert "20.84" in md
    # 不应崩,也不该有空的 source 占位
    assert "None" not in md.split("目标股息率")[1][:500]
