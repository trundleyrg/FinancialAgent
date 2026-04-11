# FinancialAgent/graph/propagation.py

from typing import Dict, Any, List, Optional, Callable
from src.graph.state import FinancialState


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit: int = 100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: Optional[str] = None,
        company_short_name: Optional[str] = None,
        stock_code: Optional[str] = None,
        pdf_path: Optional[str] = None,
        business_scope: Optional[str] = None,
        report_year: Optional[int] = None,
        report_period: Optional[str] = None,
    ) -> FinancialState:
        """Create the initial state for the agent graph.

        Args:
            company_name: 公司全名
            company_short_name: 公司简称
            stock_code: 股票代码
            pdf_path: PDF 文件路径
            business_scope: 公司经营范围描述
            report_year: 报告年份
            report_period: 报告周期 (Q1/H1/Q3/FY)

        Returns:
            FinancialState: 初始化后的状态
        """
        return FinancialState(
            # PDF 处理相关
            pdf_path=pdf_path or "",
            raw_markdown=None,
            structured_data=[],

            # 公司信息
            company_name=company_name,
            company_short_name=company_short_name,
            stock_code=stock_code,
            report_year=report_year,
            report_period=report_period,

            # 公司业务信息
            business_scope=business_scope,

            # 数据可用性检查结果
            data_availability=None,

            # 股票类型分类结果（初始为空，分析后填充）
            stock_types=[],

            # 分析结果（初始为空）
            dividend_analysis=None,
            cyclical_analysis=None,
            growth_analysis=None,
            value_analysis=None,
            defensive_analysis=None,
            fundamental_analysis=None,
            summary=None,

            # 任务状态
            status="pending",
            error_msg=None,
            record_id=None,
        )

    def get_graph_args(
        self,
        callbacks: Optional[List] = None,
        recursion_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
            recursion_limit: Override for max recursion limit.

        Returns:
            Dict containing stream_mode and config for graph invocation.
        """
        config = {"recursion_limit": recursion_limit or self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }

    def update_state(
        self,
        state: FinancialState,
        updates: Dict[str, Any],
    ) -> FinancialState:
        """Update state with new values.

        Args:
            state: Current state
            updates: Dictionary of updates to apply

        Returns:
            Updated state
        """
        new_state = state.copy()
        new_state.update(updates)
        return new_state

    def get_stock_types_from_state(self, state: FinancialState) -> List[str]:
        """Extract stock types from state.

        Args:
            state: Current state

        Returns:
            List of stock types
        """
        return state.get("stock_types", [])

    def add_analysis_result(
        self,
        state: FinancialState,
        stock_type: str,
        result: Dict[str, Any],
    ) -> FinancialState:
        """Add analysis result to state.

        Args:
            state: Current state
            stock_type: Stock type key (e.g., 'dividend', 'cyclical')
            result: Analysis result dictionary

        Returns:
            Updated state
        """
        key_map = {
            "dividend": "dividend_analysis",
            "cyclical": "cyclical_analysis",
            "growth": "growth_analysis",
            "value": "value_analysis",
            "defensive": "defensive_analysis",
            "fundamental": "fundamental_analysis",
        }
        key = key_map.get(stock_type, f"{stock_type}_analysis")
        return {**state, key: result}


# 全局默认实例
default_propagator = Propagator()
