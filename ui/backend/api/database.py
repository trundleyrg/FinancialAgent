"""
数据库查询API路由
"""
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException

from ui.backend.models.schemas import (
    QueryOptions, CompanyOption, YearOption, PeriodOption,
    QueryResult, FinancialReport, FinancialMetric
)
from ui.backend.services.db_service import DatabaseService

router = APIRouter(prefix="/database", tags=["数据库查询"])


@router.get("/options", response_model=QueryOptions)
async def get_query_options(
    db_type: str = Query("duckdb", description="数据库类型")
):
    """
    获取查询选项（公司列表、年份列表）
    """
    service = DatabaseService(db_type=db_type)

    companies = service.get_all_companies()
    years = service.get_all_years()

    return QueryOptions(
        companies=[CompanyOption(**c) for c in companies],
        years=[YearOption(**y) for y in years]
    )


@router.get("/periods", response_model=List[PeriodOption])
async def get_periods(
    stock_code: str = Query(..., description="股票代码"),
    year: int = Query(..., description="报告年份"),
    db_type: str = Query("duckdb", description="数据库类型")
):
    """
    获取指定公司和年份的可用报告周期
    """
    if not stock_code or not year:
        raise HTTPException(status_code=400, detail="股票代码和年份不能为空")

    service = DatabaseService(db_type=db_type)
    periods = service.get_available_periods(stock_code, year)

    if not periods:
        return []

    return [PeriodOption(**p) for p in periods]


@router.get("/report", response_model=Optional[FinancialReport])
async def get_report(
    stock_code: str = Query(..., description="股票代码"),
    year: int = Query(..., description="报告年份"),
    period: str = Query(..., description="报告周期"),
    db_type: str = Query("duckdb", description="数据库类型")
):
    """
    获取财务报告基本信息
    """
    service = DatabaseService(db_type=db_type)
    report = service.get_report(stock_code, year, period)

    if not report:
        raise HTTPException(status_code=404, detail="未找到财务报告")

    return report


@router.get("/data", response_model=QueryResult)
async def get_financial_data(
    stock_code: str = Query(..., description="股票代码"),
    year: int = Query(..., description="报告年份"),
    period: str = Query(..., description="报告周期"),
    db_type: str = Query("duckdb", description="数据库类型")
):
    """
    获取完整财务数据（报告信息 + 三大报表）
    """
    service = DatabaseService(db_type=db_type)
    result = service.get_financial_data(stock_code, year, period)

    if not result.get("report"):
        raise HTTPException(status_code=404, detail="未找到财务数据")

    return QueryResult(**result)


@router.get("/companies", response_model=List[CompanyOption])
async def get_companies(
    db_type: str = Query("duckdb", description="数据库类型")
):
    """
    获取所有公司列表
    """
    service = DatabaseService(db_type=db_type)
    companies = service.get_all_companies()
    return [CompanyOption(**c) for c in companies]


@router.get("/years", response_model=List[YearOption])
async def get_years(
    db_type: str = Query("duckdb", description="数据库类型")
):
    """
    获取所有年份列表
    """
    service = DatabaseService(db_type=db_type)
    years = service.get_all_years()
    return [YearOption(**y) for y in years]
