import pytest

from src.db.repository.keys import ReportKey
from src.db.repository.statements import (
    StatementSpec,
    StatementRepository,
    register_statement,
    unregister_statement,
    list_statements,
    _STATEMENT_REGISTRY,
)
from src.db.models import (
    ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
    ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
    ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement,
)


def _reset_registry():
    """每个测试前后重置注册表到 6 张默认。"""
    _STATEMENT_REGISTRY.clear()
    for spec in _DEFAULT_SPECS():
        _STATEMENT_REGISTRY[spec.table_name] = spec


def _DEFAULT_SPECS():
    return (
        StatementSpec("consolidated_balance_sheet", "合并资产负债表",
                      "consolidated", "balance_sheet", ConsolidatedBalanceSheet),
        StatementSpec("parent_company_balance_sheet", "母公司资产负债表",
                      "parent_company", "balance_sheet", ParentCompanyBalanceSheet),
        StatementSpec("consolidated_income_statement", "合并利润表",
                      "consolidated", "income_statement", ConsolidatedIncomeStatement),
        StatementSpec("parent_company_income_statement", "母公司利润表",
                      "parent_company", "income_statement", ParentCompanyIncomeStatement),
        StatementSpec("consolidated_cash_flow_statement", "合并现金流量表",
                      "consolidated", "cash_flow", ConsolidatedCashFlowStatement),
        StatementSpec("parent_company_cash_flow_statement", "母公司现金流量表",
                      "parent_company", "cash_flow", ParentCompanyCashFlowStatement),
    )


@pytest.fixture(autouse=True)
def reset_each_test():
    _reset_registry()
    yield
    _reset_registry()


class TestStatementSpec:
    def test_fields(self):
        s = StatementSpec("t", "显示名", "consolidated", "balance_sheet",
                          ConsolidatedBalanceSheet)
        assert s.table_name == "t"
        assert s.display_name == "显示名"
        assert s.scope == "consolidated"
        assert s.kind == "balance_sheet"
        assert s.model_class is ConsolidatedBalanceSheet


class TestRegistry:
    def test_default_has_six(self):
        assert len(list_statements()) == 6

    def test_register_new_statement(self):
        spec = StatementSpec("notes_schedule", "附注明细",
                             "consolidated", "other", ConsolidatedBalanceSheet)
        register_statement(spec)
        assert "notes_schedule" in list_statements()
        assert len(list_statements()) == 7

    def test_register_overwrites_existing(self, caplog):
        spec = StatementSpec("consolidated_balance_sheet", "新名",
                             "consolidated", "balance_sheet", ConsolidatedBalanceSheet)
        register_statement(spec)
        assert _STATEMENT_REGISTRY["consolidated_balance_sheet"].display_name == "新名"

    def test_unregister(self):
        unregister_statement("consolidated_balance_sheet")
        assert "consolidated_balance_sheet" not in list_statements()


class TestStatementRepositoryBasics:
    def test_statements_property_returns_6_by_default(self, fake_connector):
        repo = StatementRepository(fake_connector)
        assert len(repo.statements) == 6

    def test_by_scope_consolidated(self, fake_connector):
        repo = StatementRepository(fake_connector)
        names = repo.by_scope("consolidated")
        assert set(names) == {
            "consolidated_balance_sheet",
            "consolidated_income_statement",
            "consolidated_cash_flow_statement",
        }

    def test_by_scope_parent_company(self, fake_connector):
        repo = StatementRepository(fake_connector)
        names = repo.by_scope("parent_company")
        assert set(names) == {
            "parent_company_balance_sheet",
            "parent_company_income_statement",
            "parent_company_cash_flow_statement",
        }

    def test_by_kind_balance_sheet(self, fake_connector):
        repo = StatementRepository(fake_connector)
        names = repo.by_kind("balance_sheet")
        assert set(names) == {
            "consolidated_balance_sheet",
            "parent_company_balance_sheet",
        }

    def test_by_kind_unknown_returns_empty(self, fake_connector):
        repo = StatementRepository(fake_connector)
        assert repo.by_kind("nonexistent") == ()

    def test_get_spec(self, fake_connector):
        repo = StatementRepository(fake_connector)
        spec = repo.get_spec("consolidated_balance_sheet")
        assert spec is not None
        assert spec.scope == "consolidated"
        assert repo.get_spec("nope") is None

    def test_register_statement_visible_after(self, fake_connector):
        new_spec = StatementSpec(
            "notes_schedule", "附注明细",
            "consolidated", "other", ConsolidatedBalanceSheet,
        )
        register_statement(new_spec)
        repo = StatementRepository(fake_connector)
        assert "notes_schedule" in repo.statements
        assert repo.by_kind("other") == ("notes_schedule",)


