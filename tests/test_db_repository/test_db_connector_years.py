"""DatabaseConnector.get_all_report_years 集成测试。"""
import os
import tempfile

import pytest

from src.db.db_connector import DatabaseConnector


@pytest.fixture
def tmp_duckdb_connector(monkeypatch):
    """每次创建全新 in-memory DuckDB。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False)
    tmp.close()
    monkeypatch.setenv("DUCKDB_DB_PATH", tmp.name)
    conn = DatabaseConnector(database_type="duckdb")
    conn.create_tables()
    yield conn
    conn.close()
    os.unlink(tmp.name)


def test_get_all_report_years_empty(tmp_duckdb_connector):
    assert tmp_duckdb_connector.get_all_report_years() == []


def test_get_all_report_years_distinct_desc(tmp_duckdb_connector):
    conn = tmp_duckdb_connector
    conn.insert_record(
        "financial_reports",
        company_name="A", company_short_name="A",
        stock_code="000001", report_year=2022, report_period="FY",
        source_file="x",
    )
    conn.insert_record(
        "financial_reports",
        company_name="A", company_short_name="A",
        stock_code="000001", report_year=2024, report_period="FY",
        source_file="x",
    )
    conn.insert_record(
        "financial_reports",
        company_name="B", company_short_name="B",
        stock_code="000002", report_year=2023, report_period="FY",
        source_file="x",
    )
    assert conn.get_all_report_years() == [2024, 2023, 2022]
