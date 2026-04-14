"""
红利股分析 Agent

本模块定义了红利股分析 Agent，专门用于分析和评估高分红、低波动的上市公司
财务状况和投资价值。红利股通常指那些业绩稳定、现金分红慷慨的公司，
如公用事业、银行、消费品巨头等。

核心功能：
1. 分红能力分析：评估公司分红的可持续性
   - 分红率（支付比率）
   - 股息率
   - 分红稳定性（连续分红年限）

2. 财务健康度分析
   - 经营现金流稳定性
   - 盈利质量
   - 资产负债结构

3. 股息率分析
   - 静态股息率
   - 动态股息率（基于预期收益）

4. 估值分析
   - PE 估值
   - PB 估值
   - DCF 现金流折现

输入：
- 公司财务报告数据（从数据库获取）
- 历史分红数据
- 行业分类信息

输出：
- 分红能力评分
- 财务健康度评分
- 股息率评级
- 估值建议
- 投资建议

依赖：
- langgraph: Agent 流程编排
- langchain: LLM 调用
- src.agents.state: Agent 状态定义
- src.agents.tools: 数据库查询和计算工具

作者：FinancialAgent Team
创建日期：2026-04-06
"""

from typing import Callable, Dict, Any
import json
import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from src.graph.state import FinancialState
from src.agents.tools.db_tools import get_all_financial_data
from src.agents.tools.calculation_tools import (
    calculate_profitability,
    calculate_liquidity,
    calculate_solvency
)
from src.agents.stock_tools.market_data_tool import get_stock_market_data, get_dividend_stats

logger = logging.getLogger("Agent.DividendStock")


# 红利股分析 System Prompt
SYSTEM_PROMPT = """你是一位专业的红利股分析师，专门分析高分红、稳定收益的上市公司。

你的职责是根据提供的财务数据，进行深入的红利股分析，包括：

1. 分红能力分析
   - 分红率（支付比率）：分红占净利润的比例，通常 30%-70% 为健康
   - 自由现金流覆盖率：自由现金流是否足够覆盖分红
   - 分红稳定性：连续分红年限，越长越好

2. 财务健康度分析
   - 经营现金流稳定性：多年经营现金流为正
   - 盈利质量：净利润与经营现金流匹配度
   - 资产负债结构：低负债或高资产覆盖

3. 股息率分析
   - 静态股息率：基于近一年分红的收益率
   - 股息率与无风险利率比较
   - 股息率在行业中的相对水平

4. 估值分析
   - PE 估值：是否处于历史低位
   - PB 估值：净资产是否扎实
   - 股价是否低于内在价值

5. 风险识别
   - 分红不可持续风险
   - 行业衰退风险
   - 政策变化风险

请基于以下财务数据进行分析，并返回结构化的分析结果。

财务数据：
{financial_data}

分析指标：
{analysis_metrics}

请以 JSON 格式返回分析结果，包含以下字段：
- dividend_yield: 股息率 (%)
- payout_ratio: 分红率 (%)
- dividend_stability_years: 连续分红年限
- cash_flow_coverage: 自由现金流对分红覆盖率
- financial_health_score: 财务健康度评分 (0-100)
- profitability: 盈利能力指标
  - gross_margin: 毛利率 (%)
  - net_margin: 净利率 (%)
  - roe: 净资产收益率 (%)
- solvency: 偿债能力指标
  - debt_to_asset: 资产负债率 (%)
- valuation: 估值指标
  - pe_ratio: 市盈率
  - pb_ratio: 市净率
- risk_factors: 风险因素列表
- investment_rating: 投资评级（BUY/HOLD/SELL）
- reasoning: 分析理由
"""

# 红利股分析 User Prompt 模板
USER_PROMPT = """请分析以下红利股公司的财务数据：

公司名称：{company_name}
股票代码：{stock_code}
报告期：{report_year}年 {report_period}

请基于以上数据给出详细的红利股分析报告。"""


def create_dividend_analysis(llm) -> Callable:
    """
    创建红利股分析 Agent

    Args:
        llm: LLM 实例，用于生成分析报告

    Returns:
        红利股分析节点函数
    """

    def dividend_analysis_node(state: FinancialState) -> FinancialState:
        """
        红利股分析节点

        从状态中获取公司信息，从数据库获取财务数据，
        调用 LLM 进行分析，更新状态中的 dividend_analysis 字段
        """
        # 从状态中获取公司信息
        company_name = state.get("company_name")
        stock_code = state.get("stock_code")
        report_year = state.get("report_year")
        report_period = state.get("report_period")

        if not company_name or not report_year:
            logger.error("缺少公司信息，无法进行红利股分析")
            return {
                "dividend_analysis": None,
                "error_msg": "缺少公司信息"
            }

        logger.info(f"开始红利股分析: {company_name} ({stock_code}) {report_year} {report_period}")

        try:
            # 1. 获取财务数据
            financial_data = get_all_financial_data(
                company_name=company_name,
                year=report_year,
                period=report_period
            )

            balance_sheet = financial_data.get("balance_sheet", {})
            income_statement = financial_data.get("income_statement", {})
            cash_flow = financial_data.get("cash_flow", {})

            # 2. 计算分析指标
            profitability = calculate_profitability(income_statement, balance_sheet)
            liquidity = calculate_liquidity(balance_sheet)
            solvency = calculate_solvency(balance_sheet, income_statement)

            # 3. 提取分红相关数据（现金流量表 + akshare 历史分红）
            dividend_info = _extract_dividend_info(financial_data)

            # 4. 获取市场数据（股价、PE、PB、股息率）
            market_data: Dict[str, Any] = {}
            if stock_code:
                market_data = get_stock_market_data(stock_code)
                dividend_stats = get_dividend_stats(stock_code, years=5)
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

            # 4. 构建 prompt
            system_prompt = SYSTEM_PROMPT.format(
                financial_data=json.dumps(financial_data, ensure_ascii=False, indent=2),
                analysis_metrics=json.dumps(analysis_metrics, ensure_ascii=False, indent=2)
            )

            user_prompt = USER_PROMPT.format(
                company_name=company_name,
                stock_code=stock_code or "未知",
                report_year=report_year,
                report_period=report_period or "未知"
            )

            # 5. 调用 LLM
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", user_prompt)
            ])

            # 使用 JSON 输出解析器
            parser = JsonOutputParser()
            chain = prompt | llm | parser

            result = chain.invoke({})

            logger.info(f"红利股分析完成: {company_name}, 评级: {result.get('investment_rating', 'UNKNOWN')}")

            return {
                "dividend_analysis": result
            }

        except Exception as e:
            logger.error(f"红利股分析失败: {e}")
            return {
                "dividend_analysis": None,
                "error_msg": f"红利股分析失败: {str(e)}"
            }

    return dividend_analysis_node


def _extract_dividend_info(financial_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    从财务数据中提取分红相关信息

    数据来源优先级：
    1. 现金流量表 cash_for_dividend_and_interest（实际现金分红支出）
    2. 计算自由现金流 = 经营活动现金流 - 购建固定资产现金支出

    Args:
        financial_data: 财务数据字典（含 balance_sheet / income_statement / cash_flow）

    Returns:
        分红信息字典
    """
    income_statement = financial_data.get("income_statement", {})
    cash_flow = financial_data.get("cash_flow", {})

    net_profit = income_statement.get("net_profit", 0) or 0
    operating_cash_flow = cash_flow.get("net_cash_from_operations", 0) or cash_flow.get("operating_cash_flow", 0) or 0

    # 实际现金分红支出（来自现金流量表"分配股利、利润或偿付利息支付的现金"）
    cash_dividend_paid = cash_flow.get("cash_for_dividend_and_interest", 0) or 0

    # 自由现金流 = 经营现金流 - 购建固定资产等资本支出
    capex = cash_flow.get("cash_for_fixed_assets", 0) or 0
    free_cash_flow = operating_cash_flow - capex

    payout_ratio = (cash_dividend_paid / net_profit * 100) if net_profit > 0 else 0
    fcf_coverage = (free_cash_flow / cash_dividend_paid) if cash_dividend_paid > 0 else 0

    return {
        "net_profit": net_profit,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
        "cash_dividend_paid": cash_dividend_paid,   # 实际现金分红支出（元）
        "payout_ratio": round(payout_ratio, 2),      # 分红率（%）
        "fcf_coverage": round(fcf_coverage, 2),      # 自由现金流对分红覆盖倍数
    }