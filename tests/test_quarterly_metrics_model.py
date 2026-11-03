"""QuarterlyFinancialMetrics 模型:建表、存取、scope 维度。"""
import pytest

from src.db.models import QuarterlyFinancialMetrics, ReportPeriod


@pytest.fixture
def db(tmp_path):
    from src.db.db_connector import DatabaseConnector
    conn = DatabaseConnector(
        database_type="duckdb", database_url=str(tmp_path / "m.duckdb"),
    )
    conn.create_tables()
    yield conn
    conn.close()


def test_table_created(db):
    cols = db._table_columns("quarterly_financial_metrics")
    assert "scope" in cols
    assert "operating_revenue" in cols
    assert "weighted_roe" in cols


def test_insert_and_read_back(db):
    db.insert_record(
        "quarterly_financial_metrics",
        company_name="河南羚锐制药股份有限公司",
        stock_code="600285",
        report_year=2025,
        report_period=ReportPeriod.Q3.value,
        scope="YTD",
        operating_revenue=3041361639.17,
        net_profit_attributable_to_parent=650932609.77,
        weighted_roe=20.40,
    )
    rows = db.filter_records(
        "quarterly_financial_metrics", stock_code="600285", report_period="Q3",
    )
    assert len(rows) == 1
    rec = rows[0]
    assert rec.scope == "YTD"
    assert rec.operating_revenue == 3041361639.17
    assert rec.weighted_roe == 20.40
    assert rec.report_year == 2025


def test_two_scopes_coexist(db):
    """同一份季报的 CURRENT 与 YTD 两行并存。"""
    for scope in ("CURRENT", "YTD"):
        db.insert_record(
            "quarterly_financial_metrics",
            company_name="羚锐制药", stock_code="600285",
            report_year=2025, report_period="Q3", scope=scope,
            operating_revenue=1.0 if scope == "CURRENT" else 2.0,
        )
    rows = db.filter_records(
        "quarterly_financial_metrics", stock_code="600285", report_period="Q3",
    )
    assert {r.scope for r in rows} == {"CURRENT", "YTD"}


def test_report_period_enum_has_all_four():
    assert {p.value for p in ReportPeriod} == {"Q1", "H1", "Q3", "FY"}
