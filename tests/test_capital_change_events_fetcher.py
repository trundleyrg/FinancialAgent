import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from src.stock_tools.capital_change_fetcher import fetch_capital_change_events

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


def test_fetch_returns_cash_dividend_event():
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with _patch_ak(fx):
        events = fetch_capital_change_events("000423")
    assert len(events) == 1
    ev = events[0]
    assert ev["stock_code"] == "000423"
    assert ev["event_type"] == "cash_dividend"
    assert ev["cash_per_10_shares"] == 11.6
    assert ev["report_year"] == 2023   # 来自 cninfo.报告时间 "2023年报"
    assert ev["ex_date"] == "2024-06-20"
    assert ev["source"] == "merged"


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
