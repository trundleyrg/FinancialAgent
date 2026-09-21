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
    compute_dividend_stability_years,
    extract_dividend_info,
    get_dividend_stats_with_fallback,
)


def _fetch_total_shares(
    stock_code: str, year: int, period: str | None,
) -> float | None:
    """从 share_structure 表读 total_shares（股）。"""
    if not stock_code:
        return None
    try:
        row = get_db()._duckdb_conn.execute(
            """
            SELECT total_shares FROM share_structure
            WHERE stock_code = ? AND report_year = ? AND report_period = ?
            """,
            [stock_code, year, period or "FY"],
        ).fetchone()
    except Exception:
        return None
    if row and row[0] is not None:
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return None
    return None
from src.tools.calculation_tools import (
    calculate_liquidity,
    calculate_profitability,
    calculate_solvency,
)
from src.tools.db_tools import get_all_financial_data
from src.tools.market_data_tool import get_stock_market_data
from src.db.db_connector import get_db

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

            # 扁平化：从 pe_pb_history 取最近一日的 close/pb，
            # basic_info 不直接含 PE/PB/市值，置为 None 让 LLM 自行处理。
            pe_pb_history = market_data.get("pe_pb_history") or []
            latest = next(
                (r for r in reversed(pe_pb_history) if isinstance(r, dict) and not r.get("error")),
                None,
            )
            current_price = (latest or {}).get("close")
            pb_ratio = (latest or {}).get("pb")
            dividend_info["current_price"] = current_price
            dividend_info["pb_ratio"] = pb_ratio
            dividend_info["pe_ratio"] = None  # akshare get_stock_pe_pb_history 不返回 PE
            dividend_info["market_cap"] = None  # 同上

            # 总股本从 share_structure 取（缺失时 dividend_yield 无法准确算）
            total_shares = _fetch_total_shares(stock_code, report_year, report_period)
            dividend_info["total_shares"] = total_shares

            # 连续分红年限：从 capital_change_events 反推
            stability_years = compute_dividend_stability_years(
                stock_code, report_year, report_period or "FY",
            )
            dividend_info["dividend_stability_years"] = stability_years

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
        # 把 system_msg / user_msg 套一层 {var} 模板，避免 ChatPromptTemplate
        # 把 JSON 中的 {x: y} 当成占位符解析（f-string 嵌套字段报错）。
        chain = (
            ChatPromptTemplate.from_messages([
                ("system", "{system}"),
                ("human", "{user}"),
            ])
            | llm | JsonOutputParser()
        )
        result = chain.invoke({"system": system_msg, "user": user_msg})

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