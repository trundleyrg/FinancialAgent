"""MetricRepository — financial_metrics 查询（含 report join）。"""
from typing import Any, Dict, List, Optional, Tuple

from src.db.db_connector import DatabaseConnector
from src.db.repository.base import BaseRepository, _ModelToDict
from src.db.repository.keys import ReportKey


class MetricRepository(BaseRepository):
    """财务指标（financial_metrics）。

    `get_metrics_by_report_id` 是底座；`get_metrics` / `get_report_with_metrics`
    走 ReportKey 自动解析 report_id。
    """

    @staticmethod
    def _extract_id(record: Any) -> Any:
        """从 raw record 提取主键 id（_ModelToDict.convert 会剥离 id，
        但 report join 时仍需 raw 的 id）。"""
        if isinstance(record, dict):
            return record.get("id")
        return getattr(record, "id", None)

    def _resolve_report(
        self, key: ReportKey,
    ) -> Optional[Tuple[Dict[str, Any], Any]]:
        """根据 ReportKey 解析 report，同时返回原始 report_id。"""
        records = self.connector.filter_records(
            "financial_reports", **key.to_filter()
        )
        if not records:
            return None
        report = _ModelToDict.convert(records[0])
        if not report:
            return None
        return report, self._extract_id(records[0])

    def get_metrics_by_report_id(self, report_id: int) -> List[Dict[str, Any]]:
        records = self.connector.filter_records(
            "financial_metrics", report_id=report_id
        )
        return [d for d in (_ModelToDict.convert(r) for r in records) if d]

    def get_metrics(self, key: ReportKey) -> List[Dict[str, Any]]:
        resolved = self._resolve_report(key)
        if resolved is None:
            return []
        _, report_id = resolved
        return self.get_metrics_by_report_id(report_id)

    def get_report_with_metrics(
        self, key: ReportKey,
    ) -> Optional[Dict[str, Any]]:
        resolved = self._resolve_report(key)
        if resolved is None:
            return None
        report, report_id = resolved
        return {
            "report": report,
            "metrics": self.get_metrics_by_report_id(report_id),
        }
