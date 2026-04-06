"""
FinancialAgent LangGraph 定义

本模块定义了基于 LangGraph 的智能投研 Agent 工作流。

工作流程：
1. 意图判断（Intent Classification）
   - 根据公司经营范围判断股票类型（红利股/周期股/成长股/价值股/防御股）
   - 支持多选判断，一个公司可以属于多种类型

2. 条件路由（Conditional Routing）
   - 根据判断结果并行调用相应的分析 Agent
   - 不同类型调用不同的分析逻辑

3. 分析执行（Analysis Execution）
   - 红利股分析：分红能力、财务健康度、股息率
   - 周期股分析：行业周期定位、产能利用率、CAPEX
   - 成长股分析：营收增长、利润增速、研发投入
   - 价值股分析：估值水平、资产质量、盈利稳定性
   - 防御股分析：抗周期能力、现金流稳定性

4. 结果汇总（Result Aggregation）
   - 汇总各类型分析结果
   - 生成综合投资建议

依赖：
- langgraph: Agent 流程编排
- src.agents.state: Agent 状态定义
- src.agents.nodes: 协调器节点
- src.agents.analysis: 各类型分析 Agent
- src.agents.stock_type_config: 股票类型分类配置

作者：FinancialAgent Team
创建日期：2026-04-06
"""

from typing import Callable, Dict, Any, List, Literal
from langgraph.graph import StateGraph, END
import logging

from src.agents.state import FinancialState
from src.agents.stock_type_config import (
    STOCK_TYPES,
    STOCK_TYPE_KEYWORDS,
    classify_by_keywords,
)

logger = logging.getLogger("Agent.Graph")


def classify_stock_type(business_scope: str, company_name: str = "") -> List[str]:
    """
    根据公司经营范围和名称判断股票类型

    Args:
        business_scope: 公司经营范围描述
        company_name: 公司名称（用于辅助判断）

    Returns:
        股票类型列表（多选）

    Note:
        实际分类逻辑在 stock_type_config.py 的 classify_by_keywords 函数中定义
    """
    if not business_scope and not company_name:
        return ["fundamental"]  # 无法判断时进行基本面分析

    text = f"{company_name} {business_scope}"
    return classify_by_keywords(text)


def create_intent_classification_node(llm) -> Callable:
    """
    创建意图分类节点

    Args:
        llm: LLM 实例

    Returns:
        意图分类节点函数
    """

    def intent_classification_node(state: FinancialState) -> FinancialState:
        """
        意图分类节点

        根据公司经营范围，判断股票属于哪种类型
        支持多选判断
        """
        business_scope = state.get("business_scope", "")
        company_name = state.get("company_name", "")
        company_short_name = state.get("company_short_name", "")

        if not company_name:
            logger.warning("缺少公司名称，无法进行股票类型分类")
            return {
                "stock_types": ["fundamental"],
                "status": "processing"
            }

        # 使用关键词匹配进行分类
        stock_types = classify_stock_type(
            business_scope=business_scope,
            company_name=company_name
        )

        logger.info(f"股票类型分类完成: {company_name} -> {stock_types}")

        return {
            "stock_types": stock_types,
            "status": "processing"
        }

    return intent_classification_node


def create_analysis_nodes(llm) -> Dict[str, Callable]:
    """
    创建各类分析节点

    Args:
        llm: LLM 实例

    Returns:
        分析节点字典
    """
    from src.agents.analysis.cyclical_stock_agent import create_cyclical_analysis
    from src.agents.analysis.dividend_stock_agent import create_dividend_analysis
    from src.agents.analysis.fundamental_agent import create_fundamental_analysis

    return {
        "cyclical_analysis": create_cyclical_analysis(llm),
        "dividend_analysis": create_dividend_analysis(llm),
        "fundamental_analysis": create_fundamental_analysis(llm),
    }


