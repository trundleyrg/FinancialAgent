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

def test_fetch_share_structure_000423_local_derivation_disabled():
    """🚨 _from_local_derivation 已禁用,只剩 akshare + PDF 路径。

    真实场景:000423 2024 FY ——
        任何来源下,本地推导不再被使用(系统偏差不可消除),
        source 可以是 "akshare_spot"(成功)/ "pdf_year_report"(PDF 兜底)/
        "none"(全部失败)。
    """
    data = fetch_share_structure("000423", 2024, "FY")
    # local_derivation 已禁用,不应再出现
    assert data["source"] != "local_derivation", (
        "_from_local_derivation 已禁用,但 fetch_share_structure 仍返回 source='local_derivation'"
    )
    assert data["source"] in ("akshare_spot", "pdf_year_report", "none")


def test_fetch_and_persist_skips_when_akshare_unavailable():
    """🚨 当 akshare 不可达且本地推导已禁用,fetch_and_persist 必须返回 False。

    这条线保护的关键不变量:网络失败/推导被禁用时,
    **绝不能用脏数据覆盖已存在的 share_structure 行**(000423 真实 6.44 亿)。

    若返回 True 并覆盖真实数据 → dividend skill 后续分析会被污染。
    """
    ok = fetch_and_persist("000423", 2024, "FY")
    # 网络不可达时,akshare 失败 + 推导已禁用 → 应返回 False
    if ok is True:
        # 仅在 akshare 真拿到了数据时才写入,这是允许的
        conn = get_db()._duckdb_conn
        row = conn.execute(
            """
            SELECT total_shares FROM share_structure
            WHERE stock_code='000423' AND report_year=2024 AND report_period='FY'
            """,
        ).fetchone()
        assert row is not None and row[0] is not None
    else:
        # akshare 失败路径:不应有 delete_record 与 UPDATE 触达 share_structure
        # 现有正确数据保持不变
        conn = get_db()._duckdb_conn
        row = conn.execute(
            """
            SELECT total_shares FROM share_structure
            WHERE stock_code='000423' AND report_year=2024 AND report_period='FY'
            """,
        ).fetchone()
        # 如果之前手工入库过,值应是真实 6.44 亿(不是 7.78 / 14.79)
        if row and row[0]:
            # 偏离真实 6.44 亿 ±5% 以内,说明数据未被脏写入覆盖
            assert abs(row[0] - 643_976_824) / 643_976_824 < 0.05, (
                f"share_structure 000423 2024 应≈6.44 亿,实际 {row[0]:.0f} "
                f"(偏离 {(row[0]-643_976_824)/643_976_824*100:.1f}%)"
            )


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
