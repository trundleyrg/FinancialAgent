"""
分析结果持久化模块

从 jsonl 文件中提取各 Agent 的分析结果，拼接成完整报告并保存为 Markdown 文档
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


def load_trace_from_jsonl(jsonl_path: str) -> List[Dict[str, Any]]:
    """从 jsonl 文件加载对话追踪记录"""
    entries = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def extract_analysis_results(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从追踪记录中提取各 Agent 的分析结果"""
    results = {
        "session_info": {},
        "classification": {},
        "cyclical_analysis": None,
        "fundamental_analysis": None,
        "summary": None
    }

    for entry in entries:
        event_type = entry.get("event_type")
        data = entry.get("data", {})
        node_name = entry.get("node_name")

        if event_type == "session_start":
            results["session_info"] = data
        elif event_type == "classification_result":
            results["classification"] = data
        elif event_type == "analysis_result":
            if node_name == "run_cyclical_analysis":
                results["cyclical_analysis"] = data
            elif node_name == "run_fundamental_analysis":
                results["fundamental_analysis"] = data
        elif event_type == "summary_result":
            results["summary"] = data

    return results


def build_markdown_report(results: Dict[str, Any]) -> str:
    """将分析结果拼接成 Markdown 报告"""
    session = results.get("session_info", {})
    classification = results.get("classification", {})
    cyclical = results.get("cyclical_analysis") or {}
    fundamental = results.get("fundamental_analysis") or {}
    summary = results.get("summary") or {}

    # 时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = f"""# {session.get('company', '未知公司')} ({session.get('stock_code', '未知代码')}) 投资分析报告

> 生成时间: {timestamp}
> 报告期: {session.get('report_year', '未知年份')}

---

## 一、公司概况与股票分类

### 1.1 公司信息

- **公司名称**: {session.get('company', '未知')}
- **股票代码**: {session.get('stock_code', '未知')}
- **报告年份**: {session.get('report_year', '未知')}

### 1.2 股票类型分类

基于公司经营范围关键词匹配，分类结果为：

{chr(10).join([f'- **{st}**' for st in classification.get('stock_types', [])]) or '- 未分类'}

---

## 二、周期股分析

### 2.1 周期定位与关键指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 周期位置 | {cyclical.get('cycle_position', 'N/A')} | 当前所处经济周期阶段 |
| 产能利用率 | {cyclical.get('capacity_utilization', 'N/A')} | 产能利用情况 |
| 存货周转天数 | {cyclical.get('inventory_turnover_days', 'N/A')} | 库存管理效率 |
| CAPEX 强度 | {cyclical.get('capex_intensity', 'N/A')} | 资本支出强度 |
| 现金流健康度 | {cyclical.get('cash_flow_health', 'N/A')}/100 | 综合评分 |
| PB 市净率 | {cyclical.get('pb_ratio', 'N/A')} | 估值指标 |
| CAPE | {cyclical.get('cape_ratio', 'N/A')} | 周期调整市盈率 |

### 2.2 风险因素

{chr(10).join([f'- {risk}' for risk in cyclical.get('risk_factors', [])]) or '- 暂无'}

### 2.3 分析结论

**投资评级: {cyclical.get('investment_rating', 'N/A')}**

{cyclical.get('reasoning', '暂无分析理由')}

---

## 三、基本面分析

### 3.1 盈利能力

| 指标 | 数值 | 评价 |
|------|------|------|
| 毛利率 | {fundamental.get('profitability', {}).get('gross_margin', 'N/A')}% | {fundamental.get('profitability', {}).get('analysis', '')} |
| 净利率 | {fundamental.get('profitability', {}).get('net_margin', 'N/A')}% | - |
| ROE | {fundamental.get('profitability', {}).get('roe', 'N/A')}% | - |
| ROA | {fundamental.get('profitability', {}).get('roa', 'N/A')}% | - |

### 3.2 流动性指标

| 指标 | 数值 | 评价 |
|------|------|------|
| 流动比率 | {fundamental.get('liquidity', {}).get('current_ratio', 'N/A')} | {fundamental.get('liquidity', {}).get('analysis', '')} |
| 速动比率 | {fundamental.get('liquidity', {}).get('quick_ratio', 'N/A')} | - |
| 现金比率 | {fundamental.get('liquidity', {}).get('cash_ratio', 'N/A')} | - |

