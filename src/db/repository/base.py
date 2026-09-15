"""BaseRepository + _ModelToDict — 所有 repo 共享基础。"""
from typing import Any, Dict, List, Optional

from src.db.db_connector import DatabaseConnector
from src.db.repository.keys import ReportKey


class _ModelToDict:
    """Peewee Model / dict → dict 的唯一站点。

    优先级：
    1. None → None
    2. dict → 过滤掉 id 字段（dict 形式的"id"剥离）
    3. 带非空 __data__ 的对象（Peewee Model）→ __data__ 拷贝，剥离 id
    4. 带非空 _data 的对象（legacy / 测试 fixture 形态）→ dict(_data)，剥离 id
    5. 带非空 __dict__ 的对象（generic）→ __dict__ 拷贝，剥离 _* / id
    6. 兜底 None
    """

    @staticmethod
    def convert(record: Any) -> Optional[Dict[str, Any]]:
        if record is None:
            return None
        if isinstance(record, dict):
            return {k: v for k, v in record.items() if k != "id"}
        # Peewee stores column data in `__data__` (instance attribute, not name-mangled)
        if hasattr(record, "__data__") and isinstance(record.__data__, dict) and record.__data__:
            return {k: v for k, v in record.__data__.items() if k != "id"}
        # Generic object with `_data` dict (legacy / test fixture shape).
        if hasattr(record, "_data") and isinstance(record._data, dict) and record._data:
            return {k: v for k, v in record._data.items() if k != "id"}
        # Generic object fallback (non-Peewee, no _data).
        if hasattr(record, "__dict__") and record.__dict__:
            return {
                k: v
                for k, v in record.__dict__.items()
                if not k.startswith("_") and k != "id"
            }
        return None


class BaseRepository:
    """所有 repo 的基类。提供：
    - connector 持有
    - company_name → stock_code 显式解析
    - _query / _query_first 统一 dict 转换助手
    """

    def __init__(self, connector: DatabaseConnector) -> None:
        self.connector = connector

    def resolve_stock_code(self, key: ReportKey) -> Optional[str]:
        if key.stock_code:
            return key.stock_code
        if not key.company_name:
            return None
        records = self.connector.filter_records(
            "financial_reports", company_name=key.company_name
        )
        if not records:
            return None
        first = _ModelToDict.convert(records[0])
        return first["stock_code"] if first else None

    def _query(self, table_name: str, key: ReportKey) -> List[Dict[str, Any]]:
        records = self.connector.filter_records(table_name, **key.to_filter())
        return [d for d in (_ModelToDict.convert(r) for r in records) if d]

    def _query_first(self, table_name: str, key: ReportKey) -> Optional[Dict[str, Any]]:
        results = self._query(table_name, key)
        return results[0] if results else None
