"""
LangGraph 调试模式测试脚本

用于测试 FinancialAgent 的 langgraph 构建并生成东阿阿胶的分析
中间过程保存到 jsonl 文件
"""
import os
import sys
import json
import datetime
from pathlib import Path
from typing import Any, Dict, List

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.utils.llm_client import AIClient
from src.graph.propagation import Propagator
from src.agents.stock_tools.stock_type_config import classify_by_keywords
from src.graph.result_persister import save_analysis_report
# JSON 解析将在节点内处理

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
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
            "data": data
        }
        self.entries.append(entry)
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_node_start(self, node_name: str, state: Dict[str, Any]):
        self.log("node_start", {"state": self._sanitize_state(state)}, node_name)

    def log_node_end(self, node_name: str, state: Dict[str, Any], result: Any = None):
        self.log("node_end", {
            "state": self._sanitize_state(state),
            "result": str(result)[:1000] if result else None
        }, node_name)

    def log_llm_call(self, node_name: str, prompt: str, response: str):
        self.log("llm_call", {
            "prompt_length": len(prompt),
            "response_length": len(response) if response else 0,
            "response_preview": str(response)[:500] if response else None
        }, node_name)

    def log_error(self, node_name: str, error: str):
        self.log("error", {"error": error}, node_name)

    def _sanitize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not state:
            return {}
        safe = {}
        for k, v in state.items():
            if isinstance(v, str) and len(v) > 200:
                safe[k] = v[:200] + "..."
            else:
                safe[k] = v
        return safe


