"""所有 repo 单元测试共享的 FakeConnector。"""
from typing import Any, Dict, List, Tuple

import pytest


def _get(obj: Any, key: str) -> Any:
    """兼容 dict 与带 __dict__ 的对象（FakeModel）。"""
    if isinstance(obj, dict):
        return obj.get(key)
    if hasattr(obj, "__dict__"):
        return obj.__dict__.get(key)
    return None


class FakeConnector:
    """进程内 DatabaseConnector 替身。仅实现 repo 实际调用的方法。

    返回普通 dict（不入 Peewee Model）— 让 _ModelToDict.convert 直接走
    isinstance(record, dict) 分支；个别测试再传 FakeModel 验证 __dict__ 路径。"""

    def __init__(self) -> None:
        self.data: Dict[str, List[Dict[str, Any]]] = {}
        self.filter_calls: List[Tuple[str, Dict[str, Any]]] = []

    # ----- 测试辅助 -----
    def seed(self, table_name: str, rows: List[Dict[str, Any]]) -> None:
        # dict 走拷贝路径；非 dict（如 FakeModel）原样保存以便后续测试 __dict__ 分支
        self.data[table_name] = [
            dict(r) if isinstance(r, dict) else r for r in rows
        ]

    # ----- DatabaseConnector 表面 -----
    def filter_records(self, table_name: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self.filter_calls.append((table_name, dict(kwargs)))
        rows = self.data.get(table_name, [])
        out: List[Dict[str, Any]] = []
        for r in rows:
            if all(_get(r, k) == v for k, v in kwargs.items()):
                out.append(dict(r) if isinstance(r, dict) else r)
        return out

    def get_all_companies(self) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        for r in self.data.get("financial_reports", []):
            key = r.get("stock_code")
            if key and key not in seen:
                seen[key] = {
                    "company_name": r.get("company_name"),
                    "stock_code": key,
                }
        return list(seen.values())

    def get_company_report_years(self, stock_code: str) -> List[int]:
        years = {r["report_year"] for r in self.data.get("financial_reports", [])
                 if r.get("stock_code") == stock_code and r.get("report_year") is not None}
        return sorted(years, reverse=True)

    def get_all_report_years(self) -> List[int]:
        years = {r["report_year"] for r in self.data.get("financial_reports", [])
                 if r.get("report_year") is not None}
        return sorted(years, reverse=True)


class FakeModel:
    """带 __dict__ 的最小对象，用于验证 _ModelToDict 走 __dict__ 分支。"""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


@pytest.fixture
def fake_connector() -> FakeConnector:
    return FakeConnector()