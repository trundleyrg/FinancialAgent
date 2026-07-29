import pytest

from src.db.repository.statements import (
    StatementSpec,
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
