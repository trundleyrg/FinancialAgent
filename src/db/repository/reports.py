"""ReportRepository — financial_reports 聚合查询。"""
import datetime
from typing import Any, Dict, List

from src.db.db_connector import DatabaseConnector
from src.db.repository.base import BaseRepository
from src.db.repository.keys import ReportKey


class ReportRepository(BaseRepository):
    """财务报告（financial_reports）+ 公司/年份聚合。

    所有方法返回纯 dict 或原始类型；不返回 Peewee Model。
    """

    def get_report(self, key: ReportKey) -> Dict[str, Any] | None:
        return self._query_first("financial_reports", key)

    def list_reports(self, key: ReportKey) -> List[Dict[str, Any]]:
        return self._query("financial_reports", key)

    def list_companies(self) -> List[Dict[str, Any]]:
        return self.connector.get_all_companies()

    def list_company_years(self, stock_code: str) -> List[int]:
        return self.connector.get_company_report_years(stock_code)

    def list_all_years(self) -> List[int]:
        return self.connector.get_all_report_years()

    def list_available_periods(self, key: ReportKey) -> List[str]:
        return [
            r["report_period"]
            for r in self._query("financial_reports", key)
            if r.get("report_period")
        ]

    def check_data_availability(
        self, key: ReportKey, years: int = 10
    ) -> Dict[str, Any]:
        """替换 db_tools.check_company_data_availability。

        必须先 resolve_stock_code — 输入只给 company_name 也能查到。
        """
        stock_code = self.resolve_stock_code(key)
        current_year = datetime.datetime.now().year
        required_years = list(range(current_year - years + 1, current_year + 1))

        available_years = sorted(
            self.connector.get_company_report_years(stock_code)
            if stock_code else []
        )
        missing_years = [y for y in required_years if y not in available_years]
        data_coverage = len(available_years) / years if years > 0 else 0.0

        return {
            "has_data": len(available_years) >= years * 0.5,
            "available_years": available_years,
            "missing_years": sorted(missing_years),
            "data_coverage": round(data_coverage, 2),
            "has_latest_year": current_year in available_years,
            "required_years": required_years,
            "total_available": len(available_years),
        }

    def list_multi_year_reports(
        self, key: ReportKey, start_year: int, end_year: int
    ) -> Dict[int, Dict[str, Any]]:
        """跨年聚合：{year: report_dict}。缺失年份键缺失。"""
        out: Dict[int, Dict[str, Any]] = {}
        for y in range(start_year, end_year + 1):
            r = self.get_report(key.with_year(y))
            if r is not None:
                out[y] = r
        return out
