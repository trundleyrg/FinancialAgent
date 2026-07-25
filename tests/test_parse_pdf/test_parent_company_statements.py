from src.db.db_connector import _parse_table_data_to_model_data
from src.db.models import (
    ParentCompanyBalanceSheet,
    ParentCompanyIncomeStatement,
    ParentCompanyCashFlowStatement,
)


def _table(rows):
    return [["项目", "本期金额"]] + [list(r) for r in rows]


def test_parent_balance_sheet_matches_currency_cash():
    data = _table([("货币资金", "12,345,678.90")])
    result = _parse_table_data_to_model_data(
        data, ParentCompanyBalanceSheet, unit_str="元"
    )
    assert result.get("monetary_funds") == 12345678.90


def test_parent_income_statement_matches_revenue_and_cost():
    data = _table(
        [
            ("一、营业收入", "1,000,000,000.00"),
            ("减营业成本", "600,000,000.00"),
        ]
    )
    result = _parse_table_data_to_model_data(
        data, ParentCompanyIncomeStatement, unit_str="元"
    )
    assert result.get("operating_revenue") == 1_000_000_000.00
    assert result.get("operating_costs") == 600_000_000.00


def test_parent_cash_flow_matches_sales_cash():
    data = _table([("销售商品、提供劳务收到的现金", "555,000,000.00")])
    result = _parse_table_data_to_model_data(
        data, ParentCompanyCashFlowStatement, unit_str="元"
    )
    assert result.get("cash_from_sales") == 555_000_000.00


def test_parent_balance_sheet_ignores_goodwill_and_minority():
    data = _table(
        [
            ("货币资金", "10,000.00"),
            ("商誉", "99,999.00"),
            ("少数股东权益", "12,345.00"),
        ]
    )
    result = _parse_table_data_to_model_data(
        data, ParentCompanyBalanceSheet, unit_str="元"
    )
    assert result.get("monetary_funds") == 10_000.00
    assert "goodwill" not in result
    assert "minority_interest" not in result
