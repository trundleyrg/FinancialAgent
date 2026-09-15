"""SQL injection hardening tests for update_records/delete_records.

覆盖：
- DatabaseConnector.update_records / delete_records 拒绝未知列名
- DuckDBModelAdapter.update_records / delete_records 拒绝未知列名
- 合法的列名仍然可以正常工作
"""
import os
import tempfile

import pytest

from src.db.db_connector import DatabaseConnector, DuckDBModelAdapter
from src.db.models import CapitalChangeEvent


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


# ============================================================
# DatabaseConnector 公共 API 层
# ============================================================

class TestUpdateRecordsRejectsUnknownColumns:
    def test_update_records_rejects_unknown_filter_column(self, tmp_duckdb_connector):
        """update_records 拒绝 kwargs 中未命中模型字段的 key。"""
        with pytest.raises(ValueError, match="未知列名"):
            tmp_duckdb_connector.update_records(
                "capital_change_events",
                {"event_type": "cash_dividend"},
                evil_col="x",  # not a real column
            )

    def test_update_records_rejects_unknown_update_column(self, tmp_duckdb_connector):
        """update_records 拒绝 updates dict 中未命中模型字段的 key。"""
        with pytest.raises(ValueError, match="未知列名"):
            tmp_duckdb_connector.update_records(
                "capital_change_events",
                {"evil_col": "x"},  # bad update key
                stock_code="000423",
            )

    def test_update_records_accepts_valid_columns(self, tmp_duckdb_connector):
        """合法列名（kwargs + updates）正常执行。"""
        # 先插入一行
        tmp_duckdb_connector.insert_record(
            "capital_change_events",
            company_name="A", stock_code="000423",
            report_year=2024, report_period="FY",
            event_type="cash_dividend", event_date="2024-01-01",
            source="eastmoney", cash_per_10_shares=10.0,
        )
        # 用合法列名更新
        n = tmp_duckdb_connector.update_records(
            "capital_change_events",
            {"event_type": "allotment"},
            stock_code="000423", event_date="2024-01-01",
            event_type="cash_dividend",
        )
        assert n == 1
        # 验证行已更新
        rows = tmp_duckdb_connector.filter_records(
            "capital_change_events", stock_code="000423",
        )
        assert rows[0].event_type == "allotment"

    def test_update_records_rejects_when_kwargs_empty(self, tmp_duckdb_connector):
        """保留旧行为：kwargs 为空仍抛「需要至少一个过滤条件」。"""
        with pytest.raises(ValueError, match="至少一个过滤条件"):
            tmp_duckdb_connector.update_records(
                "capital_change_events",
                {"event_type": "cash_dividend"},
            )

    def test_update_records_rejects_empty_updates(self, tmp_duckdb_connector):
        """保留旧行为：updates 为空直接返回 0。"""
        assert tmp_duckdb_connector.update_records(
            "capital_change_events", {}, stock_code="000423",
        ) == 0


class TestDeleteRecordsRejectsUnknownColumns:
    def test_delete_records_rejects_unknown_filter_column(self, tmp_duckdb_connector):
        """delete_records 拒绝 kwargs 中未命中模型字段的 key。"""
        with pytest.raises(ValueError, match="未知列名"):
            tmp_duckdb_connector.delete_records(
                "capital_change_events",
                evil_col="x",
            )

    def test_delete_records_accepts_valid_columns(self, tmp_duckdb_connector):
        """合法列名正常删除。"""
        tmp_duckdb_connector.insert_record(
            "capital_change_events",
            company_name="A", stock_code="000423",
            report_year=2024, report_period="FY",
            event_type="cash_dividend", event_date="2024-01-01",
            source="eastmoney", cash_per_10_shares=10.0,
        )
        n = tmp_duckdb_connector.delete_records(
            "capital_change_events", stock_code="000423",
        )
        assert n == 1
        assert tmp_duckdb_connector.filter_records(
            "capital_change_events", stock_code="000423",
        ) == []

    def test_delete_records_rejects_when_kwargs_empty(self, tmp_duckdb_connector):
        """保留旧行为：kwargs 为空抛「需要至少一个过滤条件」。"""
        with pytest.raises(ValueError, match="至少一个过滤条件"):
            tmp_duckdb_connector.delete_records("capital_change_events")


# ============================================================
# DuckDBModelAdapter 直接调用层（防御深度）
# ============================================================

class TestAdapterUpdateDeleteRejectsUnknownColumns:
    def test_adapter_update_records_rejects_unknown_filter(self, tmp_duckdb_connector):
        adapter = tmp_duckdb_connector._duckdb_adapter
        with pytest.raises(ValueError, match="未知列名"):
            adapter.update_records(
                CapitalChangeEvent,
                {"event_type": "cash_dividend"},
                evil_col="x",
            )

    def test_adapter_update_records_rejects_unknown_update(self, tmp_duckdb_connector):
        adapter = tmp_duckdb_connector._duckdb_adapter
        with pytest.raises(ValueError, match="未知列名"):
            adapter.update_records(
                CapitalChangeEvent,
                {"evil_col": "x"},
                stock_code="000423",
            )

    def test_adapter_delete_records_rejects_unknown(self, tmp_duckdb_connector):
        adapter = tmp_duckdb_connector._duckdb_adapter
        with pytest.raises(ValueError, match="未知列名"):
            adapter.delete_records(CapitalChangeEvent, evil_col="x")