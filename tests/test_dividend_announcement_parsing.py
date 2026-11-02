"""分红实施公告的解析与归年测试。

## 背景(实测 bug)

``capital_change_events`` 的分红数据有两个叠加缺陷,导致东阿阿胶 2023-2025
三年的分红率算错(官方 96.52% / 97.26%,DB 算成 98.0% / 98.8%):

### Bug 1 — 归年用公告发布时间,而非标题里的分配年度

``query_dividend_announcements`` 用 ``ts.year - 1 == y`` 归年:

    「2024年半年度权益分派实施公告」(2024-08 发布) → 归 2023  ✗
    「2024年年度权益分派实施公告」  (2025-06 发布) → 归 2024  ✓

半年度公告落在前一年,又因 dedup 键是
``(stock_code, report_year, event_type='cash_dividend')``,
API 按时间倒序返回 → **半年度的先入库,年度的被跳过**,
于是 2023/2024/2025 三年 DB 里存的都是半年度数值。

### Bug 2 — 分子口径双重混用

公告的「每10股派息」是按**参与分配股数(剔除回购股)**折算的:

    每10股派 12.700919 元 = 现金分红总额 817,206,589.66 ÷ 643,423,163 × 10
                                              ↑ 剔除回购股 553,661 股后的基数

但 dividend skill 用「每10股派息 × share_structure 的年末总股本」反推,
乘数用的是**含回购股的总股本** 643,976,824 —— 两个口径混用,
分子系统性偏大 1.56%。

**修复**:分子改用公告直接披露的「现金分红总额」。

本测试用**真实公告文本片段**(从 data/000423/dividend_announcements/ 提取)
做输入,保证正则面对的是真实格式而非理想化 mock。
"""
import re

import pytest

from src.tools.download_cninfo_reports import (
    _extract_dividend_from_pdf,
    _extract_dividend_total,
    _parse_dividend_announcement_title,
)


# ──────────────────────────────────────────────────────────────────────────────
# 真实公告文本片段
# ──────────────────────────────────────────────────────────────────────────────

# 2024年度分派(1223684326.PDF):总额句式 1
TEXT_2024_ANNUAL = """
本次权益分派方案为：以公司总股本643,976,824股剔除已回购股份1,512,400股后
参与利润分配的总股数642,464,424股为基数，向全体股东每10股派发现金红利
12.729896元（含税），即（现金红利派发总额÷参与利润分配的总股数）×10=
817,850,566.48元÷（643,976,824股-1,512,400股）×10。
"""

# 2024半年度分派(1221123529.PDF):同上句式
TEXT_2024_INTERIM = """
2024年半年度权益分派方案为：以公司总股本643,976,824股剔除已回购股份
1,512,400股后参与利润分配的总股数642,464,424股为基数，向全体股东每10股
派发现金红利11.466930元（含税），即（现金红利派发总额÷参与利润分配的总股数）
×10=736,709,486.66元÷（643,976,824股-1,512,400股）×10。
"""

# 2021年度分派(1214310263.PDF):总额句式 2
TEXT_2021_ANNUAL = """
2021年度权益分派方案为：以2021年末总股本654,021,537股为基数，向全体股东
每10股派发现金6.5元（含税），现金分红总额为425,113,999.05元。
"""

# 2020年度分派(1210748404.PDF):总额句式 2
TEXT_2020_ANNUAL = """
2020年度利润分配预案为：以2020年末总股本654,021,537股为基数，向全体股东
每10股派发现金3元（含税），现金分红总额为196,206,461.10元。
"""

# 2017年度分派(1205243129.PDF):总额句式 3
TEXT_2017_ANNUAL = """
分配、不转增，即以2017年末总股本654,021,537股为基数，向全体股东每10股
派发现金9元（含税），合计派发现金总额为588,619,383.30元。
"""

# 2025半年度分派(1224578894.PDF):总额句式 1 + 句式 2 同时出现
TEXT_2025_INTERIM = """
2025年半年度利润分配方案为：以2025年6月30日总股本643,976,824股为基数，
向全体股东每10股派发现金12.69元（含税），现金分红总额为817,206,589.66元。
2．2025年半年度利润分配方案为：以公司总股本643,976,824股剔除已回购股份
553,661股后参与利润分配的总股数643,423,163股为基数，向全体股东每10股
派发现金红利12.700919元（含税），即（现金红利派发总额÷参与利润分配的总股数）
×10=817,206,589.66元÷（643,976,824股-553,661股）×10。
"""


# ──────────────────────────────────────────────────────────────────────────────
# _extract_dividend_total — 从公告提取「现金分红总额」
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        (TEXT_2021_ANNUAL, 425_113_999.05),
        (TEXT_2020_ANNUAL, 196_206_461.10),
        (TEXT_2017_ANNUAL, 588_619_383.30),
        (TEXT_2025_INTERIM, 817_206_589.66),
    ],
)
def test_extract_dividend_total_from_text(text, expected):
    """从公告文本提取「现金分红总额」(元)。"""
    assert _extract_dividend_total(text) == pytest.approx(expected, rel=1e-9)


def test_extract_dividend_total_from_multiplication_formula():
    """句式「…×10=817,850,566.48元÷…」也能提取。"""
    total = _extract_dividend_total(TEXT_2024_ANNUAL)
    assert total == pytest.approx(817_850_566.48, rel=1e-9)


def test_extract_dividend_total_returns_none_when_absent():
    """没有总额表述 → None(不臆测)。"""
    assert _extract_dividend_total("每10股派发现金红利3元（含税）") is None


def test_extract_dividend_total_prefers_dedicated_statement():
    """「现金分红总额为 X」与「×10=X」同时出现时,取「现金分红总额为」那个。"""
    text = "现金分红总额为817,206,589.66元。另一个式子×10=999,999,999.99元。"
    assert _extract_dividend_total(text) == pytest.approx(817_206_589.66)


# ──────────────────────────────────────────────────────────────────────────────
# _parse_dividend_announcement_title — 从标题解析分配年度与性质
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "title,year,kind",
    [
        ("东阿阿胶2024年年度权益分派实施公告", 2024, "annual"),
        ("东阿阿胶2024年半年度权益分派实施公告", 2024, "interim"),
        ("东阿阿胶2023年年度权益分派实施公告", 2023, "annual"),
        ("东阿阿胶:2025年半年度权益分派实施公告", 2025, "interim"),
        ("2022年年度权益分派实施公告", 2022, "annual"),
        ("2021 年年度权益分派实施公告", 2021, "annual"),
    ],
)
def test_parse_announcement_title(title, year, kind):
    """标题里的年度 = 分配年度(不是发布年份 - 1)。"""
    got_year, got_kind = _parse_dividend_announcement_title(title)
    assert got_year == year
    assert got_kind == kind


def test_parse_announcement_title_defaults_to_annual():
    """标题里没有「半年度」→ 年度分配。"""
    year, kind = _parse_dividend_announcement_title("某公司2020年权益分派实施公告")
    assert year == 2020
    assert kind == "annual"


def test_parse_announcement_title_returns_none_without_year():
    year, kind = _parse_dividend_announcement_title("无关标题")
    assert year is None
    assert kind == "annual"


# ──────────────────────────────────────────────────────────────────────────────
# 端到端:公告 PDF → 正确的分子
# ──────────────────────────────────────────────────────────────────────────────


def test_extract_from_pdf_reads_total_dividend(tmp_path):
    """从 PDF 提取时,分子用「现金分红总额」而非反推值。

    2024 年度公告:总额 817,850,566.48;若用「12.729896/10 × 643,976,824」
    反推会得到 819,867,300 —— 偏大 0.25%。
    """
    pdf = tmp_path / "ann.pdf"
    _write_minimal_pdf(pdf, TEXT_2024_ANNUAL)
    out = _extract_dividend_from_pdf(str(pdf))
    assert out["cash_dividend_total"] == pytest.approx(817_850_566.48, rel=1e-9)


def _write_minimal_pdf(path, text):
    """用 fitz 写一个只含给定文本的最小 PDF。"""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    # 中文需要 CJK 字体;用 helv 会丢字。改用 insert_textbox 配合
    # PyMuPDF 自带的 "china-s" 字体。
    page.insert_textbox(
        fitz.Rect(20, 20, 580, 780),
        text,
        fontsize=9,
        fontname="china-s",
    )
    doc.save(str(path))
    doc.close()


# ──────────────────────────────────────────────────────────────────────────────
# 分红率计算:优先用现金分红总额
# ──────────────────────────────────────────────────────────────────────────────


def test_sum_dividend_prefers_total_over_reconstruction():
    """有 cash_dividend_total 时用它,不再用「每10股 × 股本」反推。"""
    from src.skills.dividend.tools import _sum_dividend_from_events

    events = [{
        "event_type": "cash_dividend",
        "cash_per_10_shares": 12.729896,
        "cash_dividend_total": 817_850_566.48,
        "total_shares": 643_976_824,
    }]
    total = _sum_dividend_from_events(events, 643_976_824)
    # 用总额,不是 12.729896/10 × 643,976,824 = 819,867,300
    assert total == pytest.approx(817_850_566.48, rel=1e-9)


def test_sum_dividend_falls_back_to_reconstruction():
    """无 cash_dividend_total(老数据)→ 回退到「每10股 × 股本」反推。"""
    from src.skills.dividend.tools import _sum_dividend_from_events

    events = [{
        "event_type": "cash_dividend",
        "cash_per_10_shares": 3.0,
        "total_shares": 654_021_537,
    }]
    total = _sum_dividend_from_events(events, 654_021_537)
    assert total == pytest.approx(3.0 / 10 * 654_021_537, rel=1e-9)


def test_sum_dividend_sums_annual_and_interim():
    """年度 + 半年度相加(用户选定口径)。"""
    from src.skills.dividend.tools import _sum_dividend_from_events

    events = [
        {"event_type": "cash_dividend", "cash_per_10_shares": 12.729896,
         "cash_dividend_total": 817_850_566.48, "dividend_kind": "annual"},
        {"event_type": "cash_dividend", "cash_per_10_shares": 11.466930,
         "cash_dividend_total": 736_709_486.66, "dividend_kind": "interim"},
    ]
    total = _sum_dividend_from_events(events, 643_976_824)
    assert total == pytest.approx(817_850_566.48 + 736_709_486.66, rel=1e-9)


def test_extract_dividend_total_from_per_share_wording():
    """句式「共计派发现金红利 623,827,034.60 元」(600285 每股派现表述)。"""
    text = (
        "本次利润分配以方案实施前的公司总股本567,115,486股为基数，"
        "每股派发现金红利1.10元（含税），共计派发现金红利623,827,034.60元"
    )
    assert _extract_dividend_total(text) == pytest.approx(623_827_034.60, rel=1e-9)
