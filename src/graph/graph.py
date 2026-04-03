"""
构建 StateGraph、节点和边的逻辑

定义 FinancialAgent 的完整处理流程图：
1. 检查数据可用性 → 判断是否需要解析 PDF
2. 如果数据充足 → 直接进行数据分析
3. 如果数据不足 → 解析 PDF → 提取文本和表格
4. 提取财务数据 → 结构化数据
5. 保存到数据库
6. 并行执行：周期股分析 + 基本面分析
7. 综合总结 → 最终建议
"""

from typing import Any, Literal

from langgraph.graph import StateGraph, END

from src.agents.state import FinancialState
from src.agents.nodes import (
    create_check_data_availability_node,
    create_parse_pdf_node,
    create_extract_financial_data_node,
    create_save_to_database_node
)
from src.agents.analysis import (
    create_cyclical_analysis,
    create_fundamental_analysis,
    create_summary_agent
)


def should_parse_pdf(state: FinancialState) -> Literal["parse_pdf", "run_analysis"]:
    """
    条件路由函数：判断是否需要解析 PDF

    Args:
        state: 当前状态

    Returns:
        "parse_pdf" 如果数据不足需要解析
        "run_analysis" 如果数据充足直接分析
    """
    data_availability = state.get("data_availability", {})
    has_data = data_availability.get("has_data", False)

    if has_data:
        return "run_analysis"
    else:
        return "parse_pdf"


def create_financial_agent_graph(llm: Any) -> StateGraph:
    """
    创建 FinancialAgent 主图

    流程说明：
    1. check_data_availability: 检查数据库中是否有近十年数据
    2. 根据检查结果条件路由：
       - 有数据 → 直接执行分析（跳过 PDF 解析）
       - 无数据 → 解析 PDF → 提取数据 → 保存到数据库
    3. run_cyclical_analysis + run_fundamental_analysis: 并行执行两个分析
    4. run_summary: 汇总两个分析结果

    Args:
        llm: LLM 实例，将传递给分析 Agent

    Returns:
        编译后的 StateGraph
    """
    # 创建 StateGraph
    graph = StateGraph(FinancialState)

    # 添加协调器节点
    graph.add_node("check_data_availability", create_check_data_availability_node())
    graph.add_node("parse_pdf", create_parse_pdf_node())
    graph.add_node("extract_financial_data", create_extract_financial_data_node())
    graph.add_node("save_to_database", create_save_to_database_node())

    # 添加分析 Agent 节点
    graph.add_node("run_cyclical_analysis", create_cyclical_analysis(llm))
    graph.add_node("run_fundamental_analysis", create_fundamental_analysis(llm))
    graph.add_node("run_summary", create_summary_agent(llm))

    # 设置入口点
    graph.set_entry_point("check_data_availability")

    # 条件路由：检查数据可用性后决定是否需要解析 PDF
    graph.add_conditional_edges(
        "check_data_availability",
        should_parse_pdf,
        {
            "parse_pdf": "parse_pdf",       # 数据不足，需要解析 PDF
            "run_analysis": "run_cyclical_analysis"  # 数据充足，直接分析
        }
    )

    # PDF 解析流程
    graph.add_edge("parse_pdf", "extract_financial_data")
    graph.add_edge("extract_financial_data", "save_to_database")

    # 数据保存后，并行执行两个分析
    graph.add_edge("save_to_database", "run_cyclical_analysis")
    graph.add_edge("save_to_database", "run_fundamental_analysis")

    # 两个分析都完成后进行总结
    graph.add_edge("run_cyclical_analysis", "run_summary")
    graph.add_edge("run_fundamental_analysis", "run_summary")

    # 总结后结束
    graph.add_edge("run_summary", END)

    return graph


def compile_graph(llm: Any) -> Any:
    """
    编译图并返回可执行的图

    Args:
        llm: LLM 实例

    Returns:
        编译后的可执行图
    """
    graph = create_financial_agent_graph(llm)
    return graph.compile()