def create_analysis_node_with_llm(llm, analysis_type: str):
    """创建分析节点（直接调用 LLM，避免 ChatPromptTemplate 变量问题）"""

    if analysis_type == "cyclical":
        system_prompt = """你是一位专业的周期股分析师，专门分析周期性行业上市公司的财务状况和投资价值。

请基于以下财务数据，进行深入的周期股分析。

财务数据：
{financial_data}

分析指标：
{analysis_metrics}

请以 JSON 格式返回分析结果，包含以下字段：
- cycle_position: 当前周期位置（复苏/繁荣/衰退/萧条）
- capacity_utilization: 产能利用率 (0-100%)
- inventory_turnover_days: 存货周转天数
- capex_intensity: 资本支出强度（高/中/低）
- cash_flow_health: 现金流健康度评分 (0-100)
- pb_ratio: 市净率
- cape_ratio: 周期调整市盈率
- risk_factors: 风险因素列表
- investment_rating: 投资评级（BUY/HOLD/SELL）
- reasoning: 分析理由"""

        user_prompt = """请分析以下周期性行业公司的财务数据：

公司名称：{company_name}
股票代码：{stock_code}
报告期：{report_year}年 {report_period}

请给出详细的周期股分析报告。"""

    elif analysis_type == "fundamental":
        system_prompt = """你是一位专业的基本面分析师，通过分析上市公司的财务数据评估其投资价值。

请基于以下财务数据，进行全面的基本面分析。

财务数据：
{financial_data}

分析指标：
{analysis_metrics}

请以 JSON 格式返回分析结果，包含以下字段：
- profitability: 盈利能力指标 (gross_margin, net_margin, roe, roa)
- liquidity: 流动性指标 (current_ratio, quick_ratio, cash_ratio)
- solvency: 偿债能力指标 (debt_to_asset, debt_to_equity, interest_coverage)
- growth: 成长性指标 (revenue_growth, profit_growth)
- efficiency: 运营效率指标 (asset_turnover, inventory_turnover_days)
- investment_rating: 投资评级（BUY/HOLD/SELL）
- reasoning: 分析理由"""

        user_prompt = """请分析以下公司的基本面数据：

公司名称：{company_name}
股票代码：{stock_code}
报告期：{report_year}年 {report_period}

请给出详细的基本面分析报告。"""

    else:
        raise ValueError(f"Unknown analysis type: {analysis_type}")

    def node(state):
        company_name = state.get("company_name", "")
        stock_code = state.get("stock_code", "")
        report_year = state.get("report_year", "")
        report_period = state.get("report_period", "")

        # 模拟财务数据
        if analysis_type == "cyclical":
            financial_data = {
                "balance_sheet": {"total_assets": 13087136728, "total_equity": 9500000000, "inventory": 926000000},
                "income_statement": {"revenue": 5920785955, "net_profit": 1400000000},
                "cash_flow": {"operating_cash_flow": 1600000000, "free_cash_flow": 1300000000}
            }
            analysis_metrics = {
                "profitability": {"gross_margin": 58.1, "net_margin": 23.6, "roe": 14.7, "roa": 10.7},
                "liquidity": {"current_ratio": 4.0, "quick_ratio": 3.3, "cash_ratio": 1.94},
                "solvency": {"debt_to_asset": 27.4, "debt_to_equity": 0.38, "interest_coverage": 28.5},
                "growth": {"revenue_growth": 17.5, "profit_growth": 22.3}
            }
        else:
            financial_data = {
                "balance_sheet": {"total_assets": 13087136728, "total_liabilities": 3587136728, "total_equity": 9500000000,
                                  "current_assets": 7200000000, "cash": 5000000000, "inventory": 926000000},
                "income_statement": {"revenue": 5920785955, "operating_costs": 1633041966, "operating_profit": 1800000000,
                                      "net_profit": 1400000000},
                "cash_flow": {"operating_cash_flow": 1600000000, "investing_cash_flow": -300000000, "free_cash_flow": 1300000000}
            }
            analysis_metrics = {
                "profitability": {"gross_margin": 58.1, "net_margin": 23.6, "roe": 14.7, "roa": 10.7},
                "liquidity": {"current_ratio": 4.0, "quick_ratio": 3.3, "cash_ratio": 1.94},
                "solvency": {"debt_to_asset": 27.4, "debt_to_equity": 0.38, "interest_coverage": 28.5},
                "growth": {"revenue_growth": 17.5, "profit_growth": 22.3},
                "efficiency": {"asset_turnover": 0.45, "inventory_turnover_days": 210}
            }

        try:
            # 直接构建消息并调用 LLM
            from langchain_core.messages import HumanMessage, SystemMessage

            formatted_system = system_prompt.format(
                financial_data=json.dumps(financial_data, ensure_ascii=False, indent=2),
                analysis_metrics=json.dumps(analysis_metrics, ensure_ascii=False, indent=2)
            )
            formatted_user = user_prompt.format(
                company_name=company_name,
                stock_code=stock_code,
                report_year=report_year,
                report_period=report_period
            )

            messages = [
                SystemMessage(content=formatted_system),
                HumanMessage(content=formatted_user)
            ]

            # 直接调用 LLM
            response = llm.invoke(messages)

            # 解析 JSON 响应（直接获取文本内容）
            content = response.content if hasattr(response, 'content') else str(response)

            # 尝试提取 JSON（处理 markdown 代码块）
            json_text = content
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_text = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.rfind("```")
                json_text = content[start:end].strip()

            import json as json_module
            try:
                result = json_module.loads(json_text)
            except:
                # 如果 JSON 解析失败，返回原始文本
                result = {"raw_response": content, "parse_error": True}

            key = f"{analysis_type}_analysis"
            return {key: result}

        except Exception as e:
            logger.error(f"{analysis_type} 分析失败: {e}")
            import traceback
            traceback.print_exc()
            return {f"{analysis_type}_analysis": None, "error_msg": str(e)}

    return node


