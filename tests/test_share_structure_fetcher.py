"""share_structure fetcher 单元测试。

🚨 重要架构决策 — _from_local_derivation 已被禁用

原因:`cash_for_dividend_and_interest` 在中文财报是「分配股利、利润**或偿付利息**
支付的现金」,含子公司分红+利息支付,系统性偏高 ~20%。即使事件 SUM 累加对了,
推导结果仍有 21% 偏差(2024 实测:7.78 亿 vs 真实 6.44 亿)。

任何容差阈值都不能同时满足:
  - 容差太小 → 冷启动正常股票也拒绝
  - 容差太大 → 利息污染通过覆盖真实值(2024 的 21% 偏差就是这么溜进去的)

最安全的做法:直接禁用推导,只走 akshare 实时数据源。

历史事故:2026-09-21 commit a9206b2 用此函数写入了 000423 的脏数据
  total_shares=14.79 亿股(LIMIT 1 bug)+ 后续 7.78 亿股(利息污染),
被 dividend skill 误用,导致 payout_ratio 全年系统性偏高 ~2.3 倍。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.tools import share_structure_fetcher


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

class _FakeConn:
    """最小化 DuckDB connection mock — 用 ``set_response(sql_key, value)`` 装响应。"""

    def __init__(self):
        self.executed_sql: list[str] = []
        self._responses: dict[str, tuple] = {}
        self._row: tuple | None = None

    def execute(self, sql, params=None):
        self.executed_sql.append(sql)
        sql_norm = " ".join(sql.split())
        for key, val in self._responses.items():
            if key in sql_norm:
                self._row = val
                break
        else:
            self._row = None
        return self

    def fetchone(self):
        return self._row

    def set_response(self, sql_keyword: str, value: tuple):
        self._responses[sql_keyword] = value


@pytest.fixture
def fake_conn():
    return _FakeConn()


def _patch_db(monkeypatch, fake_conn):
    """把 fetcher 内的 get_db() 替换成返回 fake_conn 的 duckdb_conn。"""
    db_mock = MagicMock()
    db_mock._duckdb_conn = fake_conn
    monkeypatch.setattr(share_structure_fetcher, "get_db", lambda: db_mock)


# ──────────────────────────────────────────────────────────────────────────────
# 🚨 _from_local_derivation 必须永远返回 None — 利息污染防御
# ──────────────────────────────────────────────────────────────────────────────

def test_from_local_derivation_always_returns_none_due_to_known_bias(fake_conn, monkeypatch):
    """_from_local_derivation 已被禁用,即使有完整 events + cash flow 数据也返回 None。"""
    fake_conn.set_response("SUM(cash_per_10_shares)", (24.1968,))
    fake_conn.set_response("cash_for_dividend_and_interest", (1_882_987_553.57,))
    _patch_db(monkeypatch, fake_conn)

    result = share_structure_fetcher._from_local_derivation("000423", 2024, "FY")

    assert result is None, (
        f"本地推导已禁用(系统偏差不可消除),但返回了 {result}。"
        f"改用 akshare 实时数据或 PDF「股份变动情况表」提取。"
    )


def test_from_local_derivation_empty_data_returns_none(fake_conn, monkeypatch):
    """无 events / 无 cash flow 时也返回 None(默认禁用态)。"""
    _patch_db(monkeypatch, fake_conn)

    result = share_structure_fetcher._from_local_derivation("000423", 2024, "FY")
    assert result is None


def test_from_local_derivation_rationale_documented():
    """禁用原因应在函数 docstring 里有明确说明,防止后人误用。"""
    doc = share_structure_fetcher._from_local_derivation.__doc__ or ""
    # 关键警告点必须出现
    assert "禁用" in doc or "不可靠" in doc or "DISABLED" in doc, (
        "_from_local_derivation 必须在 docstring 里说明禁用原因"
    )
    assert "cash_for_dividend_and_interest" in doc
    assert "利息" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 端到端:fetch_and_persist 写入路径
# ──────────────────────────────────────────────────────────────────────────────

def test_fetch_and_persist_skips_write_when_no_source(fake_conn, monkeypatch):
    """akshare 失败 + 推导已禁用 → fetch_and_persist 应 return False,
    不应 DELETE/INSERT 到 share_structure(防止覆盖已有正确值)。
    """
    monkeypatch.setattr(share_structure_fetcher, "_from_akshare_spot", lambda *a, **k: None)
    _patch_db(monkeypatch, fake_conn)

    ok = share_structure_fetcher.fetch_and_persist("000423", 2024, "FY")
    assert ok is False

    writes = [
        sql for sql in fake_conn.executed_sql
        if "share_structure" in sql and ("DELETE" in sql or "INSERT" in sql)
    ]
    assert writes == [], f"无数据源时不应写库(覆盖正确值的风险),但写了: {writes}"


def test_fetch_and_persist_writes_when_akshare_succeeds(fake_conn, monkeypatch):
    """akshare 路径成功时,fetch_and_persist 应正确 DELETE + INSERT。"""
    monkeypatch.setattr(
        share_structure_fetcher,
        "_from_akshare_spot",
        lambda *a, **k: {
            "company_name": "测试公司",
            "total_shares": 643_976_824.0,
            "unrestricted_shares": 643_976_824.0,
        },
    )
    _patch_db(monkeypatch, fake_conn)

    ok = share_structure_fetcher.fetch_and_persist("000423", 2024, "FY")
    assert ok is True

    delete_sql = [s for s in fake_conn.executed_sql if "DELETE FROM share_structure" in s]
    insert_sql = [s for s in fake_conn.executed_sql if "INSERT INTO share_structure" in s]
    assert len(delete_sql) == 1
    assert len(insert_sql) == 1


# ──────────────────────────────────────────────────────────────────────────────
# akshare 路径行为
# ──────────────────────────────────────────────────────────────────────────────

def test_fetch_share_structure_prefers_akshare_over_local_derivation(fake_conn, monkeypatch):
    """akshare 成功时应优先使用 akshare,不走推导(推导已禁用)。"""
    monkeypatch.setattr(
        share_structure_fetcher,
        "_from_akshare_spot",
        lambda code: {
            "company_name": "测试公司",
            "total_shares": 643_000_000.0,
            "unrestricted_shares": 643_000_000.0,
        },
    )
    # 显式确保推导没被调用
    derivation_called = []

    def derivation_stub(*args, **kwargs):
        derivation_called.append(args)
        return None  # 已禁用

    monkeypatch.setattr(
        share_structure_fetcher,
        "_from_local_derivation",
        derivation_stub,
    )

    result = share_structure_fetcher.fetch_share_structure("000423", 2024, "FY")

    assert result["source"] == "akshare_spot"
    assert result["total_shares"] == 643_000_000.0
    assert derivation_called == [], (
        "akshare 成功就不应再走 _from_local_derivation,但被调用了"
    )