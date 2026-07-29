from src.db.repository.keys import ReportKey
from src.db.repository.metrics import MetricRepository
from tests.test_db_repository.conftest import FakeConnector


def test_get_metrics_by_report_id(fake_connector):
    fake_connector.seed("financial_metrics", [
        {"report_id": 1, "metric_name": "ROE", "value": 15.2},
        {"report_id": 1, "metric_name": "毛利率", "value": 60.5},
        {"report_id": 2, "metric_name": "ROE", "value": 18.0},
    ])
    repo = MetricRepository(fake_connector)
    out = repo.get_metrics_by_report_id(1)
    assert len(out) == 2
    assert {m["metric_name"] for m in out} == {"ROE", "毛利率"}


def test_get_metrics_via_report_key(fake_connector):
    fake_connector.seed("financial_reports", [
        {"id": 1, "company_name": "A", "stock_code": "000001",
         "report_year": 2024, "report_period": "FY", "source_file": "f"},
    ])
    fake_connector.seed("financial_metrics", [
        {"report_id": 1, "metric_name": "ROE", "value": 15.2},
    ])
    repo = MetricRepository(fake_connector)
    out = repo.get_metrics(ReportKey(stock_code="000001", year=2024, period="FY"))
    assert len(out) == 1
    assert out[0]["metric_name"] == "ROE"


def test_get_metrics_no_report_returns_empty(fake_connector):
    repo = MetricRepository(fake_connector)
    out = repo.get_metrics(ReportKey(stock_code="999999"))
    assert out == []


def test_get_report_with_metrics(fake_connector):
    fake_connector.seed("financial_reports", [
        {"id": 1, "company_name": "A", "stock_code": "000001",
         "report_year": 2024, "report_period": "FY", "source_file": "f"},
    ])
    fake_connector.seed("financial_metrics", [
        {"report_id": 1, "metric_name": "ROE", "value": 15.2},
    ])
    repo = MetricRepository(fake_connector)
    out = repo.get_report_with_metrics(
        ReportKey(stock_code="000001", year=2024, period="FY")
    )
    assert out is not None
    assert out["report"]["stock_code"] == "000001"
    assert out["metrics"][0]["metric_name"] == "ROE"


def test_get_report_with_metrics_no_report(fake_connector):
    repo = MetricRepository(fake_connector)
    assert repo.get_report_with_metrics(ReportKey(stock_code="999999")) is None