def create_summary_node(llm):
    """创建汇总节点"""
    system_prompt = """你是一位专业的投资顾问，负责汇总多个分析结果并给出最终投资建议。

请基于以下分析结果，进行综合评估并给出最终投资建议。

周期股分析结果：
{cyclical_result}

基本面分析结果：
{fundamental_result}

请以 JSON 格式返回汇总结果，包含以下字段：
- final_rating: 最终投资评级（BUY/HOLD/SELL）
- key_highlights: 核心亮点列表
- risk_factors: 风险因素列表
- investment_suggestion: 投资建议（详细说明）
"""

    user_prompt = """请综合以上分析结果，给出最终的投资建议。"""

    def node(state):
        cyclical = state.get("cyclical_analysis", {})
        fundamental = state.get("fundamental_analysis", {})

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            formatted_system = system_prompt.format(
                cyclical_result=json.dumps(cyclical, ensure_ascii=False, indent=2),
                fundamental_result=json.dumps(fundamental, ensure_ascii=False, indent=2)
            )

            messages = [
                SystemMessage(content=formatted_system),
                HumanMessage(content=user_prompt)
            ]

            response = llm.invoke(messages)

            # 解析 JSON 响应（直接获取文本内容）
            content = response.content if hasattr(response, 'content') else str(response)

            # 尝试提取 JSON
            json_text = content
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_text = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.rfind("```")
                json_text = content[start:end].strip()

            try:
                result = json.loads(json_text)
            except:
                result = {"raw_response": content, "parse_error": True}

            return {"summary": result}

        except Exception as e:
            logger.error(f"汇总失败: {e}")
            import traceback
            traceback.print_exc()
            return {"summary": None, "error_msg": str(e)}

    return node


