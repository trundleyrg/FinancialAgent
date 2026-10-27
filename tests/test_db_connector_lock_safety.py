"""db_connector 的数据库文件保护测试。

## 背景(实际事故)

``DatabaseConnector._init_duckdb`` 里,连接失败就删库重建:

    try:
        test_conn = duckdb.connect(database_url)
        test_conn.execute("SELECT 1")
    except Exception as e:
        db_logger.warning(f"数据库文件损坏，正在重新创建: {e}")
        os.remove(database_url)          # ← 删库!

但 DuckDB 的**并发锁冲突**也会走到这个 except 分支 —— 而此时文件
完全正常,只是另一个进程正持有写锁。

实测事故:两个进程同时访问同一个 .duckdb(一个跑 pipeline 写,一个跑
行情刷新读),后者拿不到锁 → 触发"文件损坏"逻辑 → **删掉整个数据库**,
前者写入的所有财报数据全部丢失,且 pipeline 仍 exit 0(看不出任何异常)。

DuckDB 是单写者锁的文件数据库,并发访问是**正常场景**(比如 CI 里
一个进程跑测试、另一个跑 pipeline),不是"文件损坏"。

本测试锁定:锁冲突必须抛出,**绝不删库**。
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_lock_conflict_error():
    """构造 DuckDB 的锁冲突异常(与真实报错同类型)。"""
    import duckdb
    exc = duckdb.IOException(
        'IO Error: Could not set lock on file "/tmp/x.duckdb": '
        "Conflicting lock is held in PID 12345 by user xxx."
    )
    return exc


def test_lock_conflict_does_not_delete_database(tmp_path):
    """锁冲突时:抛异常,但**保留**数据库文件。"""
    from src.db import db_connector as mod

    db_file = tmp_path / "test.duckdb"
    db_file.write_bytes(b"not-really-a-duckdb-but-exists")

    with patch.object(mod.duckdb, "connect", side_effect=_make_lock_conflict_error()):
        with pytest.raises(Exception) as exc_info:
            mod.DatabaseConnector("duckdb", str(db_file))

    assert db_file.exists(), (
        "锁冲突时数据库文件被删了!并发访问不是文件损坏,不该删库。"
    )
    assert "Conflicting lock" in str(exc_info.value) or "lock" in str(exc_info.value).lower(), (
        f"应把锁冲突异常抛出(让调用方等待/重试),实际 {exc_info.value}"
    )


def test_real_corruption_still_recreates(tmp_path):
    """真损坏(非锁问题)时:删文件重建 —— 保留原有行为。"""
    from src.db import db_connector as mod

    db_file = tmp_path / "broken.duckdb"
    db_file.write_bytes(b"garbage-not-duckdb")

    calls = {"n": 0}
    real_connect = mod.duckdb.connect

    def fake_connect(path, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            # 第一次:损坏检测用的探测连接
            raise RuntimeError("IO Error: The file is not a valid DuckDB database")
        return real_connect(path, *a, **kw)

    with patch.object(mod.duckdb, "connect", side_effect=fake_connect):
        conn = mod.DatabaseConnector("duckdb", str(db_file))
        assert conn is not None
        assert calls["n"] >= 2, "应重新连接"

    assert db_file.exists(), "重建后文件应存在"


def test_is_lock_conflict_classification():
    """锁冲突的可识别性:错误信息里应含 lock 相关关键词。"""
    from src.db.db_connector import _is_lock_conflict

    assert _is_lock_conflict(_make_lock_conflict_error())
    assert _is_lock_conflict(OSError("Conflicting lock is held in PID 1"))
    assert not _is_lock_conflict(RuntimeError("The file is not a valid DuckDB database"))
    assert not _is_lock_conflict(ValueError("随便什么错"))
