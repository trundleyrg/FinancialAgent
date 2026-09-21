"""投资建议汇总 skill。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.graph.state import FinancialState
from src.skills._loader import read_skill_description

logger = logging.getLogger("Skills.Summary")

SKILL_DIR = Path(__file__).parent

_INSTRUCTION = SKILL_DIR.joinpath("SKILL.md").read_text(encoding="utf-8")
_USER_PROMPT = (
    "公司名称：{company_name}\n"
    "股票代码：{stock_code}\n"
    "报告期：{report_year}年 {report_period}\n"
    "\n请结合周期股分析、股息/红利股分析与基本面分析的结果，给出综合的投资建议。"
)

DESCRIPTION = read_skill_description(SKILL_DIR / "SKILL.md")


def run(state: FinancialState, llm) -> Dict[str, Any]:
    """投资建议汇总 skill；返回 state delta。

    字段语义与原 `create_summary_agent(llm)` 节点保持一致：
    - 成功：`{"summary": <dict>, "status": "completed"}`
    - 失败：`{"summary": None, "error_msg": "..."}`
    """
    company_name = state.get("company_name")
    stock_code = state.get("stock_code")
    report_year = state.get("report_year")
    report_period = state.get("report_period")

    # 读取三方面的分析结果
    cyclical_analysis = state.get("cyclical_analysis")
    dividend_analysis = state.get("dividend_analysis")
    fundamental_analysis = state.get("fundamental_analysis")

    if not any([cyclical_analysis, dividend_analysis, fundamental_analysis]):
        logger.error("缺少前置分析结果，无法进行总结")
        return {
            "summary": None,
            "error_msg": "缺少前置分析结果",
        }

    logger.info("开始总结分析: %s (%s)", company_name, stock_code)

    try:
        # 1. 拼装 prompt（SKILL.md 指令 + 三方面分析结果）
        system_msg = (
            _INSTRUCTION
            + "\n\n## 周期股分析结果\n" + json.dumps(cyclical_analysis or {}, ensure_ascii=False, indent=2)
            + "\n\n## 红利股分析结果\n" + json.dumps(dividend_analysis or {}, ensure_ascii=False, indent=2)
            + "\n\n## 基本面分析结果\n" + json.dumps(fundamental_analysis or {}, ensure_ascii=False, indent=2)
        )
        user_msg = _USER_PROMPT.format(
            company_name=company_name or "未知",
            stock_code=stock_code or "未知",
            report_year=report_year or "未知",
            report_period=report_period or "未知",
        )

        # 2. 调用 LLM（JSON 输出）
        chain = (
            ChatPromptTemplate.from_messages([("system", system_msg), ("user", user_msg)])
            | llm | JsonOutputParser()
        )
        result = chain.invoke({})

        # 3. 注入时间戳（与原 summary_agent 行为一致）
        result["analysis_timestamp"] = datetime.now().isoformat()

        logger.info(
            "总结分析完成: %s, 综合评级: %s",
            company_name, result.get("combined_rating", "UNKNOWN"),
        )

        return {
            "summary": result,
            "status": "completed",
        }

    except Exception as e:
        logger.error("总结分析失败: %s", e)
        return {
            "summary": None,
            "error_msg": f"总结分析失败: {e}",
        }
