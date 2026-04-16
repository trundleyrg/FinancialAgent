"""
数据库查询服务
"""
from typing import List, Optional, Dict, Any
from pathlib import Path
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from src.db.db_connector import get_db
from src.db.models import ReportPeriod
from src.utils.logger import ui_logger

# 线程池用于后台数据库操作
_executor = ThreadPoolExecutor(max_workers=4)


class DatabaseService:
    """数据库查询服务（支持缓存）"""

    # 类级别的缓存（进程内共享）
    _companies_cache: Optional[List[Dict[str, str]]] = None
    _years_cache: Optional[List[Dict[str, int]]] = None
    _cache_version: int = 0

    def __init__(self, db_type: str = "duckdb"):
        self.db_type = db_type

    def get_db(self):
        """获取数据库连接"""
        return get_db(database_type=self.db_type)

    def get_all_companies(self, use_cache: bool = True) -> List[Dict[str, str]]:
        """
        获取所有公司列表（带缓存）

        Args:
            use_cache: 是否使用缓存，默认True
        """
        # 使用类级别缓存
        if use_cache and DatabaseService._companies_cache is not None:
            return DatabaseService._companies_cache

        try:
            db = self.get_db()
            companies = db.get_all_companies()
            result = [
                {
                    "label": f"{c['company_name']} ({c['stock_code']})",
                    "value": c['stock_code']
                }
                for c in companies
            ]

            # 更新缓存
            DatabaseService._companies_cache = result
            DatabaseService._cache_version += 1

            return result
        except Exception as e:
            ui_logger.error(f"获取公司列表失败: {e}")
            return DatabaseService._companies_cache or []

    def get_all_years(self, use_cache: bool = True) -> List[Dict[str, int]]:
        """
        获取所有年份列表（优化：复用公司数据，避免重复查询）

        Args:
            use_cache: 是否使用缓存，默认True
        """
        if use_cache and DatabaseService._years_cache is not None:
            return DatabaseService._years_cache

        try:
            # 复用已缓存的公司数据，避免重复查询数据库
            companies_data = self.get_all_companies(use_cache=True)
            if not companies_data:
                return DatabaseService._years_cache or []

            db = self.get_db()

            # 使用set去重年份
            all_years = set()
            stock_codes = [c['value'] for c in companies_data]

            # 批量获取年份（优化：减少数据库往返）
            for stock_code in stock_codes:
                years = db.get_company_report_years(stock_code)
                all_years.update(years)

            result = [
                {"label": str(year), "value": year}
                for year in sorted(all_years, reverse=True)
            ]

            # 更新缓存
            DatabaseService._years_cache = result
            DatabaseService._cache_version += 1

            return result
        except Exception as e:
            ui_logger.error(f"获取年份列表失败: {e}")
            return DatabaseService._years_cache or []

    @classmethod
    def invalidate_cache(cls):
        """手动清除缓存（如数据更新后）"""
        cls._companies_cache = None
        cls._years_cache = None
        cls._cache_version += 1

    def get_available_periods(self, stock_code: str, year: int) -> List[Dict[str, str]]:
        """获取指定公司和年份的可用报告周期"""
        try:
            db = self.get_db()
            reports = db.filter_records(
                "financial_reports",
                stock_code=stock_code,
                report_year=year
            )

            periods = []
            seen = set()
            for report in reports:
                period = report.report_period.value if hasattr(report, 'report_period') else report.get('report_period')
                if period and period not in seen:
                    seen.add(period)
                    periods.append({"label": period, "value": period})

            return periods
        except Exception as e:
            ui_logger.error(f"获取可用期间失败: {e}")
            return []

    def get_report(self, stock_code: str, year: int, period: str) -> Optional[Dict[str, Any]]:
        """获取财务报告"""
        try:
            db = self.get_db()
            reports = db.filter_records(
                "financial_reports",
                stock_code=stock_code,
                report_year=year,
                report_period=period
            )

            if not reports:
                return None

            report = reports[0]
            if hasattr(report, '__dict__'):
                return {
                    "id": report.id,
                    "company_name": report.company_name,
                    "company_short_name": report.company_short_name,
                    "stock_code": report.stock_code,
                    "report_year": report.report_year,
                    "report_period": report.report_period.value if hasattr(report, 'report_period') else report.get('report_period'),
                    "source_file": report.source_file,
                    "created_at": report.created_at.isoformat() if hasattr(report, 'created_at') and report.created_at else None
                }
            else:
                return dict(report)

        except Exception as e:
            ui_logger.error(f"获取财务报告失败: {e}")
            return None

    def get_financial_data(self, stock_code: str, year: int, period: str) -> Dict[str, Any]:
        """获取财务数据（资产负债表、利润表、现金流量表）"""
        try:
            db = self.get_db()
            result = {
                "report": None,
                "balance_sheet": None,
                "income_statement": None,
                "cash_flow": None
            }

            # 获取报告信息
            report = self.get_report(stock_code, year, period)
            result["report"] = report

            if not report:
                return result

            # 表名映射
            table_map = {
                "consolidated_balance_sheet": "balance_sheet",
                "parent_company_balance_sheet": "parent_balance_sheet",
                "consolidated_income_statement": "income_statement",
                "parent_company_income_statement": "parent_income_statement",
                "consolidated_cash_flow_statement": "cash_flow",
                "parent_company_cash_flow_statement": "parent_cash_flow",
            }

            for table_name, key in table_map.items():
                records = db.filter_records(
                    table_name,
                    stock_code=stock_code,
                    report_year=year,
                    report_period=period
                )

                if records:
                    record = records[0]
                    if hasattr(record, '__dict__'):
                        data = {k: v for k, v in record.__dict__.items()
                               if not k.startswith('_') and k not in ['id', 'company_name', 'stock_code', 'report_year', 'report_period']}
                    else:
                        data = dict(record)
                        for k in ['id', 'company_name', 'stock_code', 'report_year', 'report_period']:
                            data.pop(k, None)
                    result[key] = data

            return result

        except Exception as e:
            ui_logger.error(f"获取财务数据失败: {e}")
            return {"report": None, "balance_sheet": None, "income_statement": None, "cash_flow": None}
