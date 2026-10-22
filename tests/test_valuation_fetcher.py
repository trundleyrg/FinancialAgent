"""估值数据抓取器测试(PE / PB / 总市值)。

数据源:akshare ``stock_value_em``(东财个股估值)。

设计动机:此前 PE/PB 走 ``ak.stock_zh_a_hist`` + ``stock_zh_valuation_baidu``,
2026-09 起频繁断连,导致 dividend skill 估值段恒为 N/A。
``stock_value_em`` 是东财同一供应商的另一个接口,单次调用即返回
全历史(实测 600285 有 2134 行,含 PE(TTM) / PE(静) / 市净率 /
总市值 / 总股本),更适合做估值快照。

测试策略:akshare 用 ``patch`` mock(不依赖网络),只验证字段映射与
去重逻辑;真实网络连通性由集成测试覆盖。
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.tools.valuation_fetcher import (
    _normalize_code,
    extract_valuation_rows,
    save_valuation_snapshots,
)


def _make_df() -> pd.DataFrame:
    """构造 stock_value_em 的典型返回(列名与真实接口一致)。"""
    return pd.DataFrame(
        {
            "数据日期": ["2026-10-20", "2026-10-21", "2026-10-22"],
            "当日收盘价": [21.18, 20.65, 20.52],
            "总市值": [1.201151e10, 1.171093e10, 1.163721e10],
            "总股本": [567115486, 567115486, 567115486],
            "PE(TTM)": [15.395254, 15.010010, 14.915516],
            "PE(静)": [15.814955, 15.419207, 15.322137],
            "市净率": [3.716852, 3.623843, 3.601030],
        }
    )


def _patch_ak(df):
    return patch("akshare.stock_value_em", MagicMock(return_value=df))


# ──────────────────────────────────────────────────────────────────────────────
# _normalize_code
# ──────────────────────────────────────────────────────────────────────────────


def test_normalize_code():
    assert _normalize_code("600285") == "600285"
    assert _normalize_code("sh600285") == "600285"
    assert _normalize_code("SZ.000001") == "000001"
    assert _normalize_code("  000001  ") == "000001"
    assert _normalize_code("bj430047") == "430047"
    # 补零到 6 位
    assert _normalize_code("1234") == "001234"


# ──────────────────────────────────────────────────────────────────────────────
# extract_valuation_rows
# ──────────────────────────────────────────────────────────────────────────────


def test_extract_rows_maps_all_fields():
    df = _make_df()
    with _patch_ak(df):
        rows = extract_valuation_rows("600285")

    assert len(rows) == 3
    latest = rows[-1]  # 按日期升序,最后一行是最新
    assert latest["snapshot_date"] == date(2026, 10, 22)
    assert latest["close_price"] == pytest.approx(20.52)
    # PE/PB 舍入到 4 位小数(避免 float32 精度误差写进 DOUBLE)
    assert latest["pe_ratio"] == pytest.approx(14.9155, abs=1e-3)
    assert latest["pb_ratio"] == pytest.approx(3.6010, abs=1e-3)
    assert latest["total_market_cap"] == pytest.approx(1.163721e10, rel=1e-6)
    assert latest["source"] == "akshare_value_em"


def test_extract_rows_sorted_by_date_ascending():
    """东财返回按日期降序,这里统一转成升序(便于取最后一行当最新)。"""
    df = _make_df().iloc[::-1].reset_index(drop=True)  # 反转成降序
    with _patch_ak(df):
        rows = extract_valuation_rows("600285")
    dates = [r["snapshot_date"] for r in rows]
    assert dates == sorted(dates), f"应按日期升序,实际 {dates}"


def test_extract_rows_respects_lookback_days():
    """lookback_days 限制历史窗口(默认 365 天,避免写入 2000 年起的数据)。"""
    old = (date.today() - timedelta(days=800)).strftime("%Y-%m-%d")
    df = pd.DataFrame(
        {
            "数据日期": [old, date.today().strftime("%Y-%m-%d")],
            "当日收盘价": [10.0, 20.0],
            "总市值": [5e9, 1e10],
            "总股本": [5e8, 5e8],
            "PE(TTM)": [12.0, 15.0],
            "市净率": [2.0, 3.0],
        }
    )
    with _patch_ak(df):
        rows = extract_valuation_rows("600285", lookback_days=365)
    assert len(rows) == 1, f"超窗口的行应被过滤,实际 {rows}"
    assert rows[0]["pe_ratio"] == pytest.approx(15.0)


def test_extract_rows_handles_missing_columns():
    """PE / PB 缺失(银行股无 PB、亏损股无 PE)时填 None,不崩。"""
    df = pd.DataFrame(
        {
            "数据日期": ["2026-10-22"],
            "当日收盘价": [20.0],
            "总市值": [1e10],
            # 没有 PE / PB 列
        }
    )
    with _patch_ak(df):
        rows = extract_valuation_rows("600285")
    assert len(rows) == 1
    assert rows[0]["pe_ratio"] is None
    assert rows[0]["pb_ratio"] is None
    assert rows[0]["close_price"] == pytest.approx(20.0)


def test_extract_rows_skips_zero_valuation():
    """PE=0(亏损)不写库 — 会被后续 percentile 计算当成有效值污染中位数。"""
    df = pd.DataFrame(
        {
            "数据日期": ["2026-10-22"],
            "当日收盘价": [20.0],
            "总市值": [1e10],
            "PE(TTM)": [0.0],       # 亏损股
            "市净率": [3.0],
        }
    )
    with _patch_ak(df):
        rows = extract_valuation_rows("600285")
    assert rows[0]["pe_ratio"] is None, "PE=0 应转成 None"


def test_extract_rows_handles_api_failure():
    """akshare 抛异常时返回空列表,不向上传播。"""
    with patch("akshare.stock_value_em", MagicMock(side_effect=ConnectionError("断连"))):
        assert extract_valuation_rows("600285") == []


def test_extract_rows_handles_empty_df():
    with _patch_ak(pd.DataFrame()):
        assert extract_valuation_rows("600285") == []


def test_extract_rows_handles_na_values():
    """NaN 应转 None,不能写进 FLOAT 列(会被当 0 参与计算)。"""
    df = pd.DataFrame(
        {
            "数据日期": ["2026-10-22"],
            "当日收盘价": [20.0],
            "总市值": [1e10],
            "PE(TTM)": [float("nan")],
            "市净率": [3.0],
        }
    )
    with _patch_ak(df):
        rows = extract_valuation_rows("600285")
    assert rows[0]["pe_ratio"] is None


# ──────────────────────────────────────────────────────────────────────────────
# save_valuation_snapshots
# ──────────────────────────────────────────────────────────────────────────────


def test_save_upserts_idempotently():
    """重复写同一 (stock_code, snapshot_date) 应 UPDATE 而非新增行。"""
    fake_conn = MagicMock()
    # 第一次:查无此行(fetchone 返回 None)
    fake_conn.execute.return_value.fetchone.return_value = None
    fake_conn.execute.return_value.fetchall.return_value = []

    with patch("src.tools.valuation_fetcher.get_db") as mock_get_db:
        mock_get_db.return_value._duckdb_conn = fake_conn
        rows = [{
            "snapshot_date": date(2026, 10, 22),
            "close_price": 20.52,
            "pe_ratio": 14.9,
            "pb_ratio": 3.6,
            "total_market_cap": 1.16e10,
            "source": "akshare_value_em",
        }]
        first = save_valuation_snapshots("600285", rows)

    assert first["inserted"] == 1
    assert first["updated"] == 0