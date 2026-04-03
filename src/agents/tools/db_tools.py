"""
数据库查询工具

提供从数据库获取财务数据的工具函数
"""
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger("Agent.DB")

# 延迟导入，避免循环依赖
_db_connector = None


def _get_db_connector():
    """延迟获取数据库连接器"""
    global _db_connector
    if _db_connector is None:
        from src.db.db_connector import get_db
        _db_connector = get_db()
    return _db_connector


def get_balance_sheet(
    company_name: str,
    year: int,
    period: str,
    table_name: str = "consolidated_balance_sheet"
) -> Dict[str, Any]:
    """
    获取资产负债表数据

    Args:
        company_name: 公司名称
        year: 报告年份
        period: 报告周期 (Q1/H1/Q3/FY)
        table_name: 表名，默认合并资产负债表

    Returns:
        资产负债表数据字典
    """
    try:
        db = _get_db_connector()
        records = db.filter_records(
            table_name,
            company_name=company_name,
            report_year=year,
            report_period=period
        )
        if records:
            return records[0]
        logger.warning(f"未找到资产负债表数据: {company_name} {year} {period}")
        return {}
    except Exception as e:
        logger.error(f"获取资产负债表失败: {e}")
        return {}


def get_income_statement(
    company_name: str,
    year: int,
    period: str,
    table_name: str = "consolidated_income_statement"
) -> Dict[str, Any]:
    """
    获取利润表数据

    Args:
        company_name: 公司名称
        year: 报告年份
        period: 报告周期
        table_name: 表名，默认合并利润表

    Returns:
        利润表数据字典
    """
    try:
        db = _get_db_connector()
        records = db.filter_records(
            table_name,
            company_name=company_name,
            report_year=year,
            report_period=period
        )
        if records:
            return records[0]
        logger.warning(f"未找到利润表数据: {company_name} {year} {period}")
        return {}
    except Exception as e:
        logger.error(f"获取利润表失败: {e}")
        return {}


def get_cash_flow(
    company_name: str,
    year: int,
    period: str,
    table_name: str = "consolidated_cash_flow_statement"
) -> Dict[str, Any]:
    """
    获取现金流量表数据

    Args:
        company_name: 公司名称
        year: 报告年份
        period: 报告周期
        table_name: 表名，默认合并现金流量表

    Returns:
        现金流量表数据字典
    """
    try:
        db = _get_db_connector()
        records = db.filter_records(
            table_name,
            company_name=company_name,
            report_year=year,
            report_period=period
        )
        if records:
            return records[0]
        logger.warning(f"未找到现金流量表数据: {company_name} {year} {period}")
        return {}
    except Exception as e:
        logger.error(f"获取现金流量表失败: {e}")
        return {}


def get_all_financial_data(
    company_name: str,
    year: int,
    period: str
) -> Dict[str, Any]:
    """
    获取所有财务表数据

    Args:
        company_name: 公司名称
        year: 报告年份
        period: 报告周期

    Returns:
        包含所有财务表的字典
    """
    return {
        "balance_sheet": get_balance_sheet(company_name, year, period),
        "income_statement": get_income_statement(company_name, year, period),
        "cash_flow": get_cash_flow(company_name, year, period)
    }


def get_db_tools() -> List[callable]:
    """
    获取所有数据库工具

    Returns:
        工具函数列表
    """
    return [
        get_balance_sheet,
        get_income_statement,
        get_cash_flow,
        get_all_financial_data
    ]
