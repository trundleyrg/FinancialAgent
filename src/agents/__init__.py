"""
Agent 模块

提供各种 Agent 的创建函数，用于 LangGraph 图的构建
"""
from .analysis.cyclical_stock_agent import create_cyclical_analysis
from .analysis.dividend_stock_agent import create_dividend_analysis
from .analysis.fundamental_agent import create_fundamental_analysis
from .analysis.summary_agent import create_summary_agent
from .graph import (
    build_financial_agent_graph,
    build_parallel_financial_agent_graph,
    create_intent_classification_node,
    classify_stock_type,
    create_simple_stock_classifier,
    run_multi_type_analysis,
    get_available_stock_types,
    STOCK_TYPES,
)
from .stock_type_config import (
    STOCK_TYPE_KEYWORDS,
    STOCK_TYPES as CONFIG_STOCK_TYPES,
    classify_by_keywords,
    get_keywords_for_type,
    get_all_keywords,
    add_keywords,
    CLASSIFICATION_RULES,
)

__all__ = [
    # 分析 Agent
    "create_cyclical_analysis",
    "create_dividend_analysis",
    "create_fundamental_analysis",
    "create_summary_agent",
    # Graph 构建
    "build_financial_agent_graph",
    "build_parallel_financial_agent_graph",
    "create_intent_classification_node",
    "classify_stock_type",
    "create_simple_stock_classifier",
    "run_multi_type_analysis",
    "get_available_stock_types",
    "STOCK_TYPES",
    # 分类配置
    "STOCK_TYPE_KEYWORDS",
    "classify_by_keywords",
    "get_keywords_for_type",
    "get_all_keywords",
    "add_keywords",
    "CLASSIFICATION_RULES",
]
