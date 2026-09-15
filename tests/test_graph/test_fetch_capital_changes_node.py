"""fetch_capital_changes_node 单元测试。"""
import pytest
from src.graph.coordinator_nodes import fetch_capital_changes_node
from src.db import CapitalChangeEventRepository, ReportKey
from tests.test_db_repository.conftest import FakeConnector


@pytest.fixture
def wired(monkeypatch):
    fake = FakeConnector()
    repo = CapitalChangeEventRepository(fake)
    monkeypatch.setattr(
        "src.graph.coordinator_nodes.CapitalChangeEventRepository",
        lambda *a, **kw: repo,
    )
    monkeypatch.setattr(
        "src.graph.coordinator_nodes.fetch_capital_change_events",
        lambda code: [{"company_name": "东阿阿胶", "stock_code": code,
                        "report_year": 2024, "report_period": "FY",
                        "event_type": "cash_dividend", "event_date": "2025-06-15",
                        "cash_per_10_shares": 13.2, "source": "eastmoney"}],
    )
    return fake, repo


def test_node_fetches_when_count_is_zero(wired):
    fake, repo = wired
    state = {"company_name": "东阿阿胶", "stock_code": "000423"}
    out = fetch_capital_changes_node(state)
    assert out["capital_changes_fetched"] is True
    assert out["capital_changes_count"] == 1
    rows = fake.data["capital_change_events"]
    assert len(rows) == 1
    assert rows[0]["cash_per_10_shares"] == 13.2


def test_node_skips_when_already_populated(wired):
    fake, repo = wired
    fake.seed("capital_change_events", [
        {"company_name": "东阿阿胶", "stock_code": "000423",
         "report_year": 2023, "report_period": "FY",
         "event_type": "cash_dividend", "event_date": "2024-06-15",
         "cash_per_10_shares": None, "source": "eastmoney"},
    ])
    state = {"company_name": "东阿阿胶", "stock_code": "000423"}
    out = fetch_capital_changes_node(state)
    assert out["capital_changes_count"] == 1
    rows = fake.data["capital_change_events"]
    assert len(rows) == 1
    assert rows[0]["cash_per_10_shares"] is None


def test_node_fails_soft_on_akshare_error(monkeypatch):
    fake = FakeConnector()
    repo_inst = CapitalChangeEventRepository(fake)
    monkeypatch.setattr(
        "src.graph.coordinator_nodes.CapitalChangeEventRepository",
        lambda *a, **kw: repo_inst,
    )
    def _raise(code):
        raise RuntimeError("network down")
    monkeypatch.setattr(
        "src.graph.coordinator_nodes.fetch_capital_change_events",
        _raise,
    )
    state = {"company_name": "东阿阿胶", "stock_code": "000423"}
    out = fetch_capital_changes_node(state)
    assert out["capital_changes_fetched"] is False
    assert out["capital_changes_count"] == 0
