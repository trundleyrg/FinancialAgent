"""通用多序列趋势图模块。

提供 3 个公开 API:
- build_trend_table: 把 {period: {metric: value}} 展平成 DataFrame (不依赖 matplotlib)
- plot_multi_series_trend: 渲染 PNG 趋势图,支持 auto/single/twinx/subplot 4 种布局
- render_trend_chart_and_table: combine — 写图 + 返回表

默认按指标数量自动选择布局:
- 1 指标 -> single
- 2 指标 -> twinx
- 3+ 指标 -> subplot

未来周期股 commodity price 历史可直接复用 plot_multi_series_trend。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Literal

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

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
