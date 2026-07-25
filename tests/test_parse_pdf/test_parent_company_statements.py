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


from src.db.db_connector import save_tables_to_db
from src.db.table_models import TableWithHeader


class _FakeConnector:
    def __init__(self):
        self.created = []

    def insert_record(self, table_name, **kwargs):
        self.created.append((table_name, kwargs))
        return 1

    def filter_records(self, table_name, **kwargs):
        return []

    def update_record(self, table_name, record_id, **kwargs):
        return True


def _fake_table(table_data, unit="元"):
    return TableWithHeader(
        table_data=[["项目", "本期金额"]] + table_data,
        header_text="",
        page_start_num=0,
        page_end_num=0,
        bbox=(0, 0, 0, 0),
        is_merged=False,
        unit=unit,
    )


def test_save_drops_parent_only_invariants(monkeypatch):
    connector = _FakeConnector()
    table = _fake_table([("货币资金", "10.00"), ("商誉", "9,999.00")])
    monkeypatch.setattr(
        "src.db.db_connector.TABLE_NAME_TO_MODEL",
        {"母公司资产负债表": ParentCompanyBalanceSheet},
    )
    save_tables_to_db(
        main_tables={"母公司资产负债表": table},
        company_name="东阿阿胶",
        pdf_path="x.pdf",
        company_short_name="东阿",
        company_code="000423",
        report_year=2024,
        report_period="FY",
        db_connector=connector,
    )
    assert connector.created, "expected at least one record"
    parent_entries = [
        (name, payload)
        for name, payload in connector.created
        if name == "parent_company_balance_sheet"
    ]
    assert parent_entries, "expected parent_company_balance_sheet record"
    table_name, data = parent_entries[0]
    assert table_name == "parent_company_balance_sheet"
    assert data["monetary_funds"] == 10.0
    assert "goodwill" not in data
    assert "minority_interest" not in data
