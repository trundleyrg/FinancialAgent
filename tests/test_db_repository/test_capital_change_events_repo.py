"""CapitalChangeEventRepository 单元测试。"""
from datetime import date

import pytest
from src.db import ReportKey
from src.db.repository.capital_change_events import CapitalChangeEventRepository
from tests.test_db_repository.conftest import FakeConnector


@pytest.fixture
def repo(fake_connector):
    return CapitalChangeEventRepository(fake_connector)


def test_count_events_empty_returns_zero(repo):
    assert repo.count_events(ReportKey(stock_code="000423")) == 0


def test_count_events_after_seed(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2024-06-15",
         "source": "eastmoney"},
    ])
    assert repo.count_events(ReportKey(stock_code="000423")) == 1


def test_list_events_filters_by_type(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2024-06-15",
         "cash_per_10_shares": 11.6, "source": "eastmoney"},
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "allotment", "event_date": "2024-07-01",
         "allotment_price": 8.0, "source": "cninfo"},
    ])
    out = repo.list_events(ReportKey(stock_code="000423"), event_type="cash_dividend")
    assert len(out) == 1
    assert out[0]["cash_per_10_shares"] == 11.6


def test_list_events_filters_by_date_range(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2022, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2023-06-01",
         "cash_per_10_shares": 7.8, "source": "eastmoney"},
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2024-06-15",
         "cash_per_10_shares": 11.6, "source": "eastmoney"},
    ])
    out = repo.list_events(
        ReportKey(stock_code="000423"),
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
    )
    assert len(out) == 1
    assert out[0]["cash_per_10_shares"] == 11.6


def test_list_events_sorted_desc(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2024-06-15",
         "source": "eastmoney"},
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2025-06-15",
         "source": "eastmoney"},
    ])
    out = repo.list_events(ReportKey(stock_code="000423"))
    assert out[0]["event_date"] == "2025-06-15"
    assert out[1]["event_date"] == "2024-06-15"


def test_list_by_report_year_filters_and_sorts(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2024-06-15",
         "cash_per_10_shares": 11.6, "source": "eastmoney"},
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2025-06-15",
         "cash_per_10_shares": 13.2, "source": "eastmoney"},
    ])
    out = repo.list_by_report_year(ReportKey(stock_code="000423"), 2023)
    assert len(out) == 1
    assert out[0]["cash_per_10_shares"] == 11.6


def test_list_by_report_year_empty(repo):
    assert repo.list_by_report_year(ReportKey(stock_code="000423"), 2020) == []


def test_upsert_many_inserts_new(repo, fake_connector):
    events = [
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2025-06-15",
         "cash_per_10_shares": 13.2, "source": "eastmoney"},
    ]
    n = repo.upsert_many(events)
    assert n == 1
    assert fake_connector.data["capital_change_events"][0]["cash_per_10_shares"] == 13.2


def test_upsert_many_idempotent_on_key(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2025-06-15",
         "cash_per_10_shares": 13.2, "source": "eastmoney"},
    ])
    same_event = {"company_name": "A", "stock_code": "000423",
                  "report_year": 2024, "report_period": "FY",
                  "event_type": "cash_dividend", "event_date": "2025-06-15",
                  "cash_per_10_shares": 14.0, "source": "merged"}
    repo.upsert_many([same_event])
    rows = fake_connector.data["capital_change_events"]
    assert len(rows) == 1
    assert rows[0]["cash_per_10_shares"] == 14.0


def test_upsert_many_empty_list(repo):
    assert repo.upsert_many([]) == 0
