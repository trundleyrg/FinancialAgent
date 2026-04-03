"""
总结 Agent

本模块定义了总结 Agent，用于综合周期股分析和基本面分析的结论，
生成最终的投资建议报告。

核心功能：
1. 综合分析：结合周期定位和基本面评分
2. 权重调整：根据当前周期阶段调整不同分析的权重
3. 风险整合：汇总所有风险因素
4. 最终建议：生成明确的投资决策建议

决策逻辑：
- 复苏期：周期股分析权重提高（+20%），成长性权重提高
- 繁荣期：基本面权重提高（+20%），注意锁定利润
- 衰退期：基本面权重提高（+20%），关注现金流
- 萧条期：价值投资视角，关注 PB 和资产质量

输入：
- cyclical_analysis: 周期股分析结果
- fundamental_analysis: 基本面分析结果

输出：
- 综合投资评级
- 置信度评级
- 核心优势
- 核心风险
- 投资逻辑
- 建议
- 投资期限

依赖：
- langgraph: Agent 流程编排
- langchain: LLM 调用
- src.agents.state: Agent 状态定义

作者：FinancialAgent Team
创建日期：2026-04-03
"""

from typing import Callable, Dict, Any
import json
import logging
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from src.agents.state import FinancialState

logger = logging.getLogger("Agent.Summary")


# 总结分析 System Prompt
SYSTEM_PROMPT = """你是一位专业的投资顾问，负责综合周期股分析和基本面分析的结果，
给出最终的投资建议。

你的职责是：

1. 综合评估
   - 结合周期定位和基本面评分
   - 识别共同看多/看空的因素
   - 分析两种分析的互补性和分歧点

2. 投资逻辑构建
   - 清晰阐述投资理由
   - 量化风险收益比
   - 设定投资期限

3. 风险整合
   - 周期特有风险（如产能过剩）
   - 基本面风险（如高负债）
   - 市场风险（估值过高）

4. 最终建议
   - 明确 BUY/HOLD/SELL 建议
   - 设定置信度评级
   - 给出操作建议

请基于以下分析结果进行总结：

周期股分析结果：
{cyclical_analysis}

基本面分析结果：
{fundamental_analysis}

请以 JSON 格式返回总结报告，包含以下字段：
- combined_rating: 综合评级（BUY/HOLD/SELL）
- confidence_level: 置信度（高/中/低）
- key_strengths: 核心优势列表
- key_risks: 核心风险列表
- investment_thesis: 投资逻辑
- recommendation: 操作建议
- target_horizon: 投资期限（短期/中期/长期）
- analysis_timestamp: 分析时间戳
"""

# 总结分析 User Prompt 模板
USER_PROMPT = """请综合以下分析结果，给出最终的投资建议：

公司名称：{company_name}
股票代码：{stock_code}
报告期：{report_year}年 {report_period}

请结合周期股分析和基本面分析的结果，给出综合的投资建议。"""


def create_summary_agent(llm) -> Callable:
    """
    创建总结 Agent

    Args:
        llm: LLM 实例，用于生成总结报告

    Returns:
        总结节点函数
    """

    def summary_node(state: FinancialState) -> FinancialState:
        """
        总结节点

        从状态中获取周期股分析和基本面分析结果，
        调用 LLM 进行综合分析，更新状态中的 summary 字段
        """
        # 从状态中获取公司信息
        company_name = state.get("company_name")
        stock_code = state.get("stock_code")
        report_year = state.get("report_year")
        report_period = state.get("report_period")

        # 获取分析结果
        cyclical_analysis = state.get("cyclical_analysis")
        fundamental_analysis = state.get("fundamental_analysis")

        if not cyclical_analysis and not fundamental_analysis:
            logger.error("缺少分析结果，无法进行总结")
            return {
                "summary": None,
                "error_msg": "缺少分析结果"
            }

        logger.info(f"开始总结分析: {company_name} ({stock_code})")

        try:
            # 1. 构建 prompt
            system_prompt = SYSTEM_PROMPT.format(
                cyclical_analysis=json.dumps(cyclical_analysis or {}, ensure_ascii=False, indent=2),
                fundamental_analysis=json.dumps(fundamental_analysis or {}, ensure_ascii=False, indent=2)
            )

            user_prompt = USER_PROMPT.format(
                company_name=company_name or "未知",
                stock_code=stock_code or "未知",
                report_year=report_year or "未知",
                report_period=report_period or "未知"
            )

            # 2. 调用 LLM
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", user_prompt)
            ])

            # 使用 JSON 输出解析器
            parser = JsonOutputParser()
            chain = prompt | llm | parser

            result = chain.invoke({})

            # 添加时间戳
            result["analysis_timestamp"] = datetime.now().isoformat()

            logger.info(f"总结分析完成: {company_name}, 综合评级: {result.get('combined_rating', 'UNKNOWN')}")

            return {
                "summary": result,
                "status": "completed"
            }

        except Exception as e:
            logger.error(f"总结分析失败: {e}")
            return {
                "summary": None,
                "error_msg": f"总结分析失败: {str(e)}"
            }

    return summary_node
