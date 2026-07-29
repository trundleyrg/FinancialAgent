"""ShareStructureRepository — 股份结构快照（变动后）。"""
from typing import Any, Dict, List, Optional

from src.db.db_connector import DatabaseConnector
from src.db.repository.base import BaseRepository
from src.db.repository.keys import ReportKey


class ShareStructureRepository(BaseRepository):
    """股份结构快照（变动后）。与三表同地址形态，但独立 repo（不进
    _STATEMENT_REGISTRY，因为不是三表形态）。"""

    def get_structure(self, key: ReportKey) -> Optional[Dict[str, Any]]:
        return self._query_first("share_structure", key)

    def list_structures(self, key: ReportKey) -> List[Dict[str, Any]]:
        return self._query("share_structure", key)

    def get_multi_year_structures(
        self, key: ReportKey, start_year: int, end_year: int,
    ) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}
        for y in range(start_year, end_year + 1):
            d = self.get_structure(key.with_year(y))
            if d is not None:
                out[y] = d
        return out
