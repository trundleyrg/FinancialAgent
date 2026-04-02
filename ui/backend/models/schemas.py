"""
Pydantic Schemas for API
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ReportPeriod(str, Enum):
    Q1 = "Q1"
    H1 = "H1"
    Q3 = "Q3"
    FY = "FY"


class CompanyInfo(BaseModel):
    """公司信息"""
    company_name: str = Field(..., description="公司全称")
    company_short_name: str = Field(default="", description="公司简称")
    stock_code: str = Field(..., description="股票代码")
    report_year: int = Field(..., description="报告年份")
    report_period: str = Field(..., description="报告期间")


class TableInfo(BaseModel):
    """表格信息"""
    table_name: str = Field(..., description="表格名称")
    row_count: int = Field(..., description="行数")
    col_count: int = Field(..., description="列数")
    page_range: str = Field(..., description="页码范围")
    unit: str = Field(default="", description="单位")
    column_units: Dict[int, str] = Field(default_factory=dict, description="每列单位")


class ProcessResult(BaseModel):
    """PDF处理结果"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="结果消息")
    company_info: Optional[CompanyInfo] = Field(None, description="公司信息")
    tables: List[TableInfo] = Field(default_factory=list, description="表格列表")
    saved_ids: Dict[str, int] = Field(default_factory=dict, description="保存的记录ID")
    download_urls: List[str] = Field(default_factory=list, description="下载链接")


class CompanyOption(BaseModel):
    """公司选项"""
    label: str = Field(..., description="显示名称")
    value: str = Field(..., description="股票代码")


class YearOption(BaseModel):
    """年份选项"""
    label: str = Field(..., description="显示年份")
    value: int = Field(..., description="年份值")


class PeriodOption(BaseModel):
    """期间选项"""
    label: str = Field(..., description="显示期间")
    value: str = Field(..., description="期间值")


class QueryOptions(BaseModel):
    """查询选项"""
    companies: List[CompanyOption] = Field(default_factory=list)
    years: List[YearOption] = Field(default_factory=list)


class FinancialReport(BaseModel):
    """财务报告"""
    id: int
    company_name: str
    company_short_name: str
    stock_code: str
    report_year: int
    report_period: str
    source_file: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FinancialMetric(BaseModel):
    """财务指标"""
    id: int
    metric_name: str
    value: float
    unit: Optional[str] = None
    period: Optional[str] = None
    source_context: Optional[str] = None
    page_number: Optional[int] = None

    class Config:
        from_attributes = True


class QueryResult(BaseModel):
    """查询结果"""
    report: Optional[FinancialReport] = None
    metrics: List[FinancialMetric] = Field(default_factory=list)
    balance_sheet: Optional[Dict[str, Any]] = Field(None, description="资产负债表数据")
    income_statement: Optional[Dict[str, Any]] = Field(None, description="利润表数据")
    cash_flow: Optional[Dict[str, Any]] = Field(None, description="现金流量表数据")


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(None, description="详细错误信息")
