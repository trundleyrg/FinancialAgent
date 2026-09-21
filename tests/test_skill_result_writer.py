"""Skill 结果通用写表工具测试。"""
from __future__ import annotations

import json

import pytest
from langchain_core.runnables import RunnableLambda

from src.db.db_connector import get_db
from src.skills.dividend.skill import run as dividend_run
from src.tools.skill_result_writer import (
    _extract_rating,
    _extract_summary,
    _safe_json_dumps,
    save_skill_result,
    save_skill_result_from_delta,
)


@pytest.fixture(autouse=True)
def _clean_rows():
    """每个用例前清掉 000423 dividend 测试行。"""
    conn = get_db()._duckdb_conn
    conn.execute(
        "DELETE FROM skill_analysis_results WHERE stock_code='000423' AND skill_name IN ('dividend','cyclical','fundamental','summary')",
    )
    yield
    conn.execute(
        "DELETE FROM skill_analysis_results WHERE stock_code='000423' AND skill_name IN ('dividend','cyclical','fundamental','summary')",
    )


# ----- helpers -----

def test_extract_rating_finds_investment_rating():
    assert _extract_rating({"investment_rating": "BUY"}) == "BUY"
    assert _extract_rating({"cyclical_rating": "SELL"}) == "SELL"
    assert _extract_rating({"rating": "hold"}) == "hold"
    assert _extract_rating({}) is None
    assert _extract_rating(None) is None
    assert _extract_rating({"investment_rating": ""}) is None  # 空字符串不算


def test_extract_summary_finds_reasoning():
    assert _extract_summary({"reasoning": "abc"}) == "abc"
    assert _extract_summary({"summary": "xyz"}) == "xyz"
    assert _extract_summary({}) is None


def test_safe_json_dumps_handles_datetime():
    from datetime import datetime
    payload = {"created": datetime(2026, 9, 21, 12, 0, 0), "amount": 1.5}
    out = _safe_json_dumps(payload)
    d = json.loads(out)
    assert d["created"] == "2026-09-21T12:00:00"
    assert d["amount"] == 1.5


# ----- save_skill_result -----

def test_save_skill_result_writes_one_row():
    state = {"company_name": "东阿阿胶", "stock_code": "000423", "report_year": 2024, "report_period": "FY"}
    result = {"investment_rating": "BUY", "reasoning": "rationale text", "extra_field": 42}

    assert save_skill_result("dividend", state, result) is True

    conn = get_db()._duckdb_conn
    rows = conn.execute(
        """SELECT skill_name, stock_code, report_year, report_period,
                  investment_rating, summary, payload_json
           FROM skill_analysis_results
           WHERE stock_code='000423' AND skill_name='dividend'""",
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "dividend"
    assert row[1] == "000423"
    assert row[2] == 2024
    assert row[3] == "FY"
    assert row[4] == "BUY"
    assert row[5] == "rationale text"
    payload = json.loads(row[6])
    assert payload["extra_field"] == 42


def test_save_skill_result_skips_empty_or_non_dict():
    state = {"stock_code": "000423"}
    assert save_skill_result("dividend", state, None) is False
    assert save_skill_result("dividend", state, {}) is False
    assert save_skill_result("dividend", state, "not a dict") is False


def test_save_skill_result_does_not_raise_on_db_error(monkeypatch):
    """DB 异常时仅日志，不抛。"""
    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB error")
    monkeypatch.setattr("src.tools.skill_result_writer.get_db", boom)
    # 仍应返回 False 而不抛
    assert save_skill_result(
        "dividend", {"stock_code": "000423"}, {"investment_rating": "BUY"},
    ) is False


def test_save_skill_result_handles_null_state_fields():
    """state 中 stock_code/year/period 缺失时仍能写入（列为 NULL）。"""
    state = {"company_name": "X"}  # 缺 stock_code/year
    ok = save_skill_result("cyclical", state, {"rating": "HOLD"})
    assert ok is True


# ----- save_skill_result_from_delta -----

def test_save_skill_result_from_delta_dividend_pattern():
    delta = {"dividend_analysis": {"investment_rating": "HOLD", "reasoning": "..."}}
    ok = save_skill_result_from_delta("dividend", {"stock_code": "000423", "report_year": 2024}, delta)
    assert ok is True
    assert get_db()._duckdb_conn.execute(
        "SELECT COUNT(*) FROM skill_analysis_results WHERE stock_code='000423' AND skill_name='dividend'",
    ).fetchone()[0] == 1


def test_save_skill_result_from_delta_skips_error_msg():
    delta = {"dividend_analysis": None, "error_msg": "数据缺失"}
    assert save_skill_result_from_delta("dividend", {"stock_code": "000423"}, delta) is False
    assert get_db()._duckdb_conn.execute(
        "SELECT COUNT(*) FROM skill_analysis_results WHERE stock_code='000423'",
    ).fetchone()[0] == 0


# ----- skill 集成 -----

def test_full_dividend_skill_writes_to_db():
    """完整 dividend skill 跑通后，DB 必须有 1 行 dividend skill 结果。"""
    stub = RunnableLambda(
        lambda *a, **k: json.dumps(
            {
                "dividend_yield": 3.5, "payout_ratio": 60.0,
                "dividend_stability_years": 10, "cash_flow_coverage": 1.5,
                "financial_health_score": 75,
                "profitability": {"gross_margin": 60, "net_margin": 18, "roe": 12},
                "solvency": {"debt_to_asset": 35},
                "valuation": {"pe_ratio": 25, "pb_ratio": 2.5},
                "risk_factors": [], "investment_rating": "BUY",
                "reasoning": "测试持久化",
            },
            ensure_ascii=False,
        ),
    )
    state = {
        "company_name": "东阿阿胶股份有限公司",
        "stock_code": "000423", "report_year": 2024, "report_period": "FY",
    }
    delta = dividend_run(state, stub)
    assert delta["dividend_analysis"]["investment_rating"] == "BUY"

    conn = get_db()._duckdb_conn
    row = conn.execute(
        """SELECT skill_name, stock_code, report_year, investment_rating, summary
           FROM skill_analysis_results
           WHERE stock_code='000423' AND skill_name='dividend'
           ORDER BY id DESC LIMIT 1""",
    ).fetchone()
    assert row is not None
    assert row[0] == "dividend"
    assert row[3] == "BUY"
    assert row[4] == "测试持久化"


# ----- SQL 查询样例（用户问题）-----

def test_sql_query_example():
    """演示用户要的那种 SQL 查询：按 stock_code 拉所有 skill 评级。"""
    save_skill_result(
        "dividend", {"stock_code": "000423", "report_year": 2024, "report_period": "FY"},
        {"investment_rating": "BUY", "reasoning": "rate1"},
    )
    save_skill_result(
        "cyclical", {"stock_code": "000423", "report_year": 2024, "report_period": "FY"},
        {"investment_rating": "HOLD", "reasoning": "rate2"},
    )

    rows = get_db()._duckdb_conn.execute(
        """
        SELECT skill_name, report_year, investment_rating
        FROM skill_analysis_results
        WHERE stock_code = '000423'
        ORDER BY skill_name, report_year DESC
        """,
    ).fetchall()
    by_skill = {r[0]: r for r in rows}
    assert by_skill["dividend"][2] == "BUY"
    assert by_skill["cyclical"][2] == "HOLD"
