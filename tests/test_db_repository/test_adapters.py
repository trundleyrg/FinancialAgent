import pytest
from src.tools import db_tools
from tests.test_db_repository.conftest import FakeConnector


@pytest.fixture(autouse=True)
def _reset_db_tools_singleton(monkeypatch):
    """每个测试重置 db_tools 模块级单例。"""
    monkeypatch.setattr(db_tools, "_db", None)
    monkeypatch.setattr(db_tools, "_stmt_repo", None)
    monkeypatch.setattr(db_tools, "_report_repo", None)


@pytest.fixture
def wired_repos(fake_connector, monkeypatch):
    """注入 fake connector + repo，避免真 DuckDB。"""
    from src.db import StatementRepository, ReportRepository
    monkeypatch.setattr(db_tools, "_db", fake_connector)
    monkeypatch.setattr(db_tools, "_stmt_repo", StatementRepository(fake_connector))
    monkeypatch.setattr(db_tools, "_report_repo", ReportRepository(fake_connector))
    return fake_connector


def test_get_balance_sheet_default_table(wired_repos):
    wired_repos.seed("consolidated_balance_sheet", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY", "monetary_funds": 1000.0},
    ])
    out = db_tools.get_balance_sheet("东阿阿胶", 2024, "FY")
    assert out["monetary_funds"] == 1000.0


def test_get_balance_sheet_short_alias(wired_repos):
    wired_repos.seed("parent_company_balance_sheet", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY", "monetary_funds": 500.0},
    ])
    out = db_tools.get_balance_sheet("东阿阿胶", 2024, "FY",
                                     table_name="parent_balance_sheet")
    assert out["monetary_funds"] == 500.0


def test_get_balance_sheet_no_data_returns_empty_dict(wired_repos):
    out = db_tools.get_balance_sheet("不存在", 2024, "FY")
    assert out == {}


def test_get_all_financial_data_three_consolidated(wired_repos):
    wired_repos.seed("consolidated_income_statement", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY",
         "operating_revenue": 100.0},
    ])
    out = db_tools.get_all_financial_data("东阿阿胶", 2024, "FY")
    assert "balance_sheet" in out
    assert "income_statement" in out
    assert "cash_flow" in out
    assert out["income_statement"]["operating_revenue"] == 100.0
    assert out["balance_sheet"] is None
    assert out["cash_flow"] is None


def test_get_multi_year_financial_data_old_shape(wired_repos):
    wired_repos.seed("consolidated_income_statement", [
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY",
         "operating_revenue": 100.0},
    ])
    out = db_tools.get_multi_year_financial_data("A", 2023, 2024, period="FY")
    assert "2024" in out
    assert "2023" not in out


def test_check_company_data_availability(wired_repos):
    wired_repos.seed("financial_reports", [
        {"id": 1, "company_name": "A", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY", "source_file": "f"},
    ])
    out = db_tools.check_company_data_availability("A", stock_code="000423", years=3)
    assert out["available_years"] == [2024]


def test_get_db_tools_returns_callables():
    tools = db_tools.get_db_tools()
    assert callable(tools[0])
    assert len(tools) == 6