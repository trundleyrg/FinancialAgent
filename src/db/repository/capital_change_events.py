"""股本变动事件流查询（独立 repo，不入 _STATEMENT_REGISTRY）。"""
from typing import Any, Dict, List, Optional
from datetime import date

from src.db.db_connector import DatabaseConnector
from src.db.repository.base import BaseRepository
from src.db.repository.keys import ReportKey


class CapitalChangeEventRepository(BaseRepository):
    """股本变动事件流查询。"""

    def count_events(self, key: ReportKey) -> int:
        return len(self._query("capital_change_events", key))

    def list_events(
        self, key: ReportKey, event_type: Optional[str] = None,
        start_date: Optional[date] = None, end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        rows = self._query("capital_change_events", key)
        if event_type is not None:
            rows = [r for r in rows if r.get("event_type") == event_type]
        if start_date is not None:
            rows = [r for r in rows if _to_date(r.get("event_date")) and _to_date(r["event_date"]) >= start_date]
        if end_date is not None:
            rows = [r for r in rows if _to_date(r.get("event_date")) and _to_date(r["event_date"]) <= end_date]
        rows.sort(key=lambda r: r.get("event_date") or "", reverse=True)
        return rows

    def list_by_report_year(
        self, key: ReportKey, report_year: int,
    ) -> List[Dict[str, Any]]:
        rows = self._query("capital_change_events", key)
        out = [r for r in rows if r.get("report_year") == report_year]
        out.sort(key=lambda r: r.get("event_date") or "", reverse=True)
        return out

    def upsert_many(self, events: List[Dict[str, Any]]) -> int:
        if not events:
            return 0
        written = 0
        for ev in events:
            key = (ev["stock_code"], ev["event_date"], ev["event_type"])
            existing = self.connector.filter_records(
                "capital_change_events",
                stock_code=key[0], event_date=str(key[1]),
                event_type=key[2],
            )
            updates = {k: v for k, v in ev.items() if k != "id"}
            if existing:
                # 真实 DatabaseConnector 提供 filter-based update_records（kwargs 过滤）。
                # FakeConnector（test conftest）也提供同名方法。两者签名一致。
                if hasattr(self.connector, "update_records"):
                    self.connector.update_records(
                        "capital_change_events",
                        updates,
                        stock_code=key[0], event_date=str(key[1]),
                        event_type=key[2],
                    )
                else:
                    # 兜底：先查记录 id，再走按 id 更新的 update_record
                    for r in existing:
                        rid = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
                        if rid is None:
                            continue
                        self.connector.update_record(
                            "capital_change_events", rid, **updates,
                        )
            else:
                # insert_record 双签名兼容：
                # - 真实 DatabaseConnector：insert_record(table, **kwargs)
                # - FakeConnector：insert_record(table, record_dict)（占位 dict）
                try:
                    self.connector.insert_record("capital_change_events", **ev)
                except TypeError:
                    self.connector.insert_record("capital_change_events", ev)
            written += 1
        return written

    def aggregate_dividend_stats(
        self, key: ReportKey, years: int = 5,
    ) -> Dict[str, Any]:
        all_rows = self._query("capital_change_events", key)
        dividend_rows = [
            r for r in all_rows
            if r.get("event_type") in ("cash_dividend", "combination")
            and r.get("cash_per_10_shares") is not None
        ]
        dividend_rows.sort(key=lambda r: r.get("event_date") or "", reverse=True)
        cutoff_year = date.today().year - years + 1
        recent = [r for r in dividend_rows if _to_date(r.get("event_date")) and _to_date(r["event_date"]).year >= cutoff_year]

        cash_values = [float(r["cash_per_10_shares"]) for r in recent]

        # 把 events 序列化成 JSON 安全：date/datetime → ISO 字符串
        safe_events = []
        for r in recent[:10]:
            safe_events.append({
                k: (v.isoformat() if isinstance(v, date) else v)
                for k, v in r.items()
            })

        result: Dict[str, Any] = {
            "stock_code": key.stock_code,
            "years": years,
            "event_count": len(recent),
            "total_cash_per_10_shares": round(sum(cash_values), 4) if cash_values else 0.0,
            "average_cash_per_10_shares": round(sum(cash_values) / len(cash_values), 4) if cash_values else 0.0,
            "last_event_date": _to_date(recent[0]["event_date"]).isoformat() if recent else None,
            "last_cash_per_10_shares": cash_values[0] if cash_values else 0.0,
            "events": safe_events,
            "error": None,
        }
        return result


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))
