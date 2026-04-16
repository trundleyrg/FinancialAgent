"""
数据库查询API路由
"""
from typing import List, Optional, Annotated
from fastapi import APIRouter, Query, HTTPException, Depends
from functools import lru_cache

from ui.backend.models.schemas import (
    QueryOptions, CompanyOption, YearOption, PeriodOption,
    QueryResult, FinancialReport, FinancialMetric
)
from ui.backend.services.db_service import DatabaseService

router = APIRouter(prefix="/database", tags=["数据库查询"])


def get_db_service(
    db_type: Annotated[str, Query(description="数据库类型")] = "duckdb"
) -> DatabaseService:
    """数据库服务依赖注入（单例模式）"""
    return DatabaseService(db_type=db_type)


@router.get("/options", response_model=QueryOptions)
async def get_query_options(
    service: Annotated[DatabaseService, Depends(get_db_service)]
):
    """
    获取查询选项（公司列表、年份列表）

    优化：使用缓存避免重复查询数据库
    """
    companies = service.get_all_companies(use_cache=True)
    years = service.get_all_years(use_cache=True)

    return QueryOptions(
        companies=[CompanyOption(**c) for c in companies],
        years=[YearOption(**y) for y in years]
    )


@router.get("/periods", response_model=List[PeriodOption])
async def get_periods(
    stock_code: Annotated[str, Query(description="股票代码")],
    year: Annotated[int, Query(description="报告年份")],
    service: Annotated[DatabaseService, Depends(get_db_service)]
):
    """
    获取指定公司和年份的可用报告周期
    """
    if not stock_code or not year:
        raise HTTPException(status_code=400, detail="股票代码和年份不能为空")

    periods = service.get_available_periods(stock_code, year)

    if not periods:
        return []

    return [PeriodOption(**p) for p in periods]


@router.get("/report", response_model=Optional[FinancialReport])
async def get_report(
    stock_code: Annotated[str, Query(description="股票代码")],
    year: Annotated[int, Query(description="报告年份")],
    period: Annotated[str, Query(description="报告周期")],
    service: Annotated[DatabaseService, Depends(get_db_service)]
):
    """
    获取财务报告基本信息
    """
    report = service.get_report(stock_code, year, period)

    if not report:
        raise HTTPException(status_code=404, detail="未找到财务报告")

    return report


@router.get("/data", response_model=QueryResult)
async def get_financial_data(
    stock_code: Annotated[str, Query(description="股票代码")],
    year: Annotated[int, Query(description="报告年份")],
    period: Annotated[str, Query(description="报告周期")],
    service: Annotated[DatabaseService, Depends(get_db_service)]
):
    """
    获取完整财务数据（报告信息 + 三大报表）
    """
    result = service.get_financial_data(stock_code, year, period)

    if not result.get("report"):
        raise HTTPException(status_code=404, detail="未找到财务数据")

    return QueryResult(**result)


@router.get("/companies", response_model=List[CompanyOption])
async def get_companies(
    service: Annotated[DatabaseService, Depends(get_db_service)]
):
    """
    获取所有公司列表

    优化：使用缓存
    """
    companies = service.get_all_companies(use_cache=True)
    return [CompanyOption(**c) for c in companies]


@router.get("/years", response_model=List[YearOption])
async def get_years(
    service: Annotated[DatabaseService, Depends(get_db_service)]
):
    """
    获取所有年份列表

    优化：复用公司缓存数据，减少数据库查询
    """
    years = service.get_all_years(use_cache=True)
    return [YearOption(**y) for y in years]


@router.post("/cache/invalidate")
async def invalidate_cache():
    """
    手动清除数据库查询缓存

    在数据更新后调用此接口以刷新缓存
    """
    DatabaseService.invalidate_cache()
    return {"message": "缓存已清除"}
