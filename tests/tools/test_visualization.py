"""Tests for src/tools/visualization.py."""
from __future__ import annotations

from pathlib import Path

import matplotlib
import pytest

from src.tools.visualization import (
    _CJK_FONT_CANDIDATES,
    _apply_cjk_font,
    build_trend_table,
    plot_multi_series_trend,
    render_trend_chart_and_table,
)


def test_apply_cjk_font_sets_unicode_minus_false():
    _apply_cjk_font()
    assert matplotlib.rcParams["axes.unicode_minus"] is False


def test_cjk_font_candidates_includes_fallback():
    assert "DejaVu Sans" in _CJK_FONT_CANDIDATES


def test_build_trend_table_basic():
    series = {
        "2021": {"营收": 38.5e8, "净利": 4.4e8},
        "2022": {"营收": 40.4e8, "净利": 7.8e8},
    }
    df = build_trend_table(series)
    assert list(df.index) == ["2021", "2022"]
    assert list(df.columns) == ["营收", "净利"]
    assert df.loc["2021", "营收"] == 38.5e8
    assert df.loc["2022", "净利"] == 7.8e8


def test_build_trend_table_preserves_metric_order_by_first_seen():
    series = {
        "2021": {"净利": 4.4e8, "营收": 38.5e8},  # 净利 先出现
        "2022": {"营收": 40.4e8, "净利": 7.8e8},
    }
    df = build_trend_table(series)
    assert list(df.columns) == ["净利", "营收"]


def test_build_trend_table_keeps_nan_for_missing():
    series = {
        "2021": {"营收": 38.5e8, "净利": 4.4e8},
        "2022": {"营收": 40.4e8},  # 缺 净利
    }
    df = build_trend_table(series)
    assert df.loc["2022", "净利"] != df.loc["2022", "净利"]  # NaN != NaN
    assert df.loc["2021", "净利"] == 4.4e8


def test_build_trend_table_series_labels_renames_columns():
    series = {"2021": {"营收": 38.5e8, "净利": 4.4e8}}
    df = build_trend_table(series, series_labels={"营收": "营业收入(亿元)"})
    assert "营业收入(亿元)" in df.columns
    assert "营收" not in df.columns


def test_plot_single_metric_returns_path(tmp_path):
    series = {"2021": {"营收": 38.5e8}, "2022": {"营收": 40.4e8}}
    out = tmp_path / "single.png"
    p = plot_multi_series_trend(series, output_path=out)
    assert p == out
    assert out.exists()
    assert out.stat().st_size > 1000


def test_plot_two_metrics_uses_twinx(tmp_path):
    series = {
        "2021": {"营收": 38.5e8, "净利": 4.4e8},
        "2022": {"营收": 40.4e8, "净利": 7.8e8},
    }
    out = tmp_path / "twinx.png"
    plot_multi_series_trend(series, output_path=out)
    assert out.exists()


def test_plot_three_metrics_uses_subplot(tmp_path):
    series = {
        "2021": {"营收": 38.5e8, "净利": 4.4e8, "分红率": 50.0},
        "2022": {"营收": 40.4e8, "净利": 7.8e8, "分红率": 55.0},
        "2023": {"营收": 47.2e8, "净利": 11.5e8, "分红率": 60.0},
    }
    out = tmp_path / "subplot.png"
    plot_multi_series_trend(series, output_path=out)
    assert out.exists()


def test_plot_layout_explicit_subplot_forces_3_panels_even_with_2_metrics(tmp_path):
    series = {
        "2021": {"营收": 38.5e8, "净利": 4.4e8},
        "2022": {"营收": 40.4e8, "净利": 7.8e8},
    }
    out = tmp_path / "force_sub.png"
    plot_multi_series_trend(series, output_path=out, layout="subplot")
    assert out.exists()


def test_plot_empty_series_raises():
    with pytest.raises(ValueError, match="empty"):
        plot_multi_series_trend({}, output_path=Path("/tmp/x.png"))


def test_plot_creates_parent_dirs(tmp_path):
    series = {"2021": {"营收": 38.5e8}, "2022": {"营收": 40.4e8}}
    out = tmp_path / "deep" / "dir" / "x.png"
    plot_multi_series_trend(series, output_path=out)
    assert out.exists()


def test_plot_with_title(tmp_path):
    """1 指标 + title:触发 ax.set_title(single)分支。"""
    series = {"2021": {"营收": 38.5e8}, "2022": {"营收": 40.4e8}}
    out = tmp_path / "titled.png"
    plot_multi_series_trend(series, output_path=out, title="测试标题")
    assert out.exists()


def test_plot_layout_subplot_with_single_metric(tmp_path):
    """1 指标 + layout=subplot:触发 n==1 内层 list 化 axes 分支。"""
    series = {"2021": {"营收": 38.5e8}, "2022": {"营收": 40.4e8}}
    out = tmp_path / "subplot_one.png"
    plot_multi_series_trend(series, output_path=out, layout="subplot")
    assert out.exists()


def test_combine_returns_path_and_dataframe(tmp_path):
    series = {
        "2021": {"营收": 38.5e8, "净利": 4.4e8},
        "2022": {"营收": 40.4e8, "净利": 7.8e8},
    }
    out = tmp_path / "combo.png"
    p, df = render_trend_chart_and_table(series, output_path=out)
    assert p == out
    assert out.exists()
    assert list(df.index) == ["2021", "2022"]
    assert df.loc["2021", "营收"] == 38.5e8
    assert df.loc["2022", "净利"] == 7.8e8


def test_combine_table_and_chart_share_same_values(tmp_path):
    """图与表共享同一 series 口径:表里的数值就是图里画的。"""
    series = {
        "2021": {"营收": 1.0, "净利": 0.5},
        "2022": {"营收": 2.0, "净利": 1.0},
    }
    out = tmp_path / "shared.png"
    _, df = render_trend_chart_and_table(series, output_path=out)
    # 表中数据应与 series 完全一致(无变换)
    assert df.loc["2021", "营收"] == series["2021"]["营收"]
    assert df.loc["2022", "净利"] == series["2022"]["净利"]
