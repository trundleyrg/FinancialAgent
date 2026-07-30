import pytest
from src.db import ReportRepository, StatementRepository
from tests.test_db_repository.conftest import FakeConnector


@pytest.fixture
def ui_service(monkeypatch):
    """注入 fake connector 进 DatabaseService，绕开 get_db()。"""
    from ui.backend.services import db_service
    fake = FakeConnector()
    svc = db_service.DatabaseService.__new__(db_service.DatabaseService)
    svc.db_type = "duckdb"
    svc.db = fake
    svc._reports = ReportRepository(fake)
    svc._statements = StatementRepository(fake)
    db_service.DatabaseService._companies_cache = None
    db_service.DatabaseService._years_cache = None
    return svc, fake


def _seed_basic(fake):
    fake.seed("financial_reports", [
        {"id": 1, "company_name": "东阿阿胶", "company_short_name": "东阿",
         "stock_code": "000423", "report_year": 2024, "report_period": "FY",
         "source_file": "f"},
    ])
    fake.seed("consolidated_balance_sheet", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY", "monetary_funds": 1000.0},
    ])
    fake.seed("consolidated_income_statement", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY", "operating_revenue": 500.0},
    ])


def test_get_all_companies_caches(ui_service):
    svc, fake = ui_service
    _seed_basic(fake)
    out = svc.get_all_companies()
    assert out == [{"label": "东阿阿胶 (000423)", "value": "000423"}]
    out2 = svc.get_all_companies()
    assert out2 == out


def test_get_all_years_single_query_no_n_plus_1(ui_service):
    svc, fake = ui_service
    fake.seed("financial_reports", [
        {"id": 1, "company_name": "A", "stock_code": "000001",
         "report_year": 2022, "report_period": "FY", "source_file": "f"},
        {"id": 2, "company_name": "B", "stock_code": "000002",
         "report_year": 2024, "report_period": "FY", "source_file": "f"},
    ])
    svc.get_all_years()
    years_filter_calls = [
        c for c in fake.filter_calls if c[0] == "financial_reports"
    ]
    assert len(years_filter_calls) == 0  # get_all_years doesn't query reports


def test_get_available_periods(ui_service):
    svc, fake = ui_service
    _seed_basic(fake)
    out = svc.get_available_periods("000423", 2024)
    assert out == [{"label": "FY", "value": "FY"}]


def test_get_report(ui_service):
    svc, fake = ui_service
    _seed_basic(fake)
    out = svc.get_report("000423", 2024, "FY")
    assert out["stock_code"] == "000423"


def test_get_financial_data_strips_meta_fields(ui_service):
    svc, fake = ui_service
    _seed_basic(fake)
    out = svc.get_financial_data("000423", 2024, "FY")
    assert out["report"]["stock_code"] == "000423"
    assert "monetary_funds" in out["balance_sheet"]
    assert "id" not in out["balance_sheet"]
    assert "company_name" not in out["balance_sheet"]
    assert "stock_code" not in out["balance_sheet"]
    assert "report_year" not in out["balance_sheet"]
    assert "report_period" not in out["balance_sheet"]
    assert out["income_statement"]["operating_revenue"] == 500.0