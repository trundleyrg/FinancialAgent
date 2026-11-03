"""KPI 入库路径。"""
from pathlib import Path

import pytest

Q3_PDF = Path("data/600285/羚锐制药_600285_2025Q3.pdf")


@pytest.fixture
def db(tmp_path):
    from src.db.db_connector import DatabaseConnector
    conn = DatabaseConnector(
        database_type="duckdb", database_url=str(tmp_path / "s.duckdb"),
    )
    conn.create_tables()
    yield conn
    conn.close()


def test_save_quarterly_metrics_creates_rows_per_scope(db):
    from src.db.db_connector import save_quarterly_metrics
    from src.tools.quarterly_metrics_extractor import QuarterlyMetricsExtractor

    if not Q3_PDF.exists():
        pytest.skip("缺 Q3 夹具")

    ex = QuarterlyMetricsExtractor(str(Q3_PDF))
    try:
        data = ex.extract()
    finally:
        ex.close()

    saved = save_quarterly_metrics(
        metrics_by_scope=data, company_name="羚锐制药", stock_code="600285",
        report_year=2025, report_period="Q3", db_connector=db,
    )
    assert set(saved) == {"CURRENT", "YTD"}

    rows = db.filter_records(
        "quarterly_financial_metrics", stock_code="600285", report_period="Q3",
    )
    by_scope = {r.scope: r for r in rows}
    assert by_scope["CURRENT"].operating_revenue == 942156123.36
    assert by_scope["YTD"].operating_revenue == 3041361639.17
    assert by_scope["YTD"].total_assets is None   # 期末指标只进 CURRENT


def test_save_quarterly_metrics_is_idempotent(db):
    from src.db.db_connector import save_quarterly_metrics
    payload = {"CURRENT": {"operating_revenue": 1.0}}
    for _ in range(2):
        save_quarterly_metrics(
            metrics_by_scope=payload, company_name="羚锐制药", stock_code="600285",
            report_year=2025, report_period="Q3", db_connector=db,
        )
    rows = db.filter_records(
        "quarterly_financial_metrics", stock_code="600285", report_period="Q3",
    )
    assert len(rows) == 1
    assert rows[0].operating_revenue == 1.0


def test_statement_registry_includes_quarterly_metrics():
    from src.db.repository.statements import list_statements
    assert "quarterly_financial_metrics" in list_statements()
