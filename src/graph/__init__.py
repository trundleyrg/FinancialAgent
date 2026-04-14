"""
Graph 模块

提供 FinancialAgent 的 StateGraph 构建和导出

主要组件：
- state.py: FinancialState 状态定义
- coordinator_nodes.py: 协调器节点实现
- graph.py: 图构建和 FinancialAgentsGraph 类
- propagation.py: 状态初始化和传播
- result_persister.py: 分析结果持久化
"""
from .graph import (
    create_financial_agent_graph,
    compile_graph,
    FinancialAgentsGraph,
    should_parse_pdf,
)
from .state import FinancialState
from src.stock_tools.stock_type_config import (
    STOCK_TYPES,
    STOCK_TYPE_KEYWORDS,
    classify_by_keywords,
    get_keywords_for_type,
    get_all_keywords,
    add_keywords,
    CLASSIFICATION_RULES,
)
from .coordinator_nodes import (
    create_check_data_availability_node,
    create_parse_pdf_node,
    create_extract_financial_data_node,
    create_save_to_database_node,
    get_coordinator_nodes,
)
from .propagation import Propagator, default_propagator
from .result_persister import save_analysis_report

__all__ = [
    # 图构建
    "create_financial_agent_graph",
    "compile_graph",
    "FinancialAgentsGraph",
    "should_parse_pdf",
    # 状态
    "FinancialState",
    # 分类配置
    "STOCK_TYPES",
    "STOCK_TYPE_KEYWORDS",
    "classify_by_keywords",
    "get_keywords_for_type",
    "get_all_keywords",
    "add_keywords",
    "CLASSIFICATION_RULES",
    # 协调器节点
    "create_check_data_availability_node",
    "create_parse_pdf_node",
    "create_extract_financial_data_node",
    "create_save_to_database_node",
    "get_coordinator_nodes",
    # 状态传播
    "Propagator",
    "default_propagator",
    # 结果持久化
    "save_analysis_report",
]