def _seed_statement(conn, table_name, rows):
    conn.seed(table_name, rows)


class TestGetStatement:
    def test_returns_dict(self, fake_connector):
        _seed_statement(fake_connector, "consolidated_balance_sheet", [
            {"company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY",
             "monetary_funds": 1000.0, "total_assets": 5000.0},
        ])
        repo = StatementRepository(fake_connector)
        out = repo.get_statement(
            ReportKey(stock_code="000001", year=2024, period="FY"),
            "consolidated_balance_sheet",
        )
        assert out["monetary_funds"] == 1000.0

    def test_unknown_statement_raises(self, fake_connector):
        repo = StatementRepository(fake_connector)
        with pytest.raises(ValueError, match="未知 statement"):
            repo.get_statement(ReportKey(stock_code="000001"), "nope")


class TestGetAllStatements:
    def test_returns_six_keys_with_none_for_missing(self, fake_connector):
        _seed_statement(fake_connector, "consolidated_balance_sheet", [
            {"company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "monetary_funds": 1.0},
        ])
        repo = StatementRepository(fake_connector)
        out = repo.get_all_statements(
            ReportKey(stock_code="000001", year=2024, period="FY")
        )
        assert set(out.keys()) == {
            "consolidated_balance_sheet",
            "parent_company_balance_sheet",
            "consolidated_income_statement",
            "parent_company_income_statement",
            "consolidated_cash_flow_statement",
            "parent_company_cash_flow_statement",
        }
        assert out["consolidated_balance_sheet"]["monetary_funds"] == 1.0
        assert out["parent_company_balance_sheet"] is None


class TestMultiYear:
    def test_multi_year_statement_missing_years_absent(self, fake_connector):
        _seed_statement(fake_connector, "consolidated_balance_sheet", [
            {"company_name": "A", "stock_code": "000001",
             "report_year": 2022, "report_period": "FY", "monetary_funds": 100.0},
            {"company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "monetary_funds": 200.0},
        ])
        repo = StatementRepository(fake_connector)
        out = repo.get_multi_year_statement(
            ReportKey(stock_code="000001", period="FY"),
            "consolidated_balance_sheet",
            start_year=2021, end_year=2024,
        )
        assert set(out.keys()) == {2022, 2024}
        assert out[2024]["monetary_funds"] == 200.0

    def test_multi_year_all_statements_per_year_dict(self, fake_connector):
        _seed_statement(fake_connector, "consolidated_balance_sheet", [
            {"company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "monetary_funds": 1.0},
        ])
        _seed_statement(fake_connector, "parent_company_balance_sheet", [
            {"company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "monetary_funds": 0.5},
        ])
        repo = StatementRepository(fake_connector)
        out = repo.get_multi_year_all_statements(
            ReportKey(stock_code="000001", period="FY"),
            start_year=2024, end_year=2024,
        )
        assert 2024 in out
        assert out[2024]["consolidated_balance_sheet"]["monetary_funds"] == 1.0
        assert out[2024]["parent_company_balance_sheet"]["monetary_funds"] == 0.5
