"""通用多序列趋势图模块。

模块初始化时设置 matplotlib 的 CJK 字体 fallback 链与负号修复;
3 个公开 API(build_trend_table / plot_multi_series_trend /
render_trend_chart_and_table)由后续任务逐个追加到本文件。
"""
from __future__ import annotations

import logging
from typing import Callable

import matplotlib
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


def build_trend_table(
    series: dict[str, dict[str, float]],
    *,
    series_labels: dict[str, str] | None = None,
    value_formatter: Callable[[float], str] | None = None,
) -> pd.DataFrame:
    """把 {period: {metric: value}} 展平成宽表。

    Args:
        series: 与 plot_multi_series_trend 完全相同的入参形状。
        series_labels: 把内部 metric 名映射到显示名;仅改列名,不改值。
            例: {"营收": "营业收入(亿元)"} → 列名变成 "营业收入(亿元)"
        value_formatter: 把 float 格式化成字符串;默认不格式化,保留 float。
            例: lambda v: f"{v/1e8:.2f}亿" → 整列变成字符串

    Returns:
        DataFrame,index=period(按字典序),columns=metric
        (列顺序按各 period 首次出现顺序),缺失值保持 NaN。
    """
    if not series:
        raise ValueError("series is empty")

    # 按字典序排 period,保证 2020 < 2021 < 2022
    sorted_periods = sorted(series.keys())
    # 列顺序:按各 period 首次出现的 metric 顺序
    seen: list[str] = []
    for period in sorted_periods:
        for metric in series[period].keys():
            if metric not in seen:
                seen.append(metric)

    data: dict[str, list[float | None]] = {
        metric: [series[p].get(metric) for p in sorted_periods]
        for metric in seen
    }
    df = pd.DataFrame(data, index=sorted_periods)
    df.index.name = "period"

    if series_labels:
        df = df.rename(columns=series_labels)
    if value_formatter is not None:
        df = df.map(value_formatter)
    return df
