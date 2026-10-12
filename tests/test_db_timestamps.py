"""created_at / updated_at 自动维护的测试。

覆盖:
1. 12 张财务表都有 created_at + updated_at 列
2. DatabaseConnector.create(model_instance) 自动填时间戳
3. DatabaseConnector.insert(model_class, data) 自动填
4. DatabaseConnector.update_records(model_class, ...) 自动更新 updated_at
5. 历史数据回填默认值(已有行 updated_at = created_at)
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from src.db import models as db_models
from src.db.db_connector import DatabaseConnector, get_db
from src.db.models import (
    CapitalChangeEvent,
    ConsolidatedBalanceSheet,
    ConsolidatedCashFlowStatement,
    ConsolidatedIncomeStatement,
    FinancialMetric,
    FinancialReport,
    ParentCompanyBalanceSheet,
    ParentCompanyCashFlowStatement,
    ParentCompanyIncomeStatement,
    ShareStructure,
    SkillAnalysisResult,
    StockMarketSnapshot,
)


# ──────────────────────────────────────────────────────────────────────────────
# 所有 12 张表都有时间戳列
# ──────────────────────────────────────────────────────────────────────────────

ALL_TABLES = [
    FinancialReport,
    FinancialMetric,
    ConsolidatedBalanceSheet,
    ConsolidatedIncomeStatement,
    ConsolidatedCashFlowStatement,
    ParentCompanyBalanceSheet,
    ParentCompanyIncomeStatement,
    ParentCompanyCashFlowStatement,
    ShareStructure,
    CapitalChangeEvent,
    SkillAnalysisResult,
    StockMarketSnapshot,
]


@pytest.mark.parametrize("model_class", ALL_TABLES)
def test_table_has_created_at_column(model_class):
    """每张表都应有 created_at 列(DateTimeField)。"""
    fields = model_class._meta.fields
    assert "created_at" in fields, (
        f"{model_class._meta.table_name} 缺 created_at 列"
    )


@pytest.mark.parametrize("model_class", ALL_TABLES)
def test_table_has_updated_at_column(model_class):
    """每张表都应有 updated_at 列(DateTimeField)。"""
    fields = model_class._meta.fields
    assert "updated_at" in fields, (
        f"{model_class._meta.table_name} 缺 updated_at 列"
    )


# ──────────────────────────────────────────────────────────────────────────────
# DatabaseConnector.create(model_instance) 自动填时间戳
# ──────────────────────────────────────────────────────────────────────────────

def test_create_auto_fills_both_timestamps():
    """create(model_instance) 自动填 created_at 和 updated_at(应接近 now)。

    通过 DatabaseConnector._duckdb_adapter.create(model_instance) 走真实 DuckDB 路径。
    (DatabaseConnector 上没有 create(model_instance),只有 insert_record(table_name, **kwargs)。)
    """
    db = get_db()
    instance = FinancialReport(
        company_name="create 测试公司",
        company_short_name="create测试",
        stock_code="888888",
        report_year=2099,
        report_period="FY",
    )
    rid = db._duckdb_adapter.create(instance)
    try:
        now = datetime.now()
        row = db._duckdb_adapter.get_by_id(FinancialReport, rid)
        assert row["created_at"] is not None
        assert row["updated_at"] is not None
        delta_created = abs((row["created_at"] - now).total_seconds())
        delta_updated = abs((row["updated_at"] - now).total_seconds())
        assert delta_created < 5, f"created_at 偏离 now {delta_created:.1f}s"
        assert delta_updated < 5, f"updated_at 偏离 now {delta_updated:.1f}s"
    finally:
        db._duckdb_conn.execute(
            "DELETE FROM financial_reports WHERE id = ?", [rid],
        )


def test_update_preserves_created_at_and_refreshes_updated_at():
    """已有记录再 update 时,created_at 保持不变,updated_at 刷新。"""
    db = get_db()
    instance = FinancialReport(
        company_name="update 测试公司",
        company_short_name="update测试",
        stock_code="888889",
        report_year=2099,
        report_period="FY",
    )
    rid = db._duckdb_adapter.create(instance)
    try:
        original = db._duckdb_adapter.get_by_id(FinancialReport, rid)
        original_created = original["created_at"]
        original_updated = original["updated_at"]

        time.sleep(1.1)

        db._duckdb_adapter.update(FinancialReport, rid, company_short_name="改名")

        reloaded = db._duckdb_adapter.get_by_id(FinancialReport, rid)
        assert reloaded["created_at"] == original_created, (
            "created_at 不应被 update 覆盖"
        )
        assert reloaded["updated_at"] > original_updated, (
            f"updated_at 应刷新:old={original_updated}, new={reloaded['updated_at']}"
        )
    finally:
        db._duckdb_conn.execute(
            "DELETE FROM financial_reports WHERE id = ?", [rid],
        )


# ──────────────────────────────────────────────────────────────────────────────
# DatabaseConnector.insert(model_class, data) 自动填时间戳
# ──────────────────────────────────────────────────────────────────────────────

def test_insert_auto_fills_timestamps_when_caller_omits():
    """insert 不传 created_at / updated_at → 自动填为 now。"""
    db = get_db()
    initial = {
        "company_name": "insert 测试",
        "company_short_name": "irtest",
        "stock_code": "888890",
        "report_year": 2099,
        "report_period": "FY",
    }
    rid = db.insert(FinancialReport, initial)
    try:
        row = db._duckdb_conn.execute(
            "SELECT created_at, updated_at FROM financial_reports WHERE id = ?",
            [rid],
        ).fetchone()
        now = datetime.now()
        assert row[0] is not None
        assert row[1] is not None
        assert abs((row[0] - now).total_seconds()) < 5
        assert abs((row[1] - now).total_seconds()) < 5
    finally:
        db._duckdb_conn.execute(
            "DELETE FROM financial_reports WHERE id = ?", [rid],
        )


def test_insert_caller_provided_timestamps_kept():
    """insert caller 传了 created_at → 用 caller 的值,不覆盖。"""
    db = get_db()
    explicit_time = datetime(2099, 1, 1, 12, 0, 0)
    rid = db.insert(FinancialReport, {
        "company_name": "explicit_time 测试",
        "company_short_name": "ext",
        "stock_code": "888891",
        "report_year": 2099,
        "report_period": "FY",
        "created_at": explicit_time,
    })
    try:
        row = db._duckdb_conn.execute(
            "SELECT created_at, updated_at FROM financial_reports WHERE id = ?",
            [rid],
        ).fetchone()
        assert row[0] == explicit_time
        assert row[1] is not None
        assert row[1] != explicit_time
    finally:
        db._duckdb_conn.execute(
            "DELETE FROM financial_reports WHERE id = ?", [rid],
        )


def test_update_records_auto_refreshes_updated_at():
    """update_records 不传 updated_at → 自动刷新。"""
    db = get_db()
    rid = db.insert(FinancialReport, {
        "company_name": "update_records 测试",
        "company_short_name": "urtest",
        "stock_code": "888892",
        "report_year": 2099,
        "report_period": "FY",
    })
    try:
        original = db._duckdb_conn.execute(
            "SELECT updated_at FROM financial_reports WHERE id = ?",
            [rid],
        ).fetchone()
        original_updated = original[0]
        time.sleep(1.1)
        # 用 DuckDBModelAdapter 的 update_records(model_class, ...)(自动维护 updated_at)
        db._duckdb_adapter.update_records(
            FinancialReport,
            updates={"company_short_name": "urtest_new"},
            id=rid,
        )
        row = db._duckdb_conn.execute(
            "SELECT updated_at, company_short_name FROM financial_reports WHERE id = ?",
            [rid],
        ).fetchone()
        assert row[0] > original_updated, (
            f"updated_at 应刷新:old={original_updated}, new={row[0]}"
        )
        assert row[1] == "urtest_new"
    finally:
        db._duckdb_conn.execute(
            "DELETE FROM financial_reports WHERE id = ?", [rid],
        )


# ──────────────────────────────────────────────────────────────────────────────
# 历史数据回填(已有行 created_at/updated_at 不为 NULL)
# ──────────────────────────────────────────────────────────────────────────────

def test_existing_rows_have_timestamps_backfilled():
    """已存在的行:created_at / updated_at 不为 NULL(迁移默认)。"""
    db = get_db()
    rows = db._duckdb_conn.execute(
        "SELECT created_at, updated_at FROM financial_reports LIMIT 1",
    ).fetchall()
    if not rows:
        pytest.skip("financial_reports 表为空,跳过历史回填验证")
    created, updated = rows[0]
    assert created is not None, "历史行的 created_at 应被回填"
    assert updated is not None, "历史行的 updated_at 应被回填"


# ──────────────────────────────────────────────────────────────────────────────
# 模型字段默认值(default=datetime.now)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("model_class", ALL_TABLES)
def test_model_default_timestamp_value_is_callable(model_class):
    """每张表的 created_at / updated_at 字段默认值应是可调用的 now。"""
    fields = model_class._meta.fields
    for col in ("created_at", "updated_at"):
        f = fields[col]
        # default 应该是 datetime.now 函数(callable, 调用后返回当前时间)
        assert callable(f.default), (
            f"{model_class._meta.table_name}.{col}.default 应该是 datetime.now "
            f"可调用,实际是 {f.default!r}"
        )
        # 验证 default() 确实是 now()
        v = f.default()
        assert isinstance(v, datetime)