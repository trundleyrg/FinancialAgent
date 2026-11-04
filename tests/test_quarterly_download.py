"""下载器的季报/半年报支持：category 映射、标题校验、文件名约定。"""

import pytest

from src.tools.download_cninfo_reports import CNInfoReportDownloader


@pytest.fixture
def dl():
    return CNInfoReportDownloader()


# ── category 映射 ────────────────────────────────────────────────


def test_report_category_map_covers_all_periods(dl):
    assert dl.REPORT_CATEGORY == {
        "FY": "category_ndbg_szsh",
        "Q1": "category_yjdbg_szsh",
        "H1": "category_bndbg_szsh",
        "Q3": "category_sjdbg_szsh",
    }


def test_search_year_offset_annual_is_next_year(dl):
    assert dl.REPORT_SEARCH_YEAR_OFFSET["FY"] == (1, 2)


def test_search_year_offset_quarterly_is_same_year(dl):
    """季报/半年报在报告当年发布（Q1→4月、H1→8月、Q3→10月）。"""
    assert dl.REPORT_SEARCH_YEAR_OFFSET["Q1"] == (0,)
    assert dl.REPORT_SEARCH_YEAR_OFFSET["H1"] == (0,)
    assert dl.REPORT_SEARCH_YEAR_OFFSET["Q3"] == (0,)


# ── 标题校验 ────────────────────────────────────────────────────


def test_is_valid_annual_report(dl):
    assert dl._is_valid_report("羚锐制药2024年年度报告", 2024, "FY") is True


def test_is_valid_q1_report(dl):
    assert dl._is_valid_report("羚锐制药2025年第一季度报告", 2025, "Q1") is True


def test_is_valid_h1_report(dl):
    assert dl._is_valid_report("羚锐制药2025年半年度报告", 2025, "H1") is True


def test_is_valid_q3_report(dl):
    assert dl._is_valid_report("羚锐制药2025年第三季度报告", 2025, "Q3") is True


@pytest.mark.parametrize(
    "title",
    [
        "羚锐制药2025年第一季度报告摘要",
        "羚锐制药2025年第一季度报告（英文版）",
        "羚锐制药2025年第一季度报告已取消",
    ],
)
def test_is_valid_rejects_non_final_versions(dl, title):
    assert dl._is_valid_report(title, 2025, "Q1") is False


def test_is_valid_rejects_wrong_period_kind(dl):
    """Q1 任务不该匹配到半年报。"""
    assert dl._is_valid_report("羚锐制药2025年半年度报告", 2025, "Q1") is False


def test_is_valid_annual_rejects_interim_title(dl):
    """ "半年度报告" 含 "年度报告" —— 查年报时必须排除半年度标题。"""
    assert dl._is_valid_report("羚锐制药2025年半年度报告", 2025, "FY") is False
    assert dl._is_valid_report("羚锐制药2025年第三季度报告", 2025, "FY") is False
    assert dl._is_valid_report("羚锐制药2025年第一季度报告", 2025, "FY") is False


def test_is_valid_h1_rejects_quarterly_titles(dl):
    assert dl._is_valid_report("羚锐制药2025年第一季度报告", 2025, "H1") is False
    assert dl._is_valid_report("羚锐制药2025年第三季度报告", 2025, "H1") is False


def test_is_valid_rejects_wrong_year(dl):
    assert dl._is_valid_report("羚锐制药2024年年度报告", 2025, "FY") is False


def test_is_valid_rejects_unknown_period(dl):
    assert dl._is_valid_report("羚锐制药2025年年度报告", 2025, "Q9") is False


# ── 文件名约定 ──────────────────────────────────────────────────


def test_query_annual_stops_searching_after_first_match(monkeypatch, dl):
    """年报要搜 year+1 / year+2 两个窗口 —— 找到一份后必须停,
    否则同一年度会返回两条公告、重复下载。"""
    seen_windows = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "announcements": [
                    {
                        "announcementTitle": "羚锐制药2024年年度报告",
                        "adjunctUrl": "x.PDF",
                        "announcementId": "1",
                        "secName": "羚锐制药",
                        "announcementTime": 0,
                    }
                ]
            }

    def fake_post(url, data=None, headers=None, timeout=None):
        seen_windows.append(data["seDate"])
        return FakeResponse()

    monkeypatch.setattr(dl.session, "post", fake_post)

    reports = dl.query_reports_by_period(
        "600285", "gssh0600285", "sse", "sh", [2024], ["FY"]
    )
    assert len(reports) == 1
    assert len(seen_windows) == 1
    assert seen_windows[0].startswith("2025-01-01")


def test_query_quarterly_searches_report_year_only(monkeypatch, dl):
    """季报在报告当年发布 —— 搜索窗口必须是当年,不是次年。"""
    seen_windows = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "announcements": [
                    {
                        "announcementTitle": "羚锐制药2025年第一季度报告",
                        "adjunctUrl": "x.PDF",
                        "announcementId": "1",
                        "secName": "羚锐制药",
                        "announcementTime": 0,
                    }
                ]
            }

    def fake_post(url, data=None, headers=None, timeout=None):
        seen_windows.append(data["seDate"])
        return FakeResponse()

    monkeypatch.setattr(dl.session, "post", fake_post)

    reports = dl.query_reports_by_period(
        "600285", "gssh0600285", "sse", "sh", [2025], ["Q1"]
    )
    assert len(reports) == 1
    assert reports[0]["period"] == "Q1"
    assert seen_windows == ["2025-01-01~2025-12-31"]


def test_build_filename_annual_unchanged(dl):
    """年报文件名保持不变，兼容既有 data/ 下的历史文件。"""
    assert (
        dl.build_report_filename("羚锐制药", "600285", 2024, "FY")
        == "羚锐制药_600285_2024.pdf"
    )


def test_build_filename_quarterly_has_period_suffix(dl):
    assert (
        dl.build_report_filename("羚锐制药", "600285", 2025, "Q1")
        == "羚锐制药_600285_2025Q1.pdf"
    )
    assert (
        dl.build_report_filename("羚锐制药", "600285", 2025, "H1")
        == "羚锐制药_600285_2025H1.pdf"
    )
    assert (
        dl.build_report_filename("羚锐制药", "600285", 2025, "Q3")
        == "羚锐制药_600285_2025Q3.pdf"
    )


def test_build_filename_strips_illegal_chars(dl):
    assert (
        dl.build_report_filename('角"色', "600285", 2025, "Q1")
        == "角色_600285_2025Q1.pdf"
    )
