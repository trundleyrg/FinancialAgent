"""
定义 LangGraph 的 State 结构 (TypedDict)
"""

from typing import Annotated, List, TypedDict, Optional
from operator import add

class FinancialState(TypedDict):
    """
    定义 FinancialAgent 的状态结构
    """
    # 当前正在处理的 PDF 路径
    pdf_path: str
    
    # 提取出的原始 Markdown 内容（中间产物）
    raw_markdown: Optional[str]
    
    # 结构化后的财务数据（例如提取出的资产负债表 JSON）
    structured_data: Annotated[List[dict], add]
    
    # 任务执行状态：pending, processing, completed, error
    status: str
    
    # 错误日志，用于错误处理分支
    error_msg: Optional[str]
    
    # 最终保存到数据库的记录 ID
    record_id: Optional[int]
