"""
LangGraph 调试模式测试脚本

通过 FinancialAgentsGraph 运行完整的东阿阿胶分析，
流式捕获每个节点的输出并写入 JSONL trace 文件，
最终生成 Markdown 分析报告。
"""
import os
import sys
import json
import datetime
from pathlib import Path
from typing import Any, Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.utils.llm_client import AIClient
from src.graph.graph import FinancialAgentsGraph
from src.graph.propagation import Propagator
from src.graph.result_persister import save_analysis_report

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Test")


class ConversationLogger:
    def __init__(self, output_path: str):
        self.output_path = output_path
        self.entries: List[Dict[str, Any]] = []

    def log(self, event_type: str, data: Dict[str, Any], node_name: str = None):
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "event_type": event_type,
            "node_name": node_name,
            "data": data,
        }
        self.entries.append(entry)
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            return {}
        safe = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 200:
                safe[k] = v[:200] + "..."
            else:
                safe[k] = v
        return safe


def test_ej_aj_analysis():
    """东阿阿胶 (000423) 完整 LangGraph 分析——使用真实 graph 和数据库查询"""
    print("=" * 60)
    print("东阿阿胶 (000423) LangGraph 调试测试")
    print("=" * 60)

    # ── 路径配置 ──────────────────────────────────────────────────
    jsonl_path = str(project_root / "data" / "000423" / "memory" / "langgraph_trace.jsonl")
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    if os.path.exists(jsonl_path):
        os.remove(jsonl_path)

    conv_logger = ConversationLogger(jsonl_path)

    # ── 公司信息 ──────────────────────────────────────────────────
    company_name = "东阿阿胶"
    company_short_name = "东阿阿胶"
    stock_code = "000423"
    business_scope = (
        "阿胶及阿胶系列产品、其他保健品、药用辅料、包装材料进出口业务的生产、销售；"
        "畜牧养殖；中药材种植、销售"
    )
    report_year = 2024
    report_period = "FY"

    conv_logger.log("session_start", {
        "company": company_name,
        "stock_code": stock_code,
        "report_year": report_year,
        "description": "FinancialAgentsGraph 真实 graph 测试",
    })

    # ── 初始化 LLM ────────────────────────────────────────────────
    print("\n[1] 初始化 LLM...")
    ai_client = AIClient({"TEMPERATURE": 0.7, "MAX_TOKENS": 4096})
    valid, err = ai_client.validate_config()
    if not valid:
        print(f"LLM 配置无效: {err}")
        conv_logger.log("error", {"error": err}, "init_llm")
        return
    llm = ai_client.llm
    print(f"LLM 初始化成功: {ai_client.get_model_name()}")
    conv_logger.log("llm_initialized", {"model": ai_client.get_model_name()})

    # ── 构建 FinancialAgentsGraph ─────────────────────────────────
    print("\n[2] 构建 FinancialAgentsGraph...")
    agent = FinancialAgentsGraph(llm=llm)
    propagator = Propagator()
    print("Graph 构建成功")

    # ── 初始化状态 ────────────────────────────────────────────────
    print("\n[3] 初始化状态...")
    initial_state = propagator.create_initial_state(
        company_name=company_name,
        company_short_name=company_short_name,
        stock_code=stock_code,
        business_scope=business_scope,
        report_year=report_year,
        report_period=report_period,
    )
    conv_logger.log("state_initialized", {
        "company_name": company_name,
        "stock_code": stock_code,
        "report_year": report_year,
        "report_period": report_period,
    })

    # ── 流式运行 graph，逐节点记录 ────────────────────────────────
    print("\n[4] 流式运行 graph...")
    accumulated_state = dict(initial_state)

    graph_config = {"recursion_limit": 100}

    for chunk in agent.graph.stream(
        initial_state,
        config=graph_config,
        stream_mode="updates",
    ):
        # chunk 格式: {node_name: state_delta}
        for node_name, state_delta in chunk.items():
            print(f"  [OK] 节点完成: {node_name}")

            conv_logger.log(
                event_type="node_output",
                data=conv_logger._sanitize(state_delta),
                node_name=node_name,
            )

            # 合并 delta 到累积状态
            if isinstance(state_delta, dict):
                for k, v in state_delta.items():
                    if isinstance(v, list) and isinstance(accumulated_state.get(k), list):
                        # LangGraph Annotated list 追加语义
                        accumulated_state[k] = accumulated_state[k] + v
                    else:
                        accumulated_state[k] = v

    final_state = accumulated_state

    # ── 输出结果 ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("分析结果")
    print("=" * 60)

    print(f"股票类型: {final_state.get('stock_types', [])}")
    print(f"状态: {final_state.get('status')}")

    def _print_analysis(title: str, data: Any):
        if not data:
            return
        print(f"\n--- {title} ---")
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and len(value) > 300:
                    print(f"\n{key}:\n  {value}")
                elif isinstance(value, list):
                    print(f"\n{key}:")
                    for item in value:
                        print(f"  - {item}")
                else:
                    print(f"  {key}: {value}")

    _print_analysis("周期股分析", final_state.get("cyclical_analysis"))
    _print_analysis("红利股分析", final_state.get("dividend_analysis"))
    _print_analysis("基本面分析", final_state.get("fundamental_analysis"))
    _print_analysis("投资总结", final_state.get("summary"))

    conv_logger.log("session_end", {
        "stock_types": final_state.get("stock_types", []),
        "status": final_state.get("status"),
        "total_entries": len(conv_logger.entries),
    })
    print(f"\n对话流程已保存到: {jsonl_path}")

    # ── 生成 Markdown 报告 ────────────────────────────────────────
    print("\n[5] 保存分析报告...")
    try:
        report_path = save_analysis_report(
            jsonl_path=jsonl_path,
            company_name=company_name,
            stock_code=stock_code,
        )
        print(f"  分析报告已保存到: {report_path}")
    except Exception as e:
        print(f"  保存报告失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n测试完成!")


if __name__ == "__main__":
    test_ej_aj_analysis()
