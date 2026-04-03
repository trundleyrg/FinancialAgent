"""
定义 LangGraph 的 State 结构 (TypedDict)
"""

from typing import Annotated, List, TypedDict, Optional, Dict, Any
from operator import add


class FinancialState(TypedDict):
    """
    定义 FinancialAgent 的状态结构
    """
    # ========== PDF 处理相关 ==========
    # 当前正在处理的 PDF 路径
    pdf_path: str

    # 提取出的原始 Markdown 内容（中间产物）
    raw_markdown: Optional[str]

    # 结构化后的财务数据（例如提取出的资产负债表 JSON）
    structured_data: Annotated[List[dict], add]

    # ========== 公司信息（从 PDF 提取） ==========
    company_name: Optional[str]           # 公司全名
    company_short_name: Optional[str]     # 公司简称
    stock_code: Optional[str]             # 股票代码
    report_year: Optional[int]            # 报告年份
    report_period: Optional[str]          # 报告周期 (Q1/H1/Q3/FY)

    # ========== 数据可用性检查结果 ==========
    data_availability: Optional[Dict[str, Any]]  # 数据库中近十年数据可用性

    # ========== 分析结果（由各 Agent 填充） ==========
    # 周期股分析结果
    cyclical_analysis: Optional[Dict[str, Any]]

    # 基本面分析结果
    fundamental_analysis: Optional[Dict[str, Any]]

    # 总结结果
    summary: Optional[Dict[str, Any]]

    # ========== 任务状态 ==========
    # 任务执行状态：pending, processing, completed, error
    status: str

    # 错误日志，用于错误处理分支
    error_msg: Optional[str]

    # 最终保存到数据库的记录 ID
    record_id: Optional[int]
