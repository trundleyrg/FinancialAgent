"""Skill 结果通用写表工具。

用途：各 skill（dividend / cyclical / fundamental / summary）在 run() 末尾
调用本工具，把 LLM 输出的 dict 持久化到 `skill_analysis_results` 表。

设计原则：
- 失败仅日志，绝不抛异常 — skill 主流程不应被写库错误打断
- 单条 INSERT 写入；不依赖 peewee 元类，直接走 duckdb 连接（与其它 fetcher 风格一致）
- 不替换原有 skill 返回结构，调用方继续返回 `{<skill>_analysis: result}`
- 复用相同行 schema，rating / summary 自动从结果 dict 抽取
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from src.db.db_connector import get_db
from src.db.models import SkillAnalysisResult
from src.utils.logger import manager

logger = manager.get_logger("Tools.SkillResultWriter", "skill_results.log")


_RATING_KEYS = (
    "investment_rating",
    "rating",
    "cyclical_rating",
    "dividend_rating",
    "fundamental_rating",
)

_SUMMARY_KEYS = (
    "reasoning",
    "summary",
    "analysis_summary",
    "conclusion",
)


def _json_default(obj: Any) -> Any:
    """JSON 不支持的类型 → 字符串 / isoformat。"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    return str(obj)


def _safe_json_dumps(payload: Any) -> str:
    """尽量把 payload 序列化；失败时降级为 repr。"""
    try:
        return json.dumps(payload, ensure_ascii=False, default=_json_default)
    except Exception as exc:
        logger.warning("payload 序列化失败，降级到 repr: %s", exc)
        return json.dumps({"repr": repr(payload)}, ensure_ascii=False)


def _extract_rating(result: Dict[str, Any]) -> Optional[str]:
    """从结果 dict 抽取评级字符串；找不到返回 None。"""
    if not isinstance(result, dict):
        return None
    for key in _RATING_KEYS:
        val = result.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _extract_summary(result: Dict[str, Any]) -> Optional[str]:
    """从结果 dict 抽取摘要 / reasoning。"""
    if not isinstance(result, dict):
        return None
    for key in _SUMMARY_KEYS:
        val = result.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def save_skill_result(
    skill_name: str,
    state: Dict[str, Any],
    result: Dict[str, Any],
) -> bool:
    """把 skill 输出写入 skill_analysis_results 表。

    Args:
        skill_name: 'dividend' / 'cyclical' / 'fundamental' / 'summary'
        state:      FinancialState dict（含 company_name / stock_code / report_year / report_period）
        result:     skill 产出的 dict；为空或非 dict 时直接返回 False（不算错）

    Returns:
        True  写入成功
        False result 为空 / 不可序列化 / DB 异常（异常已被日志记录）
    """
    if not isinstance(result, dict) or not result:
        logger.debug("跳过保存：%s result 为空或非 dict", skill_name)
        return False

    row = {
        "skill_name": skill_name,
        "company_name": state.get("company_name"),
        "stock_code": state.get("stock_code"),
        "report_year": state.get("report_year"),
        "report_period": state.get("report_period"),
        "investment_rating": _extract_rating(result),
        "summary": _extract_summary(result),
        "payload_json": _safe_json_dumps(result),
    }

    try:
        conn = get_db()._duckdb_conn
        conn.execute(
            """
            INSERT INTO skill_analysis_results
                (skill_name, company_name, stock_code, report_year, report_period,
                 investment_rating, summary, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["skill_name"], row["company_name"], row["stock_code"],
                row["report_year"], row["report_period"],
                row["investment_rating"], row["summary"], row["payload_json"],
            ],
        )
        logger.info(
            "写入 skill_analysis_results: skill=%s stock=%s year=%s rating=%s",
            skill_name, row["stock_code"], row["report_year"], row["investment_rating"],
        )
        return True
    except Exception as exc:
        logger.error(
            "写入 skill_analysis_results 失败 (skill=%s stock=%s): %s",
            skill_name, row.get("stock_code"), exc,
        )
        return False


def save_skill_result_from_delta(
    skill_name: str,
    state: Dict[str, Any],
    delta: Dict[str, Any],
) -> bool:
    """从 skill run() 返回的 delta 自动定位 `<skill>_analysis` key。

    - 例如 dividend skill 返回 {"dividend_analysis": {...}, "error_msg": "..."}
    - 本函数会自动取 dividend_analysis 字段作为 result 写入；遇到 error_msg 跳过。
    - 兼容 summary skill 的 analysis 字段名差异：如果 `<skill>_analysis` 不存在，
      退化到 `analysis` / `<skill>_summary`。
    """
    if not isinstance(delta, dict):
        return False
    if delta.get("error_msg"):
        logger.debug("跳过保存：%s 含 error_msg", skill_name)
        return False

    candidate_keys = (
        f"{skill_name}_analysis",
        "analysis",
        f"{skill_name}_summary",
    )
    result = None
    for k in candidate_keys:
        if k in delta and isinstance(delta[k], dict):
            result = delta[k]
            break
    if result is None:
        logger.debug("跳过保存：%s delta 中未找到分析 dict", skill_name)
        return False
    return save_skill_result(skill_name, state, result)
