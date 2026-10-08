"""通用多序列趋势图模块。

模块初始化时设置 matplotlib 的 CJK 字体 fallback 链与负号修复;
3 个公开 API(build_trend_table / plot_multi_series_trend /
render_trend_chart_and_table)由后续任务逐个追加到本文件。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Literal

import matplotlib
import matplotlib.figure
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


def _resolve_layout(
    n_metrics: int,
    layout: Literal["auto", "single", "twinx", "subplot"],
) -> str:
    """根据指标数 + 显式 layout 决定最终布局。"""
    if layout != "auto":
        return layout
    if n_metrics == 1:
        return "single"
    if n_metrics == 2:
        return "twinx"
    return "subplot"


def _all_metrics(series: dict[str, dict[str, float]]) -> list[str]:
    """按各 period 首次出现顺序返回所有 metric。"""
    seen: list[str] = []
    for period in sorted(series.keys()):
        for metric in series[period].keys():
            if metric not in seen:
                seen.append(metric)
    return seen


def _draw_single(
    series: dict[str, dict[str, float]],
    metrics: list[str],
    *,
    title: str | None,
    x_label: str,
    y_label: str | None,
    series_labels: dict[str, str] | None,
    figsize: tuple[float, float],
) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=figsize)
    periods = sorted(series.keys())
    metric = metrics[0]
    values = [series[p].get(metric) for p in periods]
    ax.plot(periods, values, marker="o")
    display_metric = (series_labels or {}).get(metric, metric)
    ax.set_ylabel(y_label if y_label else display_metric)
    ax.set_xlabel(x_label)
    if title:
        ax.set_title(title)
    ax.grid(True, alpha=0.3)
    return fig


def _draw_twinx(
    series: dict[str, dict[str, float]],
    metrics: list[str],
    *,
    title: str | None,
    x_label: str,
    series_labels: dict[str, str] | None,
    figsize: tuple[float, float],
) -> matplotlib.figure.Figure:
    fig, ax_left = plt.subplots(figsize=figsize)
    ax_right = ax_left.twinx()
    periods = sorted(series.keys())

    left_metric = metrics[0]
    left_values = [series[p].get(left_metric) for p in periods]
    ax_left.plot(periods, left_values, marker="o", color="tab:blue",
                 label=(series_labels or {}).get(left_metric, left_metric))
    ax_left.set_ylabel((series_labels or {}).get(left_metric, left_metric),
                       color="tab:blue")
    ax_left.tick_params(axis="y", labelcolor="tab:blue")

    right_metric = metrics[1]
    right_values = [series[p].get(right_metric) for p in periods]
    ax_right.plot(periods, right_values, marker="s", linestyle="--",
                  color="tab:orange",
                  label=(series_labels or {}).get(right_metric, right_metric))
    ax_right.set_ylabel((series_labels or {}).get(right_metric, right_metric),
                        color="tab:orange")
    ax_right.tick_params(axis="y", labelcolor="tab:orange")

    ax_left.set_xlabel(x_label)
    if title:
        ax_left.set_title(title)
    ax_left.grid(True, alpha=0.3)
    return fig


def _draw_subplot(
    series: dict[str, dict[str, float]],
    metrics: list[str],
    *,
    title: str | None,
    x_label: str,
    series_labels: dict[str, str] | None,
    figsize_per_panel: tuple[float, float],
) -> matplotlib.figure.Figure:
    n = len(metrics)
    fig, axes = plt.subplots(
        n, 1,
        figsize=(figsize_per_panel[0], figsize_per_panel[1] * n),
        sharex=True,
    )
    if n == 1:
        axes = [axes]
    periods = sorted(series.keys())
    for ax, metric in zip(axes, metrics, strict=True):
        values = [series[p].get(metric) for p in periods]
        ax.plot(periods, values, marker="o")
        display_metric = (series_labels or {}).get(metric, metric)
        ax.set_ylabel(display_metric)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel(x_label)
    if title:
        fig.suptitle(title)
    return fig


def plot_multi_series_trend(
    series: dict[str, dict[str, float]],
    *,
    x_label: str = "年份",
    y_label: str | None = None,
    series_labels: dict[str, str] | None = None,
    title: str | None = None,
    output_path: str | Path,
    figsize: tuple[float, float] | None = None,
    value_formatter: Callable[[float], str] | None = None,  # noqa: ARG001
    layout: Literal["auto", "single", "twinx", "subplot"] = "auto",
) -> Path:
    """把 {period: {metric: value}} 渲染成趋势图 PNG。

    Args:
        series: 嵌套 dict,外层 key=period(如 "2021"),内层 key=metric(如 "营收")。
        x_label: X 轴标签,默认 "年份"。
        y_label: Y 轴标签(仅 single 布局生效);其它布局每图自带 Y 轴。
        series_labels: 把内部 metric 名映射到显示名;仅改 label,不改值。
        title: 整图标题(single/twinx 用 ax.set_title,subplot 用 fig.suptitle)。
        output_path: 写入 PNG 的路径;父目录不存在会自动创建。
        figsize: (width, height) 英寸;subplot 模式按面板数纵向叠加。
        value_formatter: 预留参数(当前未挂到画图路径上)。
        layout: "auto"(1→single / 2→twinx / 3+→subplot)或显式覆盖。

    Returns:
        Path: 写入 PNG 的路径(与 output_path 相同对象)。
    """
    if not series:
        raise ValueError("series is empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = _all_metrics(series)
    resolved = _resolve_layout(len(metrics), layout)
    fig_size: tuple[float, float] = figsize if figsize else (10.0, 6.0)

    if resolved == "single":
        fig = _draw_single(
            series, metrics, title=title, x_label=x_label, y_label=y_label,
            series_labels=series_labels, figsize=fig_size,
        )
    elif resolved == "twinx":
        fig = _draw_twinx(
            series, metrics, title=title, x_label=x_label,
            series_labels=series_labels, figsize=fig_size,
        )
    else:  # subplot
        fig = _draw_subplot(
            series, metrics, title=title, x_label=x_label,
            series_labels=series_labels, figsize_per_panel=fig_size,
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_trend_chart_and_table(
    series: dict[str, dict[str, float]],
    *,
    output_path: str | Path,
    title: str | None = None,
    x_label: str = "年份",
    y_label: str | None = None,
    series_labels: dict[str, str] | None = None,
    value_formatter: Callable[[float], str] | None = None,
    figsize: tuple[float, float] | None = None,
    layout: Literal["auto", "single", "twinx", "subplot"] = "auto",
) -> tuple[Path, pd.DataFrame]:
    """画图 + 构造表格;表格与图共享同一份 series,保证口径一致。

    Args:
        series: 嵌套 dict,外层 key=period,内层 key=metric。
        output_path: PNG 写入路径(与 plot_multi_series_trend 行为一致)。
        title: 整图标题(透传给 plot)。
        x_label: X 轴标签。
        y_label: Y 轴标签(透传,仅 single 布局生效)。
        series_labels: metric 名 -> 显示名映射,同时改图的 label 和表的列名。
        value_formatter: 把 float 格式化成字符串(同时作用于图与表);
            None 保持原值。
        figsize: (width, height) 英寸。
        layout: "auto" 或显式 single/twinx/subplot。

    Returns:
        (chart_path, table) 二元组:
        - chart_path: 写入的 PNG 路径(Path)。
        - table: build_trend_table() 的结果,index=period(按字典序),
                 columns=metric(按首次出现顺序)。
    """
    chart_path = plot_multi_series_trend(
        series,
        x_label=x_label,
        y_label=y_label,
        series_labels=series_labels,
        title=title,
        output_path=output_path,
        figsize=figsize,
        value_formatter=value_formatter,
        layout=layout,
    )
    table = build_trend_table(
        series,
        series_labels=series_labels,
        value_formatter=value_formatter,
    )
    return chart_path, table
