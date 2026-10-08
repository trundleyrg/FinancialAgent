"""Tests for src/tools/visualization.py."""
from __future__ import annotations

import matplotlib

from src.tools.visualization import _apply_cjk_font, _CJK_FONT_CANDIDATES


def test_apply_cjk_font_sets_unicode_minus_false():
    _apply_cjk_font()
    assert matplotlib.rcParams["axes.unicode_minus"] is False


def test_cjk_font_candidates_includes_fallback():
    assert "DejaVu Sans" in _CJK_FONT_CANDIDATES