### 3.3 偿债能力

| 指标 | 数值 | 评价 |
|------|------|------|
| 资产负债率 | {fundamental.get('solvency', {}).get('debt_to_asset', 'N/A')}% | {fundamental.get('solvency', {}).get('analysis', '')} |
| 产权比率 | {fundamental.get('solvency', {}).get('debt_to_equity', 'N/A')} | - |
| 利息保障倍数 | {fundamental.get('solvency', {}).get('interest_coverage', 'N/A')}x | - |

### 3.4 成长性

| 指标 | 数值 | 评价 |
|------|------|------|
| 营收增长率 | {fundamental.get('growth', {}).get('revenue_growth', 'N/A')}% | {fundamental.get('growth', {}).get('analysis', '')} |
| 净利润增长率 | {fundamental.get('growth', {}).get('profit_growth', 'N/A')}% | - |

### 3.5 运营效率

| 指标 | 数值 | 评价 |
|------|------|------|
| 资产周转率 | {fundamental.get('efficiency', {}).get('asset_turnover', 'N/A')} | {fundamental.get('efficiency', {}).get('analysis', '')} |
| 存货周转天数 | {fundamental.get('efficiency', {}).get('inventory_turnover_days', 'N/A')} | - |

### 3.6 分析结论

**投资评级: {fundamental.get('investment_rating', 'N/A')}**

{fundamental.get('reasoning', '暂无分析理由')}

---

## 四、综合投资建议

### 4.1 最终评级

**{summary.get('final_rating', 'N/A')}**

### 4.2 核心亮点

{chr(10).join([f'- {highlight}' for highlight in summary.get('key_highlights', [])]) or '- 暂无'}

### 4.3 风险提示

{chr(10).join([f'- {risk}' for risk in summary.get('risk_factors', [])]) or '- 暂无'}

### 4.4 投资建议

{summary.get('investment_suggestion', '暂无投资建议')}

---

## 五、分析方法说明

本报告由 **FinancialAgent** 智能投研系统生成，采用以下分析方法：

1. **股票类型分类**: 基于公司经营范围关键词匹配，识别股票类型（周期股/成长股/防御股等）
2. **周期股分析**: 评估行业周期位置、产能利用率、现金流健康度、PB/CAPE 估值
3. **基本面分析**: 多维度财务指标分析（盈利、流动性、偿债、成长、效率）
4. **综合汇总**: 基于多维度分析给出最终投资建议

---

> 本报告仅供参考，不构成投资建议。投资有风险，决策需谨慎。
"""
    return md


def save_analysis_report(
    jsonl_path: str,
    output_dir: Optional[str] = None,
    company_name: Optional[str] = None,
    stock_code: Optional[str] = None
) -> str:
    """保存分析报告到文件

    Args:
        jsonl_path: jsonl 文件路径
        output_dir: 输出目录，默认与 jsonl 同目录
        company_name: 公司名称（用于输出文件名）
        stock_code: 股票代码（用于输出文件名）

    Returns:
        保存的 Markdown 文件路径
    """
    # 加载追踪记录
    entries = load_trace_from_jsonl(jsonl_path)

    # 提取分析结果
    results = extract_analysis_results(entries)

    # 获取公司信息
    session = results.get("session_info", {})
    company = company_name or session.get("company", "未知公司")
    code = stock_code or session.get("stock_code", "000000")

    # 确定输出目录
    if output_dir is None:
        output_dir = os.path.dirname(jsonl_path)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"分析报告_{company}_{code}_{timestamp}.md"
    output_path = os.path.join(output_dir, filename)

    # 构建并保存报告
    md_content = build_markdown_report(results)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return output_path


if __name__ == "__main__":
    # 示例用法
    jsonl_path = "D:/projects/FinancialAgent/data/000423/mmemory/langgraph_trace.jsonl"
    output_path = save_analysis_report(jsonl_path)
    print(f"分析报告已保存到: {output_path}")