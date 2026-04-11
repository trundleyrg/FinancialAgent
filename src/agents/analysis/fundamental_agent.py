"""
基本面分析 Agent

本模块定义了基本面分析 Agent，用于分析和评估任何行业上市公司的
财务状况和投资价值。基本面分析适用于所有行业，不局限于周期性行业。

核心功能：
1. 盈利能力分析：评估公司赚钱的能力
   - 毛利率、净利率分析
   - ROE（净资产收益率）、ROA（资产收益率）
   - 费用率控制能力

2. 流动性分析：评估公司短期偿债能力
   - 流动比率、速动比率
   - 现金比率
   - 营运资本管理

3. 偿债能力分析：评估公司长期财务稳健性
   - 资产负债率
   - 产权比率
   - 利息保障倍数

4. 成长性分析：评估公司发展趋势
   - 营收增长率
   - 净利润增长率
   - 资产扩张速度

5. 运营效率分析：评估公司资产利用效率
   - 资产周转率
   - 存货周转天数
   - 应收账款周转天数

输入：
- 公司财务报告数据（从数据库获取）
- 行业平均水平（可选对照）

输出：
- 盈利能力评分
- 流动性评分
- 偿债能力评分
- 成长性评分
- 运营效率评分
- 综合投资评级

依赖：
- langgraph: Agent 流程编排
- langchain: LLM 调用
- src.agents.state: Agent 状态定义
- src.agents.tools: 数据库查询和计算工具

作者：FinancialAgent Team
创建日期：2026-04-03
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
    calculate_solvency,
    calculate_growth
)

logger = logging.getLogger("Agent.Fundamental")


# 基本面分析 System Prompt
SYSTEM_PROMPT = """你是一位专业的基本面分析师，通过分析上市公司的财务数据评估其投资价值。

你的职责是对任何行业的公司进行全面的基本面分析，包括：

1. 盈利能力分析
   - 毛利率：衡量核心业务的盈利能力
   - 净利率：衡量最终赚钱能力
   - ROE（净资产收益率）：衡量股东权益的回报水平
   - ROA（资产收益率）：衡量资产的赚钱效率
   - 费用率：费用控制能力的体现

2. 流动性分析
   - 流动比率：短期偿债能力（通常 > 1.5 为好）
   - 速动比率：去掉存货后的短期偿债能力（通常 > 1 为好）
   - 现金比率：现金对流动负债的覆盖能力

3. 偿债能力分析
   - 资产负债率：财务杠杆水平（通常 40-60% 为合理）
   - 产权比率：负债与所有者权益的比例
   - 利息保障倍数：利润对利息支出的覆盖能力

4. 成长性分析
   - 营收增长率：收入增长速度
   - 净利润增长率：利润增长速度
   - 增长质量：营收增长是否转化为利润增长

5. 运营效率分析
   - 资产周转率：资产利用效率
   - 存货周转天数：库存管理能力
   - 应收账款周转天数：回款能力

请基于以下财务数据进行分析，并返回结构化的分析结果。

财务数据：
{financial_data}

分析指标：
{analysis_metrics}

请以 JSON 格式返回分析结果，包含以下字段：
- profitability: 盈利能力指标
  - gross_margin: 毛利率 (%)
  - net_margin: 净利率 (%)
  - roe: 净资产收益率 (%)
  - roa: 资产收益率 (%)
- liquidity: 流动性指标
  - current_ratio: 流动比率
  - quick_ratio: 速动比率
  - cash_ratio: 现金比率
- solvency: 偿债能力指标
  - debt_to_asset: 资产负债率 (%)
  - debt_to_equity: 产权比率
  - interest_coverage: 利息保障倍数
- growth: 成长性指标
  - revenue_growth: 营收增长率 (%)
  - profit_growth: 净利润增长率 (%)
- efficiency: 运营效率指标
  - asset_turnover: 资产周转率
  - inventory_turnover_days: 存货周转天数
- investment_rating: 投资评级（BUY/HOLD/SELL）
- reasoning: 分析理由
"""

# 基本面分析 User Prompt 模板
USER_PROMPT = """请分析以下公司的基本面数据：

公司名称：{company_name}
股票代码：{stock_code}
报告期：{report_year}年 {report_period}

请基于以上数据给出详细的基本面分析报告。"""


def create_fundamental_analysis(llm) -> Callable:
    """
    创建基本面分析 Agent

    Args:
        llm: LLM 实例，用于生成分析报告

    Returns:
        基本面分析节点函数
    """

    def fundamental_analysis_node(state: FinancialState) -> FinancialState:
        """
        基本面分析节点

        从状态中获取公司信息，从数据库获取财务数据，
        调用 LLM 进行分析，更新状态中的 fundamental_analysis 字段
        """
        # 从状态中获取公司信息
        company_name = state.get("company_name")
        stock_code = state.get("stock_code")
        report_year = state.get("report_year")
        report_period = state.get("report_period")

        if not company_name or not report_year:
            logger.error("缺少公司信息，无法进行基本面分析")
            return {
                "fundamental_analysis": None,
                "error_msg": "缺少公司信息"
            }

        logger.info(f"开始基本面分析: {company_name} ({stock_code}) {report_year} {report_period}")

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
            profitability = calculate_profitability(income_statement)
            liquidity = calculate_liquidity(balance_sheet)
            solvency = calculate_solvency(balance_sheet, income_statement)
            growth = calculate_growth(financial_data)

            analysis_metrics = {
                "profitability": profitability,
                "liquidity": liquidity,
                "solvency": solvency,
                "growth": growth
            }

            # 3. 构建 prompt
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

            # 4. 调用 LLM
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", user_prompt)
            ])

            # 使用 JSON 输出解析器
            parser = JsonOutputParser()
            chain = prompt | llm | parser

            result = chain.invoke({})

            logger.info(f"基本面分析完成: {company_name}, 评级: {result.get('investment_rating', 'UNKNOWN')}")

            return {
                "fundamental_analysis": result
            }

        except Exception as e:
            logger.error(f"基本面分析失败: {e}")
            return {
                "fundamental_analysis": None,
                "error_msg": f"基本面分析失败: {str(e)}"
            }

    return fundamental_analysis_node
