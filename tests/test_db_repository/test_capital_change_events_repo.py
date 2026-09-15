"""CapitalChangeEventRepository 单元测试。"""
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
