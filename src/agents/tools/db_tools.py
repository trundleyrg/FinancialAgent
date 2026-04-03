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
        get_all_financial_data,
        check_company_data_availability
    ]


def check_company_data_availability(
    company_name: str,
    stock_code: Optional[str] = None,
    years: int = 10
) -> Dict[str, Any]:
    """
    检查公司在数据库中是否存在近 N 年的数据

    Args:
        company_name: 公司名称
        stock_code: 股票代码（可选）
        years: 检查的年份数量，默认 10 年

    Returns:
        包含检查结果的字典：
        {
            "has_data": bool,           # 是否有足够数据
            "available_years": List[int],  # 可用的年份列表
            "missing_years": List[int],    # 缺失的年份列表
            "data_coverage": float,         # 数据覆盖率 (0-1)
            "has_latest_year": bool         # 是否有最新年份数据
        }
    """
    import datetime

    try:
        db = _get_db_connector()
        current_year = datetime.datetime.now().year

        # 需要检查的年份范围（近 N 年）
        required_years = list(range(current_year - years + 1, current_year + 1))

        # 查询该公司所有可用的年份
        # 使用 FinancialReport 表查询可用年份
        try:
            from src.db.models import FinancialReport
            query = FinancialReport.select(FinancialReport.report_year).distinct()

            if stock_code:
                query = query.where(FinancialReport.stock_code == stock_code)
            else:
                query = query.where(FinancialReport.company_name == company_name)

            available_years = [record.report_year for record in query]
            available_years = list(set(available_years))

        except Exception as e:
            logger.warning(f"查询可用年份失败，使用 filter_records 方式: {e}")
            # 备用方式：直接查询
            records = db.filter_records(
                "financial_reports",
                company_name=company_name,
                stock_code=stock_code
            ) if stock_code else db.filter_records(
                "financial_reports",
                company_name=company_name
            )
            available_years = list(set([r.get("report_year") for r in records if r.get("report_year")]))

        # 计算缺失年份
        missing_years = [y for y in required_years if y not in available_years]

        # 数据覆盖率
        data_coverage = len(available_years) / years if years > 0 else 0

        # 是否有最新年份数据
        has_latest_year = current_year in available_years

        result = {
            "has_data": len(available_years) >= years * 0.5,  # 至少 50% 数据认为有足够数据
            "available_years": sorted(available_years),
            "missing_years": sorted(missing_years),
            "data_coverage": round(data_coverage, 2),
            "has_latest_year": has_latest_year,
            "required_years": required_years,
            "total_available": len(available_years)
        }

        logger.info(f"数据可用性检查: {company_name}, 可用 {len(available_years)}/{years} 年, 覆盖率 {result['data_coverage']:.0%}")

        return result

    except Exception as e:
        logger.error(f"检查数据可用性失败: {e}")
        return {
            "has_data": False,
            "available_years": [],
            "missing_years": list(range(datetime.datetime.now().year - years + 1, datetime.datetime.now().year + 1)),
            "data_coverage": 0.0,
            "has_latest_year": False,
            "error": str(e)
        }
