"""_ModelToDict.convert 直接单元测试 — 覆盖 6 个优先级分支。

源代码注释（src/db/repository/base.py）声明的优先级：
  1. None → None
  2. dict → 过滤掉 id 字段
  3. 带非空 __data__ 的对象（Peewee Model）→ __data__ 拷贝，剥离 id
  4. 带非空 _data 的对象（legacy / 测试 fixture 形态）→ dict(_data)，剥离 id
  5. 带非空 __dict__ 的对象（generic）→ __dict__ 拷贝，剥离 _* / id
  6. 兜底 None

每个测试只构造「刚好命中单一分支」的最小对象，避免相互串扰。
"""
import pytest

from src.db.repository.base import _ModelToDict


# ============================================================
# 测试辅助类 — 每个 helper 只暴露该分支需要的属性。
# ============================================================

class _WithUnderscoreData:
    """带 _data 字典的 legacy fixture 形态（覆盖优先级 4）。"""


class _WithDunderDictOnly:
    """只有 __dict__ 的最小 generic 对象（覆盖优先级 5）。"""


class _WithEmptyDunderData:
    """__data__ 是空 dict、__dict__ 有真实属性的对象（覆盖优先级 6）。"""


class _FakePeeweeModel:
    """仅暴露 __data__ 的 Peewee-like 模型（覆盖优先级 3 的 mock 路径）。

    避免引入真实的 peewee 依赖以保持单元测试速度。
    """


# ============================================================
# 优先级 1：None → None
# ============================================================

class TestConvertNone:
    def test_none_returns_none(self):
        assert _ModelToDict.convert(None) is None


# ============================================================
# 优先级 2：dict
# ============================================================

class TestConvertDict:
    def test_dict_without_id_passes_through(self):
        d = {"stock_code": "000423", "report_year": 2024}
        assert _ModelToDict.convert(d) == {
            "stock_code": "000423", "report_year": 2024,
        }

    def test_dict_with_id_key_strips_id(self):
        d = {"id": 99, "stock_code": "000423", "report_year": 2024}
        out = _ModelToDict.convert(d)
        assert out == {"stock_code": "000423", "report_year": 2024}
        assert "id" not in out

    def test_empty_dict_returns_empty_dict(self):
        assert _ModelToDict.convert({}) == {}

    def test_dict_does_not_mutate_input(self):
        d = {"id": 1, "x": 2}
        _ModelToDict.convert(d)
        # 原始对象没有被改写
        assert d == {"id": 1, "x": 2}


# ============================================================
# 优先级 3：带 __data__ 的对象（Peewee Model）
# ============================================================

class TestConvertWithDunderData:
    def test_fake_peewee_model_uses_dunder_data(self):
        """Mock 风格的 Peewee 实例：仅暴露 __data__。"""
        m = _FakePeeweeModel()
        m.__data__ = {
            "stock_code": "000423", "report_year": 2024, "id": 5,
        }
        out = _ModelToDict.convert(m)
        assert out == {"stock_code": "000423", "report_year": 2024}
        assert "id" not in out

    def test_fake_peewee_model_preserves_non_id_fields(self):
        m = _FakePeeweeModel()
        m.__data__ = {
            "stock_code": "000423",
            "cash_per_10_shares": 11.6,
            "bonus_shares_per_10": None,
        }
        out = _ModelToDict.convert(m)
        assert out["cash_per_10_shares"] == 11.6
        assert out["bonus_shares_per_10"] is None


# ============================================================
# 优先级 4：带 _data 的对象（legacy fixture）
# ============================================================

class TestConvertWithUnderscoreData:
    def test_legacy_data_attr_used(self):
        obj = _WithUnderscoreData()
        obj._data = {"x": 1, "y": 2, "id": 10}
        out = _ModelToDict.convert(obj)
        assert out == {"x": 1, "y": 2}
        assert "id" not in out

    def test_legacy_data_attr_handles_none_values(self):
        obj = _WithUnderscoreData()
        obj._data = {"a": "real", "b": None, "id": 99}
        out = _ModelToDict.convert(obj)
        assert out == {"a": "real", "b": None}


# ============================================================
# 优先级 5：generic 对象（仅 __dict__）
# ============================================================

class TestConvertWithDunderDictOnly:
    def test_generic_object_dunder_dict_used(self):
        obj = _WithDunderDictOnly()
        obj.stock_code = "000423"
        obj.report_year = 2024
        out = _ModelToDict.convert(obj)
        assert out == {"stock_code": "000423", "report_year": 2024}

    def test_generic_object_excludes_private_and_id(self):
        obj = _WithDunderDictOnly()
        obj.stock_code = "000423"
        obj._database = "secret"
        obj._dirty = True
        obj.id = 99
        out = _ModelToDict.convert(obj)
        assert out == {"stock_code": "000423"}
        assert "id" not in out
        assert "_database" not in out
        assert "_dirty" not in out


# ============================================================
# 优先级 6：fallback — __data__ 是空 dict 但 __dict__ 有真实属性
# ============================================================

class TestConvertEmptyDataFallsThrough:
    def test_empty_dunder_data_falls_through_to_dunder_dict(self):
        """__data__ 为空 → 不命中优先级 3；__dict__ 有内容 → 走优先级 5。"""
        obj = _WithEmptyDunderData()
        obj.__data__ = {}
        obj.stock_code = "000423"
        obj.report_year = 2024
        out = _ModelToDict.convert(obj)
        assert out == {"stock_code": "000423", "report_year": 2024}

    def test_empty_dunder_data_with_id_still_strips_id(self):
        """__data__ 为空 + __dict__ 含 id → 走 __dict__ 分支并剥离 id。"""
        obj = _WithEmptyDunderData()
        obj.__data__ = {}
        obj.stock_code = "000423"
        obj.id = 1
        out = _ModelToDict.convert(obj)
        assert out == {"stock_code": "000423"}
        assert "id" not in out


# ============================================================
# Peewee Model 集成路径：真实 CapitalChangeEvent（无 DB 写入）
# ============================================================

class TestConvertRealPeeweeModel:
    def test_real_peewee_model_uses_dunder_data_when_available(self):
        """若 Peewee 实例存在 __data__（DB 加载后），必须命中优先级 3。

        真实 DB 写入是覆盖范围外的副作用；本测试仅验证 __data__ 路径。
        """
        from src.db.models import CapitalChangeEvent

        m = CapitalChangeEvent(
            stock_code="000423", report_year=2024, report_period="FY",
            event_type="cash_dividend", event_date="2024-06-15",
            source="eastmoney",
        )
        # 模拟 peewee DB 加载：把数据放进 __data__。
        m.__data__ = {
            "id": 7,
            "stock_code": "000423",
            "report_year": 2024,
            "report_period": "FY",
            "event_type": "cash_dividend",
            "event_date": "2024-06-15",
            "source": "eastmoney",
        }
        out = _ModelToDict.convert(m)
        assert out is not None
        assert "id" not in out
        assert out["stock_code"] == "000423"
        assert out["report_year"] == 2024
        assert out["event_type"] == "cash_dividend"