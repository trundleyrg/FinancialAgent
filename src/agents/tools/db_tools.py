"""数据库查询工具（薄适配层）。

LLM 工具签名保持向后兼容；内部全部走 StatementRepository / ReportRepository。
"""
import datetime
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Agent.DB")

# 短别名 → 规范名（仅这 6 张有别名；新报表按规范名调 repo）
_STATEMENT_ALIASES = {
    "balance_sheet":            "consolidated_balance_sheet",
    "parent_balance_sheet":     "parent_company_balance_sheet",
    "income_statement":         "consolidated_income_statement",
    "parent_income_statement":  "parent_company_income_statement",
    "cash_flow":                "consolidated_cash_flow_statement",
    "parent_cash_flow":         "parent_company_cash_flow_statement",
}

_db = None
_stmt_repo = None
_report_repo = None


def _get_repos():
    """延迟初始化：首次调用时建 connector + repo。"""
    global _db, _stmt_repo, _report_repo
    if _db is None:
        from src.db.db_connector import get_db
        from src.db import StatementRepository, ReportRepository

        _db = get_db()
        _stmt_repo = StatementRepository(_db)
        _report_repo = ReportRepository(_db)
    return _stmt_repo, _report_repo


def _resolve_statement(name: str) -> str:
    """接受规范名或短别名；都返回规范名。"""
    from src.db.repository.statements import list_statements
    if name in list_statements():
        return name
    if name in _STATEMENT_ALIASES:
        return _STATEMENT_ALIASES[name]
    raise ValueError(f"未知 statement: {name}")


def _key(
    stock_code: Optional[str] = None,
    company_name: Optional[str] = None,
    year: Optional[int] = None,
    period: Optional[str] = None,
):
    """轻量本地构造 ReportKey，避免循环导入。"""
    from src.db import ReportKey
    return ReportKey(
        stock_code=stock_code, company_name=company_name,
        year=year, period=period,
    )


def _get_statement(
    company_name: str, year: int, period: str, default_table: str,
) -> Dict[str, Any]:
    """三个 get_*_statement 共用的查询逻辑。"""
    stmts, _ = _get_repos()
    out = stmts.get_statement(
        _key(company_name=company_name, year=year, period=period),
        _resolve_statement(default_table),
    )
    return out if out is not None else {}


def get_balance_sheet(
    company_name: str, year: int, period: str,
    table_name: str = "consolidated_balance_sheet",
) -> Dict[str, Any]:
    """获取资产负债表数据。"""
    try:
        return _get_statement(company_name, year, period, table_name)
    except Exception as e:
        logger.error(f"获取资产负债表失败: {e}")
        return {}


def get_income_statement(
    company_name: str, year: int, period: str,
    table_name: str = "consolidated_income_statement",
) -> Dict[str, Any]:
    """获取利润表数据。"""
    try:
        return _get_statement(company_name, year, period, table_name)
    except Exception as e:
        logger.error(f"获取利润表失败: {e}")
        return {}


def get_cash_flow(
    company_name: str, year: int, period: str,
    table_name: str = "consolidated_cash_flow_statement",
) -> Dict[str, Any]:
    """获取现金流量表数据。"""
    try:
        return _get_statement(company_name, year, period, table_name)
    except Exception as e:
        logger.error(f"获取现金流量表失败: {e}")
        return {}


def get_all_financial_data(
    company_name: str, year: int, period: str,
) -> Dict[str, Any]:
    """获取 3 张合并表（向后兼容的旧形状）。"""
    stmts, _ = _get_repos()
    key = _key(company_name=company_name, year=year, period=period)
    return {
        "balance_sheet":    stmts.get_statement(key, "consolidated_balance_sheet"),
        "income_statement": stmts.get_statement(key, "consolidated_income_statement"),
        "cash_flow":        stmts.get_statement(key, "consolidated_cash_flow_statement"),
    }


def get_multi_year_financial_data(
    company_name: str, start_year: int, end_year: int, period: str = "FY",
) -> Dict[str, Any]:
    """获取多年财务数据（旧形状：{year_str: {3 张合并表}}）。

    缺失年份键缺失 — 不抛错。
    """
    stmts, _ = _get_repos()
    key = _key(company_name=company_name, period=period)
    multi = stmts.get_multi_year_all_statements(key, start_year, end_year)
    return {
        str(y): {
            k: multi[y].get(k) for k in (
                "consolidated_balance_sheet",
                "consolidated_income_statement",
                "consolidated_cash_flow_statement",
            )
        }
        for y in sorted(multi)
    }


def check_company_data_availability(
    company_name: str, stock_code: Optional[str] = None, years: int = 10,
) -> Dict[str, Any]:
    """检查公司在数据库中是否存在近 N 年的数据。"""
    _, report_repo = _get_repos()
    try:
        if stock_code:
            key = _key(stock_code=stock_code)
        else:
            key = _key(company_name=company_name)
        return report_repo.check_data_availability(key, years=years)
    except Exception as e:
        logger.error(f"检查数据可用性失败: {e}")
        current_year = datetime.datetime.now().year
        return {
            "has_data": False,
            "available_years": [],
            "missing_years": list(range(current_year - years + 1, current_year + 1)),
            "data_coverage": 0.0,
            "has_latest_year": False,
            "error": str(e),
        }


def get_db_tools() -> List[callable]:
    """获取所有数据库工具（LLM 工具列表）。"""
    return [
        get_balance_sheet,
        get_income_statement,
        get_cash_flow,
        get_all_financial_data,
        get_multi_year_financial_data,
        check_company_data_availability,
    ]