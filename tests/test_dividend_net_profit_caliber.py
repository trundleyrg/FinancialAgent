"""多年趋势表的净利口径:归母优先(与列名 / 官方分红比例同口径)。

## 背景

``multi_year_summary["net_profit"]`` 的语义是**归母净利润**:

  - 趋势表列名是「归母净利润(亿元)」
  - 趋势图子图 2 是「归母净利润(亿元)」
  - 分红率口径 = 申报分红总额 / **归母**净利
    (与年报「现金分红占归母净利润比率」同口径)

原实现取值顺序是 ``net_profit``(合并净利)优先,只有 ``net_profit``
解析不出来时才 fallback 到归母净利 —— 口径碰巧对,但一旦 ``net_profit``
能正常解析(2026-11 修好了利润表解析),趋势表就会悄悄换成合并口径。

实测东阿阿胶 2021:
    合并净利 438,913,503.77 → 分红率 96.86%  ❌
    归母净利 440,439,963.60 → 分红率 96.52%  ✅ 官方披露值
"""
from pathlib import Path

import pytest

from src.skills.dividend.tools import _compute_payout_from_events


def test_payout_uses_attributable_net_profit_caliber():
    """分红率分母用归母净利 → 96.52%(官方披露值)。

    这是本 bug 的核心算式:分子取公告的「现金分红总额」,
    分母取归母净利。
    """
    events = [{
        "event_type": "cash_dividend",
        "cash_per_10_shares": 6.601386,
        "cash_dividend_total": 425_113_999.05,
    }]
    shares = 643_976_824.0
    attributable = 440_439_963.60   # 归母净利
    merged = 438_913_503.77         # 合并净利

    payout_attributable = _compute_payout_from_events(events, shares, attributable)
    payout_merged = _compute_payout_from_events(events, shares, merged)

    assert payout_attributable == pytest.approx(96.52, abs=0.01), (
        f"归母口径应为 96.52%,实际 {payout_attributable}"
    )
    # 合并口径会得到 96.86% —— 与官方不符,趋势表不能用它
    assert payout_merged == pytest.approx(96.86, abs=0.01)


def test_multi_year_summary_prefers_attributable_net_profit(monkeypatch, tmp_path):
    """端到端:报告里的分红率必须是 96.52%(归母口径)。

    mock 的利润表同时给 net_profit(合并)与 net_profit_attributable_to_parent
    (归母),验证 skill 取的是后者。
    """
    from src.skills import run_skill
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "999996" / "memory").mkdir(parents=True)

    merged_net_profit = 438_913_503.77       # 合并净利
    attributable_net_profit = 440_439_963.60  # 归母净利

    income = {
        "operating_revenue": 3.849e9,
        "net_profit": merged_net_profit,
        "net_profit_attributable_to_parent": attributable_net_profit,
    }
    cash_flow = {
        "net_cash_from_operations": 2.171e9,
        "cash_for_dividend_and_interest": 1.883e9,
    }
    balance = {"total_assets": 1e10}

    monkeypatch.setattr(
        "src.skills.dividend.skill.get_all_financial_data",
        lambda **kw: {
            "balance_sheet": balance,
            "income_statement": income,
            "cash_flow": cash_flow,
        },
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.get_multi_year_financial_data",
        lambda **kw: {
            "2024": {
                "consolidated_income_statement": income,
                "consolidated_cash_flow_statement": cash_flow,
                "consolidated_balance_sheet": balance,
            },
        },
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.calculate_profitability",
        lambda inc, bs: {"gross_margin": 68.0, "net_margin": 20.0, "roe": 7.7},
    )
    monkeypatch.setattr("src.skills.dividend.skill.calculate_liquidity", lambda bs: {})
    monkeypatch.setattr("src.skills.dividend.skill.calculate_solvency", lambda bs, inc: {})
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
        lambda *a, **k: 10,
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill._fetch_total_shares",
        lambda *a, **k: 643_976_824.0,
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events",
        lambda *a, **k: [{
            "event_type": "cash_dividend",
            "cash_per_10_shares": 6.601386,
            "cash_dividend_total": 425_113_999.05,
        }],
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.query_dividend_events_by_year",
        lambda *a, **k: {"2024": [{
            "event_type": "cash_dividend",
            "cash_per_10_shares": 6.601386,
            "cash_dividend_total": 425_113_999.05,
        }]},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.fetch_total_shares_by_year",
        lambda *a, **k: {"2024": 643_976_824.0},
    )
    monkeypatch.setattr(
        "src.skills.dividend.skill.save_skill_result", lambda *a, **k: True,
    )

    fake_chain = MagicMock()
    fake_chain.invoke.return_value = {
        "investment_rating": "HOLD", "reasoning": "x",
        "dividend_yield": 5.58, "payout_ratio": 96.52,
    }

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

    state = {
        "company_name": "口径测试公司",
        "stock_code": "999996",
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = run_skill("dividend", state, llm=MagicMock())
    assert "error_msg" not in delta, delta.get("error_msg")

    md_files = list(
        (tmp_path / "data" / "999996" / "memory").glob("分析报告_分红_*.md")
    )
    assert md_files, "应生成报告"
    content = md_files[0].read_text(encoding="utf-8")

    # 关键指标表:分红率 96.52(归母口径)
    assert "96.52" in content, (
        f"分红率应用归母净利(96.52%);报告前 1500 字:\n{content[:1500]}"
    )
    # 趋势表「归母净利润(亿元)」列:4.40(归母 440,439,963.60)而非 4.39(合并)
    assert "4.40" in content, "趋势表「归母净利润」列应是归母净利 4.40 亿"
