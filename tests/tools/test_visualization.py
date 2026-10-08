"""Tests for src/tools/visualization.py."""
from __future__ import annotations

import matplotlib

from src.tools.visualization import _apply_cjk_font, _CJK_FONT_CANDIDATES


def test_apply_cjk_font_sets_unicode_minus_false():
    _apply_cjk_font()
    assert matplotlib.rcParams["axes.unicode_minus"] is False


def test_cjk_font_candidates_includes_fallback():
    assert "DejaVu Sans" in _CJK_FONT_CANDIDATES


from src.tools.visualization import build_trend_table


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
