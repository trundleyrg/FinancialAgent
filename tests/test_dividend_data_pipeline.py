"""红利股分析数据管道测试：fetcher → DB → skill 端到端。"""
from __future__ import annotations

import json

import pytest
from langchain_core.runnables import RunnableLambda

from src.db.db_connector import get_db
from src.skills.dividend.skill import run as dividend_run
from src.skills.dividend.tools import (
    compute_dividend_stability_years,
    extract_dividend_info,
)
from src.tools.share_structure_fetcher import (
    fetch_and_persist,
    fetch_share_structure,
)


# ----- extract_dividend_info 字段 fallback -----

def test_extract_dividend_info_uses_net_profit_attributable_to_parent_when_net_profit_is_none():
    """net_profit 字段为 None 时应回退到 net_profit_attributable_to_parent。"""
    fd = {
        "income_statement": {
            "net_profit": None,
            "net_profit_attributable_to_parent": 1_557_000_000.0,
        },
        "cash_flow": {
            "net_cash_from_operations": 2_000_000_000.0,
            "cash_for_dividend_and_interest": 1_000_000_000.0,
            "cash_for_fixed_assets": 200_000_000.0,
        },
    }
    info = extract_dividend_info(fd)
    assert info["net_profit"] == 1_557_000_000.0
    assert info["free_cash_flow"] == 1_800_000_000.0
    # payout = 1e9 / 1.557e9 ≈ 64.23%
    assert 64.0 < info["payout_ratio"] < 65.0


def test_extract_dividend_info_handles_all_none_net_profit():
    """三个候选字段都为 None/缺失时，net_profit = 0，payout_ratio = 0。"""
    fd = {
        "income_statement": {"net_profit": None},
        "cash_flow": {"net_cash_from_operations": 0, "cash_for_dividend_and_interest": 0},
    }
    info = extract_dividend_info(fd)
    assert info["net_profit"] == 0
    assert info["payout_ratio"] == 0


# ----- compute_dividend_stability_years -----

def test_dividend_stability_years_for_000423_in_2024_is_at_least_8():
    """000423 在 2024 视角下应至少有 8 年连续分红（含 2024 之前）。"""
    years = compute_dividend_stability_years("000423", 2024, "FY")
    assert years >= 8, f"期望 >= 8，实际 {years}"


def test_dividend_stability_years_unknown_stock_is_zero():
    """未知股票应返回 0（不抛异常）。"""
    assert compute_dividend_stability_years("999999", 2024, "FY") == 0


# ----- share_structure fetcher -----

def test_fetch_share_structure_000423_local_derivation():
    """akshare 不可达时本地推导 000423 总股本。"""
    data = fetch_share_structure("000423", 2024, "FY")
    # akshare 当前网络不通，期望 source 退化到 local_derivation 或 akshare_spot 至少一个
    assert data["source"] in ("akshare_spot", "local_derivation")
    if data["source"] == "local_derivation":
        assert data["total_shares"] is not None
        # 14.79 亿股 = 1,479,184,875
        assert 1.4e9 < data["total_shares"] < 1.55e9


def test_fetch_and_persist_share_structure_writes_row():
    """fetch_and_persist 应在 share_structure 表中写入/覆盖一行。"""
    ok = fetch_and_persist("000423", 2024, "FY")
    assert ok is True
    conn = get_db()._duckdb_conn
    row = conn.execute(
        """
        SELECT total_shares FROM share_structure
        WHERE stock_code='000423' AND report_year=2024 AND report_period='FY'
        """,
    ).fetchone()
    assert row is not None
    assert row[0] is not None


# ----- 端到端 skill -----

def test_dividend_skill_end_to_end_000423_2024():
    """完整 state + stub_llm 跑 000423 2024 FY，dividend_analysis 不为 None。"""
    stub = RunnableLambda(
        lambda *a, **k: json.dumps(
            {
                "dividend_yield": 3.5, "payout_ratio": 60.0,
                "dividend_stability_years": 10, "cash_flow_coverage": 1.5,
                "financial_health_score": 75,
                "profitability": {"gross_margin": 60, "net_margin": 18, "roe": 12},
                "solvency": {"debt_to_asset": 35},
                "valuation": {"pe_ratio": 25, "pb_ratio": 2.5},
                "risk_factors": [], "investment_rating": "HOLD",
                "reasoning": "stub",
            },
            ensure_ascii=False,
        ),
    )
    state = {
        "company_name": "东阿阿胶股份有限公司",
        "stock_code": "000423",
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = dividend_run(state, stub)
    assert delta.get("dividend_analysis") is not None
    assert delta.get("error_msg") is None
    result = delta["dividend_analysis"]
    assert result["investment_rating"] == "HOLD"
    # 所有 SKILL.md 要求的字段都存在
    for field in [
        "dividend_yield", "payout_ratio", "dividend_stability_years",
        "cash_flow_coverage", "financial_health_score",
        "profitability", "solvency", "valuation",
        "risk_factors", "investment_rating", "reasoning",
    ]:
        assert field in result, f"missing {field}"
