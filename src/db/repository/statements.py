"""StatementSpec + _STATEMENT_REGISTRY + 注册/反注册 + StatementRepository。

本文件分两部分：spec/registry（注册机制）+ StatementRepository（查询方法）。
新增 task（Task 7）追加 StatementRepository 类。
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Type

from src.db.db_connector import DatabaseConnector
from src.db.models import (
    ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
    ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
    ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement,
)
from src.db.repository.base import BaseRepository
from src.db.repository.keys import ReportKey
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


class StatementRepository(BaseRepository):
    """全部注册报表的统一查询。运行时集合由 _STATEMENT_REGISTRY 决定。"""

    @property
    def statements(self) -> Tuple[str, ...]:
        return list_statements()

    def by_scope(self, scope: str) -> Tuple[str, ...]:
        return tuple(
            n for n, s in _STATEMENT_REGISTRY.items() if s.scope == scope
        )

    def by_kind(self, kind: str) -> Tuple[str, ...]:
        return tuple(
            n for n, s in _STATEMENT_REGISTRY.items() if s.kind == kind
        )

    def get_spec(self, table_name: str) -> Optional[StatementSpec]:
        return _STATEMENT_REGISTRY.get(table_name)

    def get_statement(
        self, key: ReportKey, statement: str,
    ) -> Optional[Dict[str, Any]]:
        if statement not in _STATEMENT_REGISTRY:
            raise ValueError(
                f"未知 statement: {statement}; 可用: {list(_STATEMENT_REGISTRY)}"
            )
        return self._query_first(statement, key)

    def get_all_statements(
        self, key: ReportKey,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        return {stmt: self.get_statement(key, stmt) for stmt in self.statements}

    def get_multi_year_statement(
        self, key: ReportKey, statement: str,
        start_year: int, end_year: int,
    ) -> Dict[int, Dict[str, Any]]:
        if statement not in _STATEMENT_REGISTRY:
            raise ValueError(f"未知 statement: {statement}")
        out: Dict[int, Dict[str, Any]] = {}
        for y in range(start_year, end_year + 1):
            d = self.get_statement(key.with_year(y), statement)
            if d is not None:
                out[y] = d
        return out

    def get_multi_year_all_statements(
        self, key: ReportKey,
        start_year: int, end_year: int,
    ) -> Dict[int, Dict[str, Dict[str, Any]]]:
        out: Dict[int, Dict[str, Dict[str, Any]]] = {}
        for y in range(start_year, end_year + 1):
            year_key = key.with_year(y)
            stmts = self.get_all_statements(year_key)
            if any(stmts.values()):
                out[y] = stmts
        return out

