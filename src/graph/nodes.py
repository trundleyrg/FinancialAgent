"""
图节点属性定义

定义 FinancialAgent 图中所有节点的属性和元数据
"""

from typing import TypedDict


class GraphNode(TypedDict):
    """节点定义，包含名称、描述和类型"""
    name: str                      # 节点名称
    description: str              # 节点描述
    agent_type: str               # 节点类型: coordinator/cyclical/fundamental/summary


# 图中所有节点的注册表
NODES = {
    # ========== 协调器节点（同步操作）==========
    "parse_pdf": GraphNode(
        name="parse_pdf",
        description="解析 PDF 文件，提取文本、表格和公司信息",
        agent_type="coordinator"
    ),

    "extract_financial_data": GraphNode(
        name="extract_financial_data",
        description="从 PDF 中提取结构化财务数据",
        agent_type="coordinator"
    ),

    "save_to_database": GraphNode(
        name="save_to_database",
        description="将提取的财务数据保存到数据库",
        agent_type="coordinator"
    ),

    # ========== 分析节点（LLM 调用）==========
    "run_cyclical_analysis": GraphNode(
        name="run_cyclical_analysis",
        description="运行周期股分析，评估行业周期位置和周期股特有风险",
        agent_type="cyclical"
    ),

    "run_fundamental_analysis": GraphNode(
        name="run_fundamental_analysis",
        description="运行基本面分析，评估公司盈利能力、流动性等",
        agent_type="fundamental"
    ),

    "run_summary": GraphNode(
        name="run_summary",
        description="综合两种分析结果，生成最终投资建议",
        agent_type="summary"
    ),
}


def get_node_info(node_name: str) -> GraphNode:
    """获取节点信息"""
    return NODES.get(node_name)


def get_all_nodes() -> dict:
    """获取所有节点注册表"""
    return NODES


def get_nodes_by_type(agent_type: str) -> list:
    """获取指定类型的所有节点"""
    return [
        {"name": name, **node}
        for name, node in NODES.items()
        if node["agent_type"] == agent_type
    ]
