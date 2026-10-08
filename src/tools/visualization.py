"""通用多序列趋势图模块。

模块初始化时设置 matplotlib 的 CJK 字体 fallback 链与负号修复;
3 个公开 API(build_trend_table / plot_multi_series_trend /
render_trend_chart_and_table)由后续任务逐个追加到本文件。
"""
from __future__ import annotations

import logging

import matplotlib

logger = logging.getLogger("Tools.Visualization")

# 中文字体兼容:按顺序 fallback,第一个在系统中存在的字体被采用。
# axes.unicode_minus = False 解决负号方块问题。
_CJK_FONT_CANDIDATES = [
    "PingFang SC", "Hiragino Sans GB", "Heiti SC",
    "WenQuanYi Zen Hei", "Noto Sans CJK SC",
    "Source Han Sans CN", "Microsoft YaHei", "SimHei",
    "DejaVu Sans",  # 兜底
]


def _apply_cjk_font() -> None:
    """设置 matplotlib 全局中文字体与负号。"""
    matplotlib.rcParams["font.sans-serif"] = list(_CJK_FONT_CANDIDATES)
    matplotlib.rcParams["axes.unicode_minus"] = False


# 模块导入时立即生效
_apply_cjk_font()
