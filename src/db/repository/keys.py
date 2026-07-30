"""ReportKey — 所有读查询的统一寻址对象。"""
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ReportKey:
    """定位一份财务报告（或一个聚合查询）。

    至少需要 stock_code 或 company_name 之一。year/period 可选；
    缺则查所有年份/期间。
    """

    stock_code: Optional[str] = None
    company_name: Optional[str] = None
    year: Optional[int] = None
    period: Optional[str] = None  # "Q1" | "H1" | "Q3" | "FY"

    def __post_init__(self) -> None:
        if not (self.stock_code or self.company_name):
            raise ValueError("ReportKey requires stock_code or company_name")

    def to_filter(self) -> Dict[str, Any]:
        """序列化为 db_connector.filter_records 的 kwargs。
        stock_code 优先（financial_reports 在 stock_code 上查询更稳）。"""
        f: Dict[str, Any] = {}
        if self.stock_code:
            f["stock_code"] = self.stock_code
        elif self.company_name:
            f["company_name"] = self.company_name
        if self.year is not None:
            f["report_year"] = self.year
        if self.period:
            f["report_period"] = self.period
        return f

    def with_year(self, year: int) -> "ReportKey":
        return replace(self, year=year)
