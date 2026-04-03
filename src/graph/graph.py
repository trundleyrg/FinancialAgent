"""
构建 StateGraph、节点和边的逻辑

定义 FinancialAgent 的完整处理流程图：
1. 解析 PDF → 提取文本和表格
2. 提取财务数据 → 结构化数据
3. 保存到数据库
4. 并行执行：周期股分析 + 基本面分析
5. 综合总结 → 最终建议
"""

from typing import Any

from langgraph.graph import StateGraph, END

from src.agents.state import FinancialState
from src.agents.nodes import (
    create_parse_pdf_node,
    create_extract_financial_data_node,
    create_save_to_database_node
)
from src.agents.analysis import (
    create_cyclical_analysis,
    create_fundamental_analysis,
    create_summary_agent
)


def create_financial_agent_graph(llm: Any) -> StateGraph:
    """
    创建 FinancialAgent 主图

    Args:
        llm: LLM 实例，将传递给分析 Agent

    Returns:
        编译后的 StateGraph
    """
    # 创建 StateGraph
    graph = StateGraph(FinancialState)

    # 添加协调器节点
    graph.add_node("parse_pdf", create_parse_pdf_node())
    graph.add_node("extract_financial_data", create_extract_financial_data_node())
    graph.add_node("save_to_database", create_save_to_database_node())

    # 添加分析 Agent 节点
    graph.add_node("run_cyclical_analysis", create_cyclical_analysis(llm))
    graph.add_node("run_fundamental_analysis", create_fundamental_analysis(llm))
    graph.add_node("run_summary", create_summary_agent(llm))

    # 定义边（流程连接）
    # 1. 解析 PDF 后提取财务数据
    graph.add_edge("parse_pdf", "extract_financial_data")

    # 2. 提取财务数据后保存到数据库
    graph.add_edge("extract_financial_data", "save_to_database")

    # 3. 保存后并行执行两个分析
    graph.add_edge("save_to_database", "run_cyclical_analysis")
    graph.add_edge("save_to_database", "run_fundamental_analysis")

    # 4. 两个分析都完成后进行总结
    graph.add_edge("run_cyclical_analysis", "run_summary")
    graph.add_edge("run_fundamental_analysis", "run_summary")

    # 5. 总结后结束
    graph.add_edge("run_summary", END)

    # 设置入口点
    graph.set_entry_point("parse_pdf")

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
