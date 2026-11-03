"""
quarterly_metrics_extractor.py    # 抽取季报/半年报「主要会计数据和财务指标」

季报第二节的 KPI 矩阵有三种版式（实测 600285）：

  Q1  : 项目 | 本报告期 | 上年同期 | 增减变动幅度(%)
        ...表内子表头切到: 本报告期末 | 上年度末 | 增减变动幅度(%)
  Q3  : 项目 | 本报告期 | 变动(%) | 年初至报告期末 | 变动(%)
        本报告期 = 7-9 月**单季**；年初至报告期末 = 1-9 月累计
  H1  : 主要会计数据 | 本报告期（1－6月） | 上年同期 | 增减(%)
        主要财务指标 | 本报告期（1－6月） | 上年同期 | 增减(%)

三季报的 KPI 表**跨页**：首页有表头，次页续表**没有表头**（首行直接是数据行）。

输出：{scope: {字段名: 数值}}，scope ∈ {'CURRENT', 'YTD'}。
"""
import re
from typing import Any, Dict, List, Optional

import fitz

from src.utils.logger import chapter_logger

# 项目名（归一化后）→ 模型字段名
METRIC_FIELD_BY_LABEL: Dict[str, str] = {
    '营业收入': 'operating_revenue',
    '利润总额': 'total_profit',
    '归属于上市公司股东的净利润': 'net_profit_attributable_to_parent',
    '归属于上市公司股东的扣除非经常性损益的净利润': 'net_profit_deducted_non_recurring',
    '经营活动产生的现金流量净额': 'net_cash_from_operations',
    '基本每股收益': 'basic_eps',
    '稀释每股收益': 'diluted_eps',
    '加权平均净资产收益率': 'weighted_roe',
    '总资产': 'total_assets',
    '归属于上市公司股东的所有者权益': 'total_equity_attributable_to_parent',
    '归属于上市公司股东的净资产': 'total_equity_attributable_to_parent',
}

# KPI 表的首列表头取值
KPI_FIRST_CELL_LABELS = ('项目', '主要会计数据', '主要财务指标')

# scope 取值
SCOPE_CURRENT = 'CURRENT'
SCOPE_YTD = 'YTD'

# 「增减变动幅度」列的特征词 —— 含这些词的表头不是数据列
_CHANGE_COLUMN_MARKERS = ('增减', '变动', '同比')


def normalize_metric_label(raw: str) -> str:
    """归一化项目名：去空白 + 去尾部括号注释。

    '基本每股收益（元/股）' → '基本每股收益'
    '归属于上市公司股东的\\n净利润' → '归属于上市公司股东的净利润'
    """
    if not raw:
        return ''
    s = str(raw).replace('\n', '').replace('\r', '')
    s = re.sub(r'\s+', '', s)
    # 去掉尾部的一组括号注释（单位说明）
    s = re.sub(r'[（(][^（()）]*[)）]$', '', s)
    return s.strip()


def parse_metric_value(raw: str) -> Optional[float]:
    """把 KPI 单元格转成 float。'不适用'、'增加0.22 个百分点' 等返回 None。"""
    if raw is None:
        return None
    s = str(raw).replace('\n', '').replace('\r', '').strip()
    if not s or s in ('不适用', '—', '-', '--', '/'):
        return None
    # 去掉千分位逗号
    s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


def _detect_column_roles(header_cells: List[Any]) -> Dict[str, int]:
    """从表头行判定各列的角色。

    返回 {'current': idx, 'ytd': idx, 'period_end': idx} 的子集。
    """
    roles: Dict[str, int] = {}
    for i, cell in enumerate(header_cells):
        if i == 0:
            continue
        h = normalize_metric_label(cell)
        if not h:
            continue
        if any(marker in h for marker in _CHANGE_COLUMN_MARKERS):
            continue  # 增减变动幅度列不是数据列
        if '年初至报告期末' in h:
            roles['ytd'] = i
        elif '本报告期末' in h:
            roles['period_end'] = i
        elif '本报告期' in h:
            roles['current'] = i
    return roles


def _is_sub_header_row(row: List[Any]) -> bool:
    """判断一行是不是表内的子表头（如 '本报告期末 | 上年度末 | ...'）。"""
    if not row:
        return False
    if str(row[0] or '').strip():
        return False
    for cell in row[1:]:
        h = normalize_metric_label(cell)
        if any(k in h for k in ('本报告期', '本报告期末', '上年度末', '年初至报告期末')):
            return True
    return False


class QuarterlyMetricsExtractor:
    """从季报/半年报 PDF 抽取「主要会计数据和财务指标」。"""

    MAX_SCAN_PAGES = 12

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)

    def extract(self) -> Dict[str, Dict[str, Any]]:
        """返回 {'CURRENT': {...}, 'YTD': {...}}。没有的 scope 不出现。"""
        out: Dict[str, Dict[str, Any]] = {}
        roles: Dict[str, int] = {}
        ncols: Optional[int] = None

        for pno in range(min(self.MAX_SCAN_PAGES, len(self.doc))):
            page = self.doc[pno]
            for tab in page.find_tables(strategy='lines_strict'):
                rows = tab.extract()
                if not rows or len(rows) < 2:
                    continue

                first_cell = normalize_metric_label(rows[0][0])
                is_header_table = first_cell in KPI_FIRST_CELL_LABELS

                if is_header_table:
                    roles = _detect_column_roles(rows[0])
                    ncols = len(rows[0])
                    start = 1
                elif ncols is not None and len(rows[0]) == ncols:
                    # 续表（无表头），沿用上一张表的列角色
                    start = 0
                else:
                    continue

                if not roles:
                    continue

                for row in rows[start:]:
                    if _is_sub_header_row(row):
                        # 子表头：重置列角色（如从「本报告期」切到「本报告期末」）
                        roles = _detect_column_roles(row)
                        continue

                    label = normalize_metric_label(row[0])
                    field = METRIC_FIELD_BY_LABEL.get(label)
                    if not field:
                        continue

                    # 'current' / 'period_end' → CURRENT；'ytd' → YTD
                    for role, scope in (('current', SCOPE_CURRENT),
                                        ('period_end', SCOPE_CURRENT),
                                        ('ytd', SCOPE_YTD)):
                        idx = roles.get(role)
                        if idx is None or idx >= len(row):
                            continue
                        value = parse_metric_value(row[idx])
                        if value is None:
                            continue
                        out.setdefault(scope, {}).setdefault(field, value)

        if not out:
            chapter_logger.warning(
                "QuarterlyMetricsExtractor: %s 未找到主要会计数据表", self.pdf_path,
            )
        return out

    def close(self):
        self.doc.close()
