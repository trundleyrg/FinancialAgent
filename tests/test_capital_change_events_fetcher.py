import json
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from src.stock_tools.capital_change_fetcher import (
    _report_year_from_cninfo,
    fetch_capital_change_events,
)

FIXTURE = Path(__file__).parent / "fixtures" / "capital_change_events_000423.json"


def _df(rows):
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _patch_ak(fixture_data):
    def fake_em_dividend(symbol, indicator):
        if indicator == "分红":
            return _df(fixture_data["eastmoney_dividend"])
        return _df(fixture_data["eastmoney_allotment"])

    def fake_cninfo_dividend(symbol):
        return _df(fixture_data["cninfo_dividend"])

    def fake_cninfo_allotment(symbol):
        return _df(fixture_data["cninfo_allotment"])

    return patch.multiple(
        "akshare",
        stock_history_dividend_detail=MagicMock(side_effect=fake_em_dividend),
        stock_dividend_cninfo=MagicMock(side_effect=fake_cninfo_dividend),
        stock_allotment_cninfo=MagicMock(side_effect=fake_cninfo_allotment),
    )


def test_fetch_returns_cash_dividend_events_with_left_join():
    """Left-join: all eastmoney rows kept; cninfo enrichment upgrades matching rows."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with _patch_ak(fx):
        events = fetch_capital_change_events("000423")
    # Both eastmoney rows survive (left-join)
    assert len(events) == 2
    by_date = {e["event_date"]: e for e in events}
    # 2024-06-15 matches cninfo: source upgraded to "merged", report_year from cninfo
    matched = by_date["2024-06-15"]
    assert matched["event_type"] == "cash_dividend"
    assert matched["cash_per_10_shares"] == 11.6
    assert matched["report_year"] == 2023   # 来自 cninfo.报告时间 "2023年报"
    assert matched["ex_date"] == "2024-06-20"
    assert matched["source"] == "merged"
    # 2023-06-15 has no cninfo match: source stays "eastmoney", report_year from event_date
    unmatched = by_date["2023-06-15"]
    assert unmatched["event_type"] == "cash_dividend"
    assert unmatched["cash_per_10_shares"] == 7.8
    assert unmatched["report_year"] == 2023   # fallback: event_date.year
    assert unmatched["source"] == "eastmoney"


def test_fetch_returns_empty_when_no_data():
    empty = {
        "eastmoney_dividend": [], "eastmoney_allotment": [],
        "cninfo_dividend": [], "cninfo_allotment": [],
    }
    with _patch_ak(empty):
        events = fetch_capital_change_events("000423")
    assert events == []


def test_fetch_infers_event_type_from_fields():
    fx = {
        "eastmoney_dividend": [
            {"公告日期": "2020-06-15", "送股": 5.0, "转增": 0.0, "派息": 0.0,
             "进度": "实施", "除权除息日": "2020-06-20", "股权登记日": "2020-06-19", "红股上市日": "2020-06-22"},
        ],
        "eastmoney_allotment": [],
        "cninfo_dividend": [],
        "cninfo_allotment": [],
    }
    with _patch_ak(fx):
        events = fetch_capital_change_events("000423")
    assert len(events) == 1
    assert events[0]["event_type"] == "bonus_share"
    assert events[0]["bonus_shares_per_10"] == 5.0
    assert events[0]["source"] == "eastmoney"


def test_fetch_combines_cash_and_bonus():
    fx = {
        "eastmoney_dividend": [
            {"公告日期": "2021-06-15", "送股": 3.0, "转增": 0.0, "派息": 5.0,
             "进度": "实施", "除权除息日": "2021-06-20", "股权登记日": "2021-06-19", "红股上市日": "2021-06-22"},
        ],
        "eastmoney_allotment": [],
        "cninfo_dividend": [],
        "cninfo_allotment": [],
    }
    with _patch_ak(fx):
        events = fetch_capital_change_events("000423")
    assert events[0]["event_type"] == "combination"
    assert events[0]["cash_per_10_shares"] == 5.0
    assert events[0]["bonus_shares_per_10"] == 3.0


def test_fetch_propagates_company_name_when_provided():
    """Passing company_name=... should stamp it onto every emitted event."""
    fx = {
        "eastmoney_dividend": [
            {"公告日期": "2022-06-15", "送股": 0.0, "转增": 0.0, "派息": 6.0,
             "进度": "实施", "除权除息日": "2022-06-20", "股权登记日": "2022-06-19", "红股上市日": "2022-06-22"},
            {"公告日期": "2023-06-15", "送股": 0.0, "转增": 0.0, "派息": 7.0,
             "进度": "实施", "除权除息日": "2023-06-20", "股权登记日": "2023-06-19", "红股上市日": "2023-06-22"},
        ],
        "eastmoney_allotment": [],
        "cninfo_dividend": [],
        "cninfo_allotment": [],
    }
    with _patch_ak(fx):
        events = fetch_capital_change_events(
            "000423", company_name="东阿阿胶",
        )
    assert len(events) == 2
    for ev in events:
        assert ev["company_name"] == "东阿阿胶", (
            f"company_name should be propagated; got {ev['company_name']!r}"
        )


def test_fetch_defaults_company_name_to_empty_string():
    """When company_name is omitted, each event should default to empty string."""
    fx = {
        "eastmoney_dividend": [
            {"公告日期": "2022-06-15", "送股": 0.0, "转增": 0.0, "派息": 6.0,
             "进度": "实施", "除权除息日": "2022-06-20", "股权登记日": "2022-06-19", "红股上市日": "2022-06-22"},
        ],
        "eastmoney_allotment": [],
        "cninfo_dividend": [],
        "cninfo_allotment": [],
    }
    with _patch_ak(fx):
        events = fetch_capital_change_events("000423")
    assert len(events) == 1
    assert events[0]["company_name"] == ""


# ============================================================
# _report_year_from_cninfo — 解析巨潮「报告时间」字段
# ============================================================

class TestReportYearFromCninfo:
    """直接覆盖 4 种报告期格式 + 兜底分支。"""

    def _fb(self):
        # 兜底回退：与 fetcher 调用约定一致
        return date(2024, 6, 15)

    def test_annual_report(self):
        assert _report_year_from_cninfo("2023年报", self._fb()) == 2023

    def test_half_year_report(self):
        assert _report_year_from_cninfo("2023中报", self._fb()) == 2023

    def test_q1_report(self):
        assert _report_year_from_cninfo("2023一季报", self._fb()) == 2023

    def test_q3_report(self):
        assert _report_year_from_cninfo("2023三季报", self._fb()) == 2023

    def test_annual_with_extra_suffix(self):
        assert _report_year_from_cninfo("2023年报分配", self._fb()) == 2023

    def test_none_falls_back_to_fallback_date_year(self):
        assert _report_year_from_cninfo(None, date(2024, 6, 15)) == 2024

    def test_empty_string_falls_back_to_fallback_date_year(self):
        assert _report_year_from_cninfo("", date(2024, 6, 15)) == 2024

    def test_none_fallback_date_returns_zero(self):
        assert _report_year_from_cninfo(None, None) == 0

    def test_unparseable_string_falls_back(self):
        # 不是已知 4 种 token，也无法拆出 4 位数字年份
        assert _report_year_from_cninfo("不规则文本", date(2024, 6, 15)) == 2024
