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

同时提供 FinancialAgentsGraph 类，用于协调整个投研 Agent 工作流。
"""

from typing import Any, Literal, Optional, List, Dict
import logging

from langgraph.graph import StateGraph, END

from src.graph.state import FinancialState
from src.graph.coordinator_nodes import (
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
from src.stock_tools.stock_type_config import (
    STOCK_TYPES,
    classify_by_keywords,
)
from src.graph.propagation import Propagator

logger = logging.getLogger("Graph")


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


# ========== FinancialAgentsGraph 类 ==========

def _create_intent_classification_node(llm) -> Any:
    """创建意图分类节点"""
    from src.agents.graph import create_intent_classification_node
    return create_intent_classification_node(llm)


class FinancialAgentsGraph:
    """
    FinancialAgent 主类，协调整个投研 Agent 工作流。

    类似于 TradingAgentsGraph 的结构，提供：
    - LLM 管理
    - 图构建和执行
    - 状态传播
    """

    def __init__(
        self,
        llm,
        debug: bool = False,
        max_recur_limit: int = 100,
        callbacks: Optional[List] = None,
    ):
        """初始化 FinancialAgent 图和组件。

        Args:
            llm: LLM 实例，用于生成分析报告
            debug: 是否以调试模式运行
            max_recur_limit: 最大递归深度
            callbacks: 可选的回调处理器列表
        """
        self.debug = debug
        self.max_recur_limit = max_recur_limit
        self.callbacks = callbacks or []

        # 初始化 LLM
        self.llm = llm

        # 初始化组件
        self.propagator = Propagator(max_recur_limit=max_recur_limit)

        # 创建分析节点
        self.intent_node = _create_intent_classification_node(llm)
        self.cyclical_node = self._create_cyclical_node()
        self.dividend_node = self._create_dividend_node()
        self.fundamental_node = self._create_fundamental_node()
        self.summary_node = self._create_summary_node()

        # 状态跟踪
        self.curr_state: Optional[FinancialState] = None
        self.company_name: Optional[str] = None

        # 构建图
        self.graph = self._build_graph()

    def _create_cyclical_node(self):
        """创建周期股分析节点"""
        return create_cyclical_analysis(self.llm)

    def _create_dividend_node(self):
        """创建红利股分析节点"""
        from src.agents.analysis.dividend_stock_agent import create_dividend_analysis
        return create_dividend_analysis(self.llm)

    def _create_fundamental_node(self):
        """创建基本面分析节点"""
        return create_fundamental_analysis(self.llm)

    def _create_summary_node(self):
        """创建总结节点"""
        return create_summary_agent(self.llm)

    def _build_graph(self) -> StateGraph:
        """构建状态图"""
        workflow = StateGraph(FinancialState)

        # 添加节点
        workflow.add_node("intent_classification", self.intent_node)
        workflow.add_node("analysis_cyclical", self.cyclical_node)
        workflow.add_node("analysis_dividend", self.dividend_node)
        workflow.add_node("analysis_fundamental", self.fundamental_node)
        workflow.add_node("aggregate", self.summary_node)

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

        return workflow.compile()

    def propagate(
        self,
        company_name: str,
        business_scope: str = "",
        company_short_name: Optional[str] = None,
        stock_code: Optional[str] = None,
        report_year: Optional[int] = None,
        report_period: Optional[str] = None,
    ) -> FinancialState:
        """运行 FinancialAgent 图进行分析。

        Args:
            company_name: 公司名称
            business_scope: 公司经营范围描述
            company_short_name: 公司简称
            stock_code: 股票代码
            report_year: 报告年份
            report_period: 报告周期 (Q1/H1/Q3/FY)

        Returns:
            最终状态，包含分析结果
        """
        self.company_name = company_name

        # 初始化状态
        init_state = self.propagator.create_initial_state(
            company_name=company_name,
            company_short_name=company_short_name,
            stock_code=stock_code,
            business_scope=business_scope,
            report_year=report_year,
            report_period=report_period,
        )

        args = self.propagator.get_graph_args(
            callbacks=self.callbacks,
            recursion_limit=self.max_recur_limit,
        )

        if self.debug:
            # 调试模式，带追踪
            trace = []
            for chunk in self.graph.stream(init_state, **args):
                if chunk:
                    trace.append(chunk)
            final_state = trace[-1] if trace else init_state
        else:
            # 标准模式
            final_state = self.graph.invoke(init_state, **args)

        # 存储当前状态
        self.curr_state = final_state

        logger.info(f"分析完成: {company_name}")

        return final_state

    def get_result(self) -> Optional[Dict[str, Any]]:
        """获取分析结果。

        Returns:
            包含分析结果的字典，如果不存在则返回 None
        """
        if self.curr_state is None:
            return None

        return {
            "company_name": self.curr_state.get("company_name"),
            "stock_code": self.curr_state.get("stock_code"),
            "stock_types": self.curr_state.get("stock_types", []),
            "cyclical_analysis": self.curr_state.get("cyclical_analysis"),
            "dividend_analysis": self.curr_state.get("dividend_analysis"),
            "fundamental_analysis": self.curr_state.get("fundamental_analysis"),
            "summary": self.curr_state.get("summary"),
            "status": self.curr_state.get("status"),
        }
