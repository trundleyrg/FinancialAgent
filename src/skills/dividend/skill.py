"""红利股分析 skill。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.graph.state import FinancialState
from src.skills._loader import read_skill_description
from src.skills.dividend.tools import (
    extract_dividend_info,
    get_dividend_stats_with_fallback,
)
from src.tools.calculation_tools import (
    calculate_liquidity,
    calculate_profitability,
    calculate_solvency,
)
from src.tools.db_tools import get_all_financial_data
from src.tools.market_data_tool import get_stock_market_data

logger = logging.getLogger("Skills.Dividend")

SKILL_DIR = Path(__file__).parent

_INSTRUCTION = SKILL_DIR.joinpath("SKILL.md").read_text(encoding="utf-8")
_USER_PROMPT = (
    "公司名称：{company_name}\n"
    "股票代码：{stock_code}\n"
    "报告期：{report_year}年 {report_period}\n"
    "\n请基于以上信息与下方财务/分析指标，给出详细的红利股分析报告。"
)

DESCRIPTION = read_skill_description(SKILL_DIR / "SKILL.md")


def run(state: FinancialState, llm) -> Dict[str, Any]:
    """红利股分析 skill；返回 state delta。

    字段语义与原 `create_dividend_analysis(llm)` 节点保持一致：
    - 成功：`{"dividend_analysis": <dict>}`
    - 失败：`{"dividend_analysis": None, "error_msg": "..."}`
    """
    company_name = state.get("company_name")
    stock_code = state.get("stock_code")
    report_year = state.get("report_year")
    report_period = state.get("report_period")

    if not company_name or not report_year:
        logger.error("缺少公司信息，无法进行红利股分析")
        return {"dividend_analysis": None, "error_msg": "缺少公司信息"}

    logger.info(
        "开始红利股分析: %s (%s) %s %s",
        company_name, stock_code, report_year, report_period,
    )

    try:
        # 1. 获取财务数据
        financial_data = get_all_financial_data(
            company_name=company_name,
            year=report_year,
            period=report_period,
        )

        balance_sheet = financial_data.get("balance_sheet", {})
        income_statement = financial_data.get("income_statement", {})
        cash_flow = financial_data.get("cash_flow", {})

        # 2. 计算分析指标
        profitability = calculate_profitability(income_statement, balance_sheet)
        liquidity = calculate_liquidity(balance_sheet)
        solvency = calculate_solvency(balance_sheet, income_statement)

        # 3. 提取分红相关数据（现金流量表 + akshare 历史分红）
        dividend_info = extract_dividend_info(financial_data)

        # 4. 获取市场数据（股价、PE、PB、股息率）
        market_data: Dict[str, Any] = {}
        if stock_code:
            market_data = get_stock_market_data(stock_code)
            dividend_stats = get_dividend_stats_with_fallback(stock_code, years=5)
            dividend_info["market_dividend_stats"] = dividend_stats
            dividend_info["pe_ratio"] = market_data.get("pe_ratio", 0.0)
            dividend_info["pb_ratio"] = market_data.get("pb_ratio", 0.0)
            dividend_info["current_price"] = market_data.get("current_price", 0.0)
            dividend_info["market_cap"] = market_data.get("market_cap", 0.0)

        analysis_metrics = {
            "profitability": profitability,
            "liquidity": liquidity,
            "solvency": solvency,
            "dividend_info": dividend_info,
            "market_data": market_data,
        }

        # 5. 拼装 prompt（SKILL.md 指令 + 财务数据 + 分析指标）
        system_msg = (
            _INSTRUCTION
            + "\n\n## 财务数据\n" + json.dumps(financial_data, ensure_ascii=False, indent=2)
            + "\n\n## 分析指标\n" + json.dumps(analysis_metrics, ensure_ascii=False, indent=2)
        )
        user_msg = _USER_PROMPT.format(
            company_name=company_name,
            stock_code=stock_code or "未知",
            report_year=report_year,
            report_period=report_period or "未知",
        )

        # 6. 调用 LLM（JSON 输出）
        chain = (
            ChatPromptTemplate.from_messages([("system", system_msg), ("user", user_msg)])
            | llm | JsonOutputParser()
        )
        result = chain.invoke({})

        logger.info(
            "红利股分析完成: %s, 评级: %s",
            company_name, result.get("investment_rating", "UNKNOWN"),
        )

        return {"dividend_analysis": result}

    except Exception as e:
        logger.error("红利股分析失败: %s", e)
        return {
            "dividend_analysis": None,
            "error_msg": f"红利股分析失败: {e}",
        }