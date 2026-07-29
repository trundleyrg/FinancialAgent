# src/db/repository/__init__.py
"""Repository layer — 项目唯一的读查询入口。

消费方使用方式：
    from src.db import ReportKey, StatementRepository, ReportRepository
    from src.db.db_connector import get_db

    db = get_db()
    repo = StatementRepository(db)
    rows = repo.get_multi_year_statement(
        ReportKey(stock_code="000423", period="FY"),
        "consolidated_balance_sheet",
        start_year=2020, end_year=2024,
    )
"""
from src.db.repository.keys import ReportKey
from src.db.repository.base import BaseRepository, _ModelToDict
from src.db.repository.reports import ReportRepository
from src.db.repository.statements import (
    StatementRepository,
    StatementSpec,
    register_statement,
    unregister_statement,
    list_statements,
)
from src.db.repository.metrics import MetricRepository
from src.db.repository.share_structure import ShareStructureRepository

__all__ = [
    "ReportKey",
    "BaseRepository",
    "ReportRepository",
    "StatementRepository",
    "MetricRepository",
    "ShareStructureRepository",
    "StatementSpec",
    "register_statement",
    "unregister_statement",
    "list_statements",
]
