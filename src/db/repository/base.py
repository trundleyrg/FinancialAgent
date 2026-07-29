"""BaseRepository + _ModelToDict — 所有 repo 共享基础。"""
from typing import Any, Dict, List, Optional

from src.db.db_connector import DatabaseConnector
from src.db.repository.keys import ReportKey


class _ModelToDict:
    """Peewee Model / dict → dict 的唯一站点。

    优先级：
    1. None → None
    2. dict → 过滤掉 id 字段（dict 形式的"id"剥离）
    3. 带非空 __dict__ 的对象（Peewee Model）→ __dict__ 拷贝，剥离 _* / id
    4. 带 _data 的对象 → dict(_data)
    5. 兜底 None
    """

    @staticmethod
    def convert(record: Any) -> Optional[Dict[str, Any]]:
        if record is None:
            return None
        if isinstance(record, dict):
            return {k: v for k, v in record.items() if k != "id"}
        if hasattr(record, "__dict__") and record.__dict__:
            return {
                k: v
                for k, v in record.__dict__.items()
                if not k.startswith("_") and k != "id"
            }
        if hasattr(record, "_data"):
            return dict(record._data)
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
