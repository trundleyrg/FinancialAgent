"""
周期股分析 Agent

本模块定义了周期股分析 Agent，专门用于分析和评估周期性行业上市公司的
财务状况和投资价值。周期股通常指那些盈利随经济周期波动较大的行业，
如钢铁、煤炭、化工、有色金属、航运、建筑等。

核心功能：
1. 行业周期定位：判断当前所处经济周期阶段（复苏、繁荣、衰退、萧条）
2. 财务指标分析：针对周期股的特殊财务指标分析
   - 产能利用率分析
   - 存货周转率与价格波动关系
   - 资本支出（CAPEX）周期分析
   - 现金流在周期各阶段的表现
3. 估值模型适配：使用适合周期股的估值方法
   - 市净率（PB）分析
   - 周期调整市盈率（CAPE）
   - 重置成本法估值
4. 风险识别：识别周期股特有的投资风险
   - 产能扩张风险
   - 大宗商品价格波动风险
   - 政策调控风险

输入：
- 公司财务报告数据（从数据库获取）
- 行业分类信息
- 宏观经济指标（可选）

输出：
- 周期定位分析结果
- 财务健康度评分
- 估值建议
- 风险提示

依赖：
- langgraph: Agent 流程编排
- langchain: LLM 调用
- src.agents.state: Agent 状态定义
- src.agents.tools: 数据库查询和计算工具

作者：FinancialAgent Team
创建日期：2026-03-27
"""

from typing import Callable, Dict, Any
import json
import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser

from src.graph.state import FinancialState
from src.agents.tools.db_tools import get_all_financial_data
from src.agents.tools.calculation_tools import (
    calculate_profitability,
    calculate_liquidity,
    calculate_solvency,
    calculate_cyclical_metrics,
)
from src.agents.stock_tools.market_data_tool import get_stock_market_data

logger = logging.getLogger("Agent.CyclicalStock")


# 周期股分析 System Prompt
SYSTEM_PROMPT = """你是一位专业的周期股分析师，专门从周期角度分析上市公司的财务状况和投资价值。

你的职责是根据提供的财务数据，进行深入的周期股分析，包括：

1. 行业周期定位
   - 复苏期：需求回升、产能利用率提高、价格上涨
   - 繁荣期：需求旺盛、利润率最高、资本扩张
   - 衰退期：需求下降、价格下跌、产能过剩
   - 萧条期：需求低迷、普遍亏损、去产能

2. 周期股专用指标分析
   - 产能利用率：判断当前产能是否过剩或不足
   - 存货周转：分析库存周期与价格波动关系
   - CAPEX 强度：判断公司所处扩张/收缩周期
   - 现金流健康度：经营现金流与净利润的匹配程度

3. 适合周期股的估值方法
   - 市净率（PB）：周期股底部估值指标
   - 周期调整市盈率（CAPE）：考虑长期均值回归
   - 重置成本法：净资产价值评估

4. 风险识别
   - 产能扩张风险：过度扩张导致的供给过剩
   - 大宗商品价格波动风险：原材料和产品价格剧烈波动
   - 政策调控风险：环保、去产能等政策影响
   - 财务杠杆风险：高负债率在经济下行期的压力

请基于以下财务数据进行分析，并返回结构化的分析结果。

财务数据：
{financial_data}

分析指标：
{analysis_metrics}

请以 JSON 格式返回分析结果，包含以下字段：
- cycle_position: 当前周期位置（复苏/繁荣/衰退/萧条）
- capacity_utilization: 产能利用率 (0-100%)
- inventory_turnover_days: 存货周转天数
- capex_intensity: 资本支出强度（高/中/低）
- cash_flow_health: 现金流健康度评分 (0-100)
- pb_ratio: 市净率
- cape_ratio: 周期调整市盈率
- risk_factors: 风险因素列表
- investment_rating: 投资评级（BUY/HOLD/SELL）
- reasoning: 分析理由
"""

# 周期股分析 User Prompt 模板
USER_PROMPT = """请分析以下周期性行业公司的财务数据：

公司名称：{company_name}
股票代码：{stock_code}
报告期：{report_year}年 {report_period}

请基于以下数据给出详细的周期股分析报告。"""


def create_cyclical_analysis(llm) -> Callable:
    """
    创建周期股分析 Agent

    Args:
        llm: LLM 实例，用于生成分析报告

    Returns:
        周期股分析节点函数
    """

    def cyclical_analysis_node(state: FinancialState) -> FinancialState:
        """
        周期股分析节点

        从状态中获取公司信息，从数据库获取财务数据，
        调用 LLM 进行分析，更新状态中的 cyclical_analysis 字段
        """
        # 从状态中获取公司信息
        company_name = state.get("company_name")
        stock_code = state.get("stock_code")
        report_year = state.get("report_year")
        report_period = state.get("report_period")

        if not company_name or not report_year:
            logger.error("缺少公司信息，无法进行周期股分析")
            return {
                "cyclical_analysis": None,
                "error_msg": "缺少公司信息"
            }

        logger.info(f"开始周期股分析: {company_name} ({stock_code}) {report_year} {report_period}")

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
            cyclical_metrics = calculate_cyclical_metrics(
                balance_sheet, income_statement, cash_flow
            )

            # 3. 获取市场估值数据（PE、PB、股价）
            market_data = {}
            if stock_code:
                market_data = get_stock_market_data(stock_code)

            analysis_metrics = {
                "profitability": profitability,
                "liquidity": liquidity,
                "solvency": solvency,
                "cyclical_metrics": cyclical_metrics,
                "market_valuation": {
                    "pe_ratio": market_data.get("pe_ratio", 0.0),
                    "pb_ratio": market_data.get("pb_ratio", 0.0),
                    "current_price": market_data.get("current_price", 0.0),
                    "market_cap": market_data.get("market_cap", 0.0),
                },
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

            logger.info(f"周期股分析完成: {company_name}, 评级: {result.get('investment_rating', 'UNKNOWN')}")

            return {
                "cyclical_analysis": result
            }

        except Exception as e:
            logger.error(f"周期股分析失败: {e}")
            return {
                "cyclical_analysis": None,
                "error_msg": f"周期股分析失败: {str(e)}"
            }

    return cyclical_analysis_node
