"""StatementSpec + _STATEMENT_REGISTRY + 注册/反注册 + StatementRepository。

本文件分两部分：spec/registry（注册机制）+ StatementRepository（查询方法）。
新增 task（Task 7）追加 StatementRepository 类。
"""
from dataclasses import dataclass
from typing import Dict, Tuple, Type

from src.db.models import (
    ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
    ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
    ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement,
)
from src.utils.logger import db_logger


@dataclass(frozen=True)
class StatementSpec:
    """报表注册条目。新增一张报表 = 构造一个 spec 并 register_statement()。"""

    table_name: str
    display_name: str
    scope: str         # "consolidated" | "parent_company" | 未来扩展值
    kind: str          # "balance_sheet" | "income_statement" | "cash_flow"
    model_class: Type


_STATEMENT_REGISTRY: Dict[str, StatementSpec] = {
    spec.table_name: spec for spec in (
        StatementSpec(
            "consolidated_balance_sheet", "合并资产负债表",
            scope="consolidated", kind="balance_sheet",
            model_class=ConsolidatedBalanceSheet,
        ),
        StatementSpec(
            "parent_company_balance_sheet", "母公司资产负债表",
            scope="parent_company", kind="balance_sheet",
            model_class=ParentCompanyBalanceSheet,
        ),
        StatementSpec(
            "consolidated_income_statement", "合并利润表",
            scope="consolidated", kind="income_statement",
            model_class=ConsolidatedIncomeStatement,
        ),
        StatementSpec(
            "parent_company_income_statement", "母公司利润表",
            scope="parent_company", kind="income_statement",
            model_class=ParentCompanyIncomeStatement,
        ),
        StatementSpec(
            "consolidated_cash_flow_statement", "合并现金流量表",
            scope="consolidated", kind="cash_flow",
            model_class=ConsolidatedCashFlowStatement,
        ),
        StatementSpec(
            "parent_company_cash_flow_statement", "母公司现金流量表",
            scope="parent_company", kind="cash_flow",
            model_class=ParentCompanyCashFlowStatement,
        ),
    )
}


def register_statement(spec: StatementSpec) -> None:
    """注册一张新报表。覆盖同名 spec 时打 warning 日志。"""
    if spec.table_name in _STATEMENT_REGISTRY:
        db_logger.warning(
            "register_statement: 覆盖已有 spec (%s)", spec.table_name
        )
    _STATEMENT_REGISTRY[spec.table_name] = spec


def unregister_statement(table_name: str) -> None:
    """注销一张报表（主要用于测试）。"""
    _STATEMENT_REGISTRY.pop(table_name, None)


def list_statements() -> Tuple[str, ...]:
    """当前注册的全部报表 table_name。"""
    return tuple(_STATEMENT_REGISTRY.keys())
