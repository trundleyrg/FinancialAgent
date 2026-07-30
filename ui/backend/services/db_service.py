"""数据库查询服务（UI 薄适配）。"""
from typing import Any, Dict, List, Optional

from src.db import ReportKey, ReportRepository, StatementRepository
from src.db.db_connector import DatabaseConnector
from src.utils.logger import ui_logger


class DatabaseService:
    """数据库查询服务（带类级缓存）。

    - 类级缓存：`_companies_cache` / `_years_cache`（实例之间共享）
    - `_TABLE_MAP`：把 6 张表物理名映射为 UI 用的 key（保留现有契约）
    - 内部查询全部走 ReportRepository / StatementRepository
    """

    _companies_cache: Optional[List[Dict[str, str]]] = None
    _years_cache: Optional[List[Dict[str, int]]] = None

    _TABLE_MAP: Dict[str, str] = {
        "consolidated_balance_sheet":        "balance_sheet",
        "parent_company_balance_sheet":      "parent_balance_sheet",
        "consolidated_income_statement":     "income_statement",
        "parent_company_income_statement":   "parent_income_statement",
        "consolidated_cash_flow_statement":  "cash_flow",
        "parent_company_cash_flow_statement": "parent_cash_flow",
    }

    _DICT_STRIP_KEYS = {
        "id", "company_name", "stock_code",
        "report_year", "report_period",
    }

    def __init__(self, db_type: str = "duckdb") -> None:
        from src.db.db_connector import get_db
        self.db_type = db_type
        self.db: DatabaseConnector = get_db(database_type=db_type)
        self._reports = ReportRepository(self.db)
        self._statements = StatementRepository(self.db)

    # ----- 缓存 -----
    @classmethod
    def invalidate_cache(cls) -> None:
        cls._companies_cache = None
        cls._years_cache = None

    # ----- 聚合 -----
    def get_all_companies(self, use_cache: bool = True) -> List[Dict[str, str]]:
        if use_cache and self._companies_cache is not None:
            return self._companies_cache
        try:
            companies = self._reports.list_companies()
            result = [
                {
                    "label": f"{c['company_name']} ({c['stock_code']})",
                    "value": c["stock_code"],
                }
                for c in companies
            ]
            self._companies_cache = result
            return result
        except Exception as e:
            ui_logger.error(f"获取公司列表失败: {e}")
            return self._companies_cache or []

    def get_all_years(self, use_cache: bool = True) -> List[Dict[str, int]]:
        if use_cache and self._years_cache is not None:
            return self._years_cache
        try:
            years = self._reports.list_all_years()
            result = [
                {"label": str(y), "value": y}
                for y in sorted(years, reverse=True)
            ]
            self._years_cache = result
            return result
        except Exception as e:
            ui_logger.error(f"获取年份列表失败: {e}")
            return self._years_cache or []

    # ----- 单报告 -----
    def get_available_periods(self, stock_code: str, year: int) -> List[Dict[str, str]]:
        try:
            return [
                {"label": p, "value": p}
                for p in self._reports.list_available_periods(
                    ReportKey(stock_code=stock_code, year=year)
                )
            ]
        except Exception as e:
            ui_logger.error(f"获取可用期间失败: {e}")
            return []

    def get_report(
        self, stock_code: str, year: int, period: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            return self._reports.get_report(
                ReportKey(stock_code=stock_code, year=year, period=period)
            )
        except Exception as e:
            ui_logger.error(f"获取财务报告失败: {e}")
            return None

    def get_financial_data(
        self, stock_code: str, year: int, period: str,
    ) -> Dict[str, Any]:
        """获取 3 张合并表 + 报告（按 UI 契约返回）。"""
        key = ReportKey(stock_code=stock_code, year=year, period=period)
        result: Dict[str, Any] = {
            "report": None,
            "balance_sheet": None,
            "income_statement": None,
            "cash_flow": None,
        }
        try:
            report = self._reports.get_report(key)
            result["report"] = report
            if not report:
                return result
            stmts = self._statements.get_all_statements(key)
            for table_name, ui_key in self._TABLE_MAP.items():
                d = stmts.get(table_name)
                if d:
                    result[ui_key] = {
                        k: v for k, v in d.items()
                        if k not in self._DICT_STRIP_KEYS
                    }
        except Exception as e:
            ui_logger.error(f"获取财务数据失败: {e}")
        return result