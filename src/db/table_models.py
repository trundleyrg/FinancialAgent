"""
表格相关的数据模型定义
"""

from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class TableWithHeader:
    """表格与表头的关联结构"""
    table_data: List[List[str]]  # 表格数据：二维列表
    header_text: str             # 关联的表头文本
    page_start_num: int          # 表格起始页码
    page_end_num: int            # 表格结束页码
    bbox: Tuple[float, float, float, float]  # 表格位置 (x0, y0, x1, y1)
    is_merged: bool = False      # 是否为跨页合并表格