def route_based_on_stock_type(state: FinancialState) -> Literal["analysis_cyclical", "analysis_dividend", "analysis_fundamental", "aggregate"]:
    """
    根据股票类型路由到对应的分析节点

    Args:
        state: Agent 状态

    Returns:
        下一个节点的名称
    """
    stock_types = state.get("stock_types", [])

    if not stock_types:
        return "aggregate"

    # 多选判断：优先检查是否有周期股或红利股
    if "cyclical" in stock_types:
        return "analysis_cyclical"
    elif "dividend" in stock_types:
        return "analysis_dividend"
    elif "fundamental" in stock_types:
        return "analysis_fundamental"

    return "aggregate"


def create_analysis_router(stock_type: str) -> Callable:
    """
    创建特定类型的分析节点包装器

    Args:
        stock_type: 股票类型

    Returns:
        分析节点函数
    """
    from src.agents.analysis.cyclical_stock_agent import create_cyclical_analysis
    from src.agents.analysis.dividend_stock_agent import create_dividend_analysis
    from src.agents.analysis.fundamental_agent import create_fundamental_analysis

    analysis_creators = {
        "cyclical": create_cyclical_analysis,
        "dividend": create_dividend_analysis,
        "fundamental": create_fundamental_analysis,
    }

    def create_router_node(llm):
        creator = analysis_creators.get(stock_type)
        if creator:
            return creator(llm)
        # 默认返回空节点
        return lambda state: state

    return create_router_node


def build_financial_agent_graph(llm) -> StateGraph:
    """
    构建 FinancialAgent 状态图

    Args:
        llm: LLM 实例

    Returns:
        编译后的 StateGraph
    """
    from src.agents.analysis.summary_agent import create_summary_agent
    from src.agents.analysis.cyclical_stock_agent import create_cyclical_analysis
    from src.agents.analysis.dividend_stock_agent import create_dividend_analysis
    from src.agents.analysis.fundamental_agent import create_fundamental_analysis

    # 创建图
    workflow = StateGraph(FinancialState)

    # 创建节点
    intent_node = create_intent_classification_node(llm)
    cyclical_node = create_cyclical_analysis(llm)
    dividend_node = create_dividend_analysis(llm)
    fundamental_node = create_fundamental_analysis(llm)
    summary_node = create_summary_agent(llm)

    # 添加节点
    workflow.add_node("intent_classification", intent_node)
    workflow.add_node("analysis_cyclical", cyclical_node)
    workflow.add_node("analysis_dividend", dividend_node)
    workflow.add_node("analysis_fundamental", fundamental_node)
    workflow.add_node("aggregate", summary_node)

    # 设置入口点
    workflow.set_entry_point("intent_classification")

    # 添加边
    workflow.add_edge("intent_classification", "analysis_cyclical", condition=lambda s: "cyclical" in s.get("stock_types", []))
    workflow.add_edge("intent_classification", "analysis_dividend", condition=lambda s: "dividend" in s.get("stock_types", []))
    workflow.add_edge("intent_classification", "analysis_fundamental", condition=lambda s: not any(t in s.get("stock_types", []) for t in ["cyclical", "dividend"]))

    # 分析节点都汇聚到 aggregate
    workflow.add_edge("analysis_cyclical", "aggregate")
    workflow.add_edge("analysis_dividend", "aggregate")
    workflow.add_edge("analysis_fundamental", "aggregate")

    # aggregate 是终点
    workflow.add_edge("aggregate", END)

    # 编译图
    return workflow.compile()


def build_parallel_financial_agent_graph(llm) -> StateGraph:
    """
    构建支持并行分析的多类型 FinancialAgent 状态图

    该图支持一个公司同时被判断为多种类型，并行执行多种分析

    Args:
        llm: LLM 实例

    Returns:
        编译后的 StateGraph
    """
    from src.agents.analysis.summary_agent import create_summary_agent
    from src.agents.analysis.cyclical_stock_agent import create_cyclical_analysis
    from src.agents.analysis.dividend_stock_agent import create_dividend_analysis
    from src.agents.analysis.fundamental_agent import create_fundamental_analysis

    # 创建图
    workflow = StateGraph(FinancialState)

    # 创建节点
    intent_node = create_intent_classification_node(llm)
    cyclical_node = create_cyclical_analysis(llm)
    dividend_node = create_dividend_analysis(llm)
    fundamental_node = create_fundamental_analysis(llm)
    summary_node = create_summary_agent(llm)

    # 添加节点
    workflow.add_node("intent_classification", intent_node)
    workflow.add_node("analysis_cyclical", cyclical_node)
    workflow.add_node("analysis_dividend", dividend_node)
    workflow.add_node("analysis_fundamental", fundamental_node)
    workflow.add_node("aggregate", summary_node)

    # 设置入口点
    workflow.set_entry_point("intent_classification")

    # 定义条件路由函数
    def should_run_cyclical(state: FinancialState) -> bool:
        return "cyclical" in state.get("stock_types", [])

    def should_run_dividend(state: FinancialState) -> bool:
        return "dividend" in state.get("stock_types", [])

    def should_run_fundamental(state: FinancialState) -> bool:
        stock_types = state.get("stock_types", [])
        return "fundamental" in stock_types or (not any(t in stock_types for t in ["cyclical", "dividend"]))

    # 使用条件边实现多选判断
    workflow.add_conditional_edges(
        "intent_classification",
        {
            "cyclical": should_run_cyclical,
            "dividend": should_run_dividend,
            "fundamental": should_run_fundamental
        }
    )

    # 分析节点汇聚到 aggregate
    workflow.add_edge("analysis_cyclical", "aggregate")
    workflow.add_edge("analysis_dividend", "aggregate")
    workflow.add_edge("analysis_fundamental", "aggregate")

    # aggregate 是终点
    workflow.add_edge("aggregate", END)

    # 编译图
    return workflow.compile()


def create_run_analysis_for_type(stock_type: str) -> Callable:
    """
    创建针对特定类型运行分析的函数

    Args:
        stock_type: 股票类型

    Returns:
        分析函数
    """
    from src.agents.analysis.cyclical_stock_agent import create_cyclical_analysis
    from src.agents.analysis.dividend_stock_agent import create_dividend_analysis
    from src.agents.analysis.fundamental_agent import create_fundamental_analysis

    creators = {
        "cyclical": create_cyclical_analysis,
        "dividend": create_dividend_analysis,
        "fundamental": create_fundamental_analysis,
    }

    def run_analysis(llm, state: FinancialState) -> FinancialState:
        creator = creators.get(stock_type)
        if creator:
            node = creator(llm)
            return node(state)
        return state

    return run_analysis


def run_multi_type_analysis(
    llm,
    state: FinancialState,
    stock_types: List[str]
) -> FinancialState:
    """
    对给定类型列表并行运行多种分析

    Args:
        llm: LLM 实例
        state: 初始状态
        stock_types: 股票类型列表

    Returns:
        更新后的状态
    """
    from src.agents.analysis.cyclical_stock_agent import create_cyclical_analysis
    from src.agents.analysis.dividend_stock_agent import create_dividend_analysis
    from src.agents.analysis.fundamental_agent import create_fundamental_analysis

    result_state = state.copy()

    for stock_type in stock_types:
        if stock_type == "cyclical":
            node = create_cyclical_analysis(llm)
            result_state = node(result_state)
        elif stock_type == "dividend":
            node = create_dividend_analysis(llm)
            result_state = node(result_state)
        elif stock_type == "fundamental":
            node = create_fundamental_analysis(llm)
            result_state = node(result_state)

    return result_state


# ========== 便捷入口函数 ==========

def create_simple_stock_classifier() -> Callable:
    """
    创建简单的股票分类器（无需 LLM）

    Returns:
        分类函数
    """
    def classify(state: FinancialState) -> FinancialState:
        business_scope = state.get("business_scope", "")
        company_name = state.get("company_name", "")

        stock_types = classify_stock_type(business_scope, company_name)

        return {
            "stock_types": stock_types
        }

    return classify


def get_available_stock_types() -> List[str]:
    """
    获取所有可用的股票类型

    Returns:
        股票类型列表
    """
    return STOCK_TYPES.copy()


__all__ = [
    "build_financial_agent_graph",
    "build_parallel_financial_agent_graph",
    "create_intent_classification_node",
    "classify_stock_type",
    "create_simple_stock_classifier",
    "run_multi_type_analysis",
    "get_available_stock_types",
    "STOCK_TYPES"
]