def test_ej_aj_analysis():
    """测试东阿阿胶分析"""
    print("=" * 60)
    print("东阿阿胶 (000423) LangGraph 调试测试")
    print("=" * 60)

    jsonl_path = "D:/projects/FinancialAgent/data/000423/memory/langgraph_trace.jsonl"
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    conv_logger = ConversationLogger(jsonl_path)

    if os.path.exists(jsonl_path):
        os.remove(jsonl_path)

    conv_logger.log("session_start", {
        "company": "东阿阿胶",
        "stock_code": "000423",
        "report_year": 2025,
        "description": "LangGraph 调试模式测试 - 完整工作流"
    })

    # 1. 初始化 LLM
    print("\n[1] 初始化 LLM...")
    ai_client = AIClient({"TEMPERATURE": 0.7, "MAX_TOKENS": 4096})
    valid, err = ai_client.validate_config()
    if not valid:
        print(f"LLM 配置无效: {err}")
        conv_logger.log_error("init_llm", err)
        return
    llm = ai_client.llm
    print(f"LLM 初始化成功: {ai_client.get_model_name()}")
    conv_logger.log("llm_initialized", {"model": ai_client.get_model_name()})

    # 2. 股票类型分类
    print("\n[2] 股票类型分类...")
    company_name = "东阿阿胶"
    company_short_name = "东阿阿胶"
    stock_code = "000423"
    business_scope = "阿胶及阿胶系列产品、其他保健品、药用辅料、包装材料进出口业务的生产、销售；畜牧养殖；中药材种植、销售"

    text_for_classification = f"{company_name} {business_scope}"
    stock_types = classify_by_keywords(text_for_classification)
    print(f"  分类结果: {stock_types}")
    conv_logger.log("classification_result", {"stock_types": stock_types, "text": text_for_classification[:80]})

    # 3. 准备状态
    print("\n[3] 准备状态...")
    propagator = Propagator()
    state = propagator.create_initial_state(
        company_name=company_name,
        company_short_name=company_short_name,
        stock_code=stock_code,
        business_scope=business_scope,
        report_year=2024,
        report_period="FY"
    )
    state["stock_types"] = stock_types
    state["data_availability"] = {"has_data": True, "available_years": [2020, 2021, 2022, 2023, 2024], "data_coverage": 0.8}
    state["status"] = "processing"
    conv_logger.log("state_prepared", {"stock_types": stock_types})

    # 4. 创建节点
    print("\n[4] 创建分析节点...")
    cyclical_node = create_analysis_node_with_llm(llm, "cyclical")
    fundamental_node = create_analysis_node_with_llm(llm, "fundamental")
    summary_node = create_summary_node(llm)
    conv_logger.log("nodes_created", {"nodes": "all_created"})

    # 5. 执行周期股分析
    print("\n[5] 执行周期股分析...")
    conv_logger.log_node_start("run_cyclical_analysis", state)

    cyclical_state = cyclical_node(state.copy())
    cyclical_result = cyclical_state.get("cyclical_analysis")

    if cyclical_result:
        print(f"  周期股分析完成: {cyclical_result.get('investment_rating', 'N/A')}")
        conv_logger.log("analysis_result", cyclical_result, "run_cyclical_analysis")
    conv_logger.log_node_end("run_cyclical_analysis", cyclical_state, cyclical_result)
    state.update(cyclical_state)

    # 6. 执行基本面分析
    print("\n[6] 执行基本面分析...")
    conv_logger.log_node_start("run_fundamental_analysis", state)

    fundamental_state = fundamental_node(state.copy())
    fundamental_result = fundamental_state.get("fundamental_analysis")

    if fundamental_result:
        print(f"  基本面分析完成: {fundamental_result.get('investment_rating', 'N/A')}")
        conv_logger.log("analysis_result", fundamental_result, "run_fundamental_analysis")
    conv_logger.log_node_end("run_fundamental_analysis", fundamental_state, fundamental_result)
    state.update(fundamental_state)

    # 7. 执行汇总
    print("\n[7] 执行投资汇总...")
    conv_logger.log_node_start("run_summary", state)

    summary_state = summary_node(state.copy())
    summary_result = summary_state.get("summary")

    if summary_result:
        print(f"  汇总完成: {summary_result.get('final_rating', 'N/A')}")
        conv_logger.log("summary_result", summary_result, "run_summary")
    conv_logger.log_node_end("run_summary", summary_state, summary_result)
    state.update(summary_state)

    # 8. 输出结果
    print("\n" + "=" * 60)
    print("分析结果")
    print("=" * 60)
    conv_logger.log("final_result", {
        "status": state.get('status'),
        "stock_types": state.get('stock_types', [])
    })

    print(f"状态: {state.get('status')}")
    print(f"股票类型: {state.get('stock_types', [])}")

    if state.get('cyclical_analysis'):
        print("\n--- 周期股分析 ---")
        ca = state.get('cyclical_analysis')
        if isinstance(ca, dict):
            for key, value in ca.items():
                if isinstance(value, str) and len(value) > 300:
                    print(f"\n{key}:\n  {value}")
                else:
                    print(f"  {key}: {value}")

    if state.get('fundamental_analysis'):
        print("\n--- 基本面分析 ---")
        fa = state.get('fundamental_analysis')
        if isinstance(fa, dict):
            for key, value in fa.items():
                if isinstance(value, str) and len(value) > 300:
                    print(f"\n{key}:\n  {value}")
                else:
                    print(f"  {key}: {value}")

    if state.get('summary'):
        print("\n--- 投资总结 ---")
        summary = state.get('summary')
        if isinstance(summary, dict):
            for key, value in summary.items():
                if isinstance(value, str):
                    print(f"\n{key}:\n  {value}")
                elif isinstance(value, list):
                    print(f"\n{key}:")
                    for item in value:
                        print(f"  - {item}")
                else:
                    print(f"  {key}: {value}")

    conv_logger.log("session_end", {"total_entries": len(conv_logger.entries)})
    print(f"\n对话流程已保存到: {jsonl_path}")

    # 9. 保存分析报告
    print("\n[9] 保存分析报告...")
    try:
        report_path = save_analysis_report(
            jsonl_path=jsonl_path,
            company_name=company_name,
            stock_code=stock_code
        )
        print(f"  分析报告已保存到: {report_path}")
    except Exception as e:
        print(f"  保存报告失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n测试完成!")


if __name__ == "__main__":
    test_ej_aj_analysis()