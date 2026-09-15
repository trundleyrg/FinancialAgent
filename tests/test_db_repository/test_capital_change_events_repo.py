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


def test_aggregate_dividend_stats_computes_totals(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2024-06-15",
         "cash_per_10_shares": 11.6, "source": "eastmoney"},
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2024, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2025-06-15",
         "cash_per_10_shares": 13.2, "source": "eastmoney"},
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "allotment", "event_date": "2024-08-01",
         "allotment_price": 8.0, "source": "cninfo"},
    ])
    out = repo.aggregate_dividend_stats(ReportKey(stock_code="000423"), years=5)
    assert out["event_count"] == 2
    assert out["total_cash_per_10_shares"] == round(11.6 + 13.2, 4)
    assert out["average_cash_per_10_shares"] == round((11.6 + 13.2) / 2, 4)
    assert out["last_event_date"] == "2025-06-15"
    assert out["last_cash_per_10_shares"] == 13.2


def test_aggregate_dividend_stats_empty(repo):
    out = repo.aggregate_dividend_stats(ReportKey(stock_code="000423"), years=5)
    assert out["event_count"] == 0
    assert out["total_cash_per_10_shares"] == 0.0
    assert out["last_event_date"] is None


def test_aggregate_dividend_stats_excludes_allotment(repo, fake_connector):
    fake_connector.seed("capital_change_events", [
        {"company_name": "A", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "allotment", "event_date": "2024-08-01",
         "cash_per_10_shares": None, "allotment_price": 8.0, "source": "cninfo"},
    ])
    out = repo.aggregate_dividend_stats(ReportKey(stock_code="000423"), years=5)
    assert out["event_count"] == 0


def test_aggregate_dividend_stats_cutoff_year_excludes_old_events(
    repo, fake_connector,
):
    """cutoff_year 窗口外的 cash_dividend 事件必须不计入合计 / 计数。

    repo 逻辑：cutoff_year = date.today().year - years + 1，
    即「过去 years 年的所有事件」均视为窗口内。

    本测试在窗口内插 4 条、窗口外插 2 条（10 年前 / 5 年前），
    断言 event_count == 4 且 total 仅汇总窗口内 4 条。
    """
    today = date.today()
    cutoff_year = today.year - 5 + 1  # 镜像 repo 公式

    recent_years = [cutoff_year, cutoff_year + 1, today.year - 1, today.year]
    recent_events = [
        {"company_name": "A", "stock_code": "000423",
         "report_year": y, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": f"{y}-06-15",
         "cash_per_10_shares": 10.0, "source": "eastmoney"}
        for y in recent_years
    ]
    old_events = [
        {"company_name": "A", "stock_code": "000423",
         "report_year": cutoff_year - 10, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": f"{cutoff_year - 10}-06-15",
         "cash_per_10_shares": 100.0, "source": "eastmoney"},
        {"company_name": "A", "stock_code": "000423",
         "report_year": cutoff_year - 5, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": f"{cutoff_year - 5}-06-15",
         "cash_per_10_shares": 50.0, "source": "eastmoney"},
    ]
    fake_connector.seed("capital_change_events", recent_events + old_events)
    out = repo.aggregate_dividend_stats(
        ReportKey(stock_code="000423"), years=5,
    )
    assert out["event_count"] == 4
    assert out["total_cash_per_10_shares"] == round(4 * 10.0, 4)
    assert out["average_cash_per_10_shares"] == round(10.0, 4)


def test_aggregate_dividend_stats_cutoff_year_includes_boundary_year(
    repo, fake_connector,
):
    """cutoff_year 当年的事件应当被包含（边界 >= 而非 >）。"""
    today = date.today()
    cutoff_year = today.year - 3 + 1
    fake_connector.seed("capital_change_events", [
        {"company_name": "A", "stock_code": "000423",
         "report_year": cutoff_year, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": f"{cutoff_year}-03-15",
         "cash_per_10_shares": 5.5, "source": "eastmoney"},
    ])
    out = repo.aggregate_dividend_stats(
        ReportKey(stock_code="000423"), years=3,
    )
    assert out["event_count"] == 1
    assert out["total_cash_per_10_shares"] == 5.5
