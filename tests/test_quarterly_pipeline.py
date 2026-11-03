"""季报端到端：PDF → 合并三表 → DuckDB。

PDF 是外部夹具,缺失时 skip:
    python script/fetch_quarterly_fixtures.py 600285 2025
"""
from pathlib import Path

import pytest

Q1_PDF = Path("data/600285/羚锐制药_600285_2025Q1.pdf")
Q3_PDF = Path("data/600285/羚锐制药_600285_2025Q3.pdf")

pytestmark = pytest.mark.skipif(
    not (Q1_PDF.exists() and Q3_PDF.exists()),
    reason="缺少季报 PDF 夹具,先跑 script/fetch_quarterly_fixtures.py 600285 2025",
)


@pytest.fixture
def db(tmp_path):
    from src.db.db_connector import DatabaseConnector
    conn = DatabaseConnector(
        database_type="duckdb", database_url=str(tmp_path / "q.duckdb"),
    )
    conn.create_tables()
    yield conn
    conn.close()


def _parse(conn, pdf_path, year, period):
    from src.db.db_connector import save_tables_to_db
    from src.tools.chapter_extractor import PDFChapterExtractor

    ex = PDFChapterExtractor(str(pdf_path))
    try:
        name, short, code, y, p = ex.get_company_info()
        assert y == year
        assert p == period
        tables = ex.extract_main_tables()
    finally:
        ex.close()

    return save_tables_to_db(
        main_tables=tables, company_name=name, pdf_path=str(pdf_path),
        company_short_name=short or name, company_code=code,
        report_year=year, report_period=period, stock_code=code,
        db_connector=conn,
    )


def test_q1_statements_land_with_correct_values(db):
    """Q1 关键数值与 PDF 原值一致(单位:元)。"""
    saved = _parse(db, Q1_PDF, 2025, "Q1")
    assert saved["consolidated_balance_sheet"]
    assert saved["consolidated_income_statement"]
    assert saved["consolidated_cash_flow_statement"]

    con = db._duckdb_conn
    bs = con.execute(
        "SELECT report_year, report_period, total_assets, monetary_funds "
        "FROM consolidated_balance_sheet"
    ).fetchone()
    assert bs == (2025, "Q1", 5410895780.92, 570929618.67)

    inc = con.execute(
        "SELECT operating_revenue, net_profit FROM consolidated_income_statement"
    ).fetchone()
    assert inc == (1020755870.55, 216733789.10)

    cf = con.execute(
        "SELECT net_cash_from_operations FROM consolidated_cash_flow_statement"
    ).fetchone()
    assert cf == (117615900.12,)


def test_q3_income_statement_is_ytd_cumulative(db):
    """Q3 行是 1-9 月累计口径(与季报印的一致)。"""
    _parse(db, Q3_PDF, 2025, "Q3")
    inc = db._duckdb_conn.execute(
        "SELECT report_year, report_period, operating_revenue "
        "FROM consolidated_income_statement"
    ).fetchone()
    assert inc == (2025, "Q3", 3041361639.17)


def test_annual_and_quarterly_coexist_in_same_table(db):
    """FY 与 Q1 行在同一张表里共存,互不覆盖。"""
    from src.db.db_connector import save_tables_to_db
    from src.tools.chapter_extractor import PDFChapterExtractor

    annual = Path("data/600285/羚锐制药_600285_2024.pdf")
    if not annual.exists():
        pytest.skip("缺少年报夹具")

    ex = PDFChapterExtractor(str(annual))
    try:
        name, short, code, y, p = ex.get_company_info()
        assert (y, p) == (2024, "FY")
        tables = ex.extract_main_tables()
    finally:
        ex.close()
    save_tables_to_db(
        main_tables=tables, company_name=name, pdf_path=str(annual),
        company_short_name=short or name, company_code=code,
        report_year=2024, report_period="FY", stock_code=code, db_connector=db,
    )
    _parse(db, Q1_PDF, 2025, "Q1")

    periods = db._duckdb_conn.execute(
        "SELECT report_year, report_period FROM consolidated_income_statement "
        "ORDER BY report_year, report_period"
    ).fetchall()
    assert (2024, "FY") in periods
    assert (2025, "Q1") in periods
