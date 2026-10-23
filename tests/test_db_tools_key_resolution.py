"""db_tools 的寻址键解析测试(通用性)。

背景:`get_all_financial_data` / `get_multi_year_financial_data` 原先
只按 `company_name` 查 DB。但 company_name 是**可变字段** ——
公司改名、简称不一致、或上游误传股票代码,都会导致查不到数据,
skill 直接 fail-fast(「财务数据为空」)。

`stock_code` 才是稳定主键。本测试锁定新行为:

- 传了 stock_code → 用 stock_code 查(优先,稳)
- 只传 company_name → 向后兼容,仍可用
- company_name 缺失或看着像股票代码 → 自动退化到 stock_code
"""
from unittest.mock import MagicMock, patch

import pytest

from src.tools import db_tools


def _make_stmts():
    """造一个记录调用参数的假 stmts repo。"""
    stmts = MagicMock()
    stmts.get_statement.return_value = {}
    stmts.get_multi_year_all_statements.return_value = {}
    return stmts


def _patch_repos(stmts):
    return patch.object(db_tools, "_get_repos", return_value=(stmts, MagicMock()))


# ──────────────────────────────────────────────────────────────────────────────
# get_all_financial_data
# ──────────────────────────────────────────────────────────────────────────────


def test_get_all_uses_stock_code_when_provided():
    """传了 stock_code → ReportKey 用 stock_code,不再依赖 company_name。"""
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_all_financial_data(
            company_name="某公司", year=2024, period="FY", stock_code="600000",
        )
    key = stmts.get_statement.call_args_list[0][0][0]
    assert key.stock_code == "600000", "stock_code 应被写入 ReportKey"
    assert key.to_filter().get("stock_code") == "600000", (
        "filter 应优先用 stock_code 查询(比 company_name 稳)"
    )


def test_get_all_falls_back_to_company_name():
    """没传 stock_code → 向后兼容,仍按 company_name 查。"""
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_all_financial_data(
            company_name="东阿阿胶", year=2024, period="FY",
        )
    key = stmts.get_statement.call_args_list[0][0][0]
    assert key.company_name == "东阿阿胶"
    assert key.stock_code is None


def test_get_all_survives_company_name_being_a_stock_code():
    """上游误把股票代码传进 company_name(600285 / 实际踩过的坑)。

    此时若 stock_code 有效,应自动退化到 stock_code 查询,
    而不是拿 "600285" 当公司名去查 → 查不到 → skill fail-fast。
    """
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_all_financial_data(
            company_name="600285", year=2024, period="FY", stock_code="600285",
        )
    key = stmts.get_statement.call_args_list[0][0][0]
    assert key.to_filter().get("stock_code") == "600285", (
        "company_name 形似股票代码时应改用 stock_code 查询"
    )
    assert key.to_filter().get("company_name") is None, (
        "不应再拿股票代码当 company_name 去查"
    )


def test_get_all_company_name_none_with_stock_code():
    """company_name=None 但 stock_code 有效 → 仍能查到数据。"""
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_all_financial_data(
            company_name=None, year=2024, period="FY", stock_code="600000",
        )
    key = stmts.get_statement.call_args_list[0][0][0]
    assert key.to_filter().get("stock_code") == "600000"


# ──────────────────────────────────────────────────────────────────────────────
# get_multi_year_financial_data
# ──────────────────────────────────────────────────────────────────────────────


def test_get_multi_year_uses_stock_code_when_provided():
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_multi_year_financial_data(
            company_name="某公司", start_year=2020, end_year=2024,
            period="FY", stock_code="600000",
        )
    key = stmts.get_multi_year_all_statements.call_args_list[0][0][0]
    assert key.to_filter().get("stock_code") == "600000"


def test_get_multi_year_falls_back_to_company_name():
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_multi_year_financial_data(
            company_name="东阿阿胶", start_year=2020, end_year=2024,
        )
    key = stmts.get_multi_year_all_statements.call_args_list[0][0][0]
    assert key.company_name == "东阿阿胶"


def test_get_multi_year_survives_company_name_being_a_stock_code():
    """与 get_all 同理:company_name 形似股票代码时退化到 stock_code。"""
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_multi_year_financial_data(
            company_name="000423", start_year=2020, end_year=2024,
            stock_code="000423",
        )
    key = stmts.get_multi_year_all_statements.call_args_list[0][0][0]
    assert key.to_filter().get("stock_code") == "000423"
    assert key.to_filter().get("company_name") is None


def test_get_multi_year_company_name_none_with_stock_code():
    stmts = _make_stmts()
    with _patch_repos(stmts):
        db_tools.get_multi_year_financial_data(
            company_name=None, start_year=2020, end_year=2024, stock_code="600000",
        )
    key = stmts.get_multi_year_all_statements.call_args_list[0][0][0]
    assert key.to_filter().get("stock_code") == "600000"