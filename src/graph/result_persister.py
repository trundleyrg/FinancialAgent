"""
分析结果持久化模块

从 jsonl 文件中提取各 Agent 的分析结果，拼接成完整报告并保存为 Markdown 文档
"""
import json
import os
import re
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


def load_dividend_data(memory_dir: str | Path) -> Optional[Dict[str, Any]]:
    """从 memory_dir 里读最新的 `分析报告_分红_*.md`,提取趋势表 + 关键指标。

    返回 dict:
        {
            "source_md_name": str,
            "trend_table_md": str,    # 完整 markdown 表格(含表头+分隔行+数据行)
            "key_indicators": dict,   # {"股息率(%)": "4.50", ...}
            "risk_factors": list[str],
            "investment_rating": str, # "BUY" / "HOLD" / "SELL"
        }
        或 None(没找到 dividend md 时)

    这是主报告整合 dividend 分析的桥梁:dividend skill 自己已生成独立 markdown,
    我们这里再把它的事实数字(趋势表)+ 判断结果(评级/风险)汇总进主报告。
    """
    memory_dir = Path(memory_dir)
    if not memory_dir.is_dir():
        return None

    md_files = sorted(memory_dir.glob("分析报告_分红_*.md"))
    if not md_files:
        return None
    latest = md_files[-1]
    text = latest.read_text(encoding="utf-8")

    # ── 趋势表 ──
    # 找 markdown 表格块(以 | 开头的连续行)
    table_lines: list[str] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("|"):
            table_lines.append(line)
            in_table = True
        elif in_table and line.strip() == "":
            # 表格结束
            break
        elif in_table and not line.startswith("|"):
            # 表格结束了
            break
    trend_table_md = "\n".join(table_lines) if table_lines else ""

    # ── 关键指标(## 二、关键指标 段) ──
    key_indicators: Dict[str, str] = {}
    m = re.search(
        r"## 二、关键指标\s*\n(.+?)(?=\n##|\Z)",
        text, re.DOTALL,
    )
    if m:
        section = m.group(1)
        for row in re.findall(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", section):
            name, value = row
            n = name.strip()
            v = value.strip()
            # 跳过空、分隔行(---)以及 markdown 表头本身(指标 / 数值)
            if not n or not v or "---" in n or "---" in v:
                continue
            if n in ("指标", "数值"):
                continue
            key_indicators[n] = v

    # ── 风险因素(## 六、风险因素 段) ──
    risk_factors: list[str] = []
    m = re.search(
        r"## 六、风险因素\s*\n(.+?)(?=\n##|\Z)",
        text, re.DOTALL,
    )
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                risk_factors.append(line[2:].strip())

    # ── 投资评级 ──
    investment_rating = ""
    m = re.search(r"\*\*投资评级:\s*([A-Z]+)\*\*", text)
    if m:
        investment_rating = m.group(1).strip()

    return {
        "source_md_name": latest.name,
        "trend_table_md": trend_table_md,
        "key_indicators": key_indicators,
        "risk_factors": risk_factors,
        "investment_rating": investment_rating,
    }


def build_markdown_report(
    results: Dict[str, Any],
    memory_dir: str | Path | None = None,
) -> str:
    """将分析结果拼接成 Markdown 报告

    Args:
        results: extract_analysis_results 返回的 dict
        memory_dir: 用于查找 `分析报告_分红_*.md` 等子产物,
            找到则嵌入「红利股分析」section;None 或没找到则跳过该 section。
    """
    session = results.get("session_info", {})
    classification = results.get("classification", {})
    cyclical = results.get("cyclical_analysis") or {}
    fundamental = results.get("fundamental_analysis") or {}
    summary = results.get("summary") or {}

    # 红利股分析数据(从独立的分红 markdown 报告里抓)
    dividend = load_dividend_data(memory_dir) if memory_dir else None

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
"""
    # ── 四、红利股分析(可选,依赖 memory_dir 下有没有 dividend 报告) ──
    dividend_section = ""
    tail = ""
    if dividend and (dividend.get("trend_table_md") or dividend.get("key_indicators")):
        div_table = dividend.get("trend_table_md") or "*(趋势表缺失)*"
        div_indicators = dividend.get("key_indicators") or {}
        div_risks = dividend.get("risk_factors") or []
        div_rating = dividend.get("investment_rating") or "N/A"
        div_source = dividend.get("source_md_name", "")

        if div_indicators:
            indicator_rows = "\n".join(
                f"| {k} | {v} |" for k, v in div_indicators.items()
            )
            indicator_table = indicator_rows  # 仅数据行,表头在外层模板里
        else:
            indicator_table = "| 数值 | N/A |"

        risk_md = (
            "\n".join(f"- {r}" for r in div_risks) if div_risks else "- 暂无"
        )

        dividend_section = f"""## 四、红利股分析

> 数据来源: `{div_source}`(由 dividend skill 独立生成,本报告汇总展示)

### 4.1 多年关键指标趋势(分红)

{div_table}

> **口径说明**:分红率(%) = 现金分红总额 / 归母净利润 × 100。
  送转股(10送X / 10转X)未折算进比率,详见「拆股情况」列。

### 4.2 当年关键指标

| 指标 | 数值 |
|------|------|
{indicator_table}

### 4.3 分红风险因素

{risk_md}

### 4.4 分红评级

**投资评级: {div_rating}**

---
"""

    # 综合投资建议 + 分析方法说明(编号随 dividend 是否存在而平移)
    if dividend_section:
        tail = f"""## 五、综合投资建议

### 5.1 最终评级

**{summary.get('final_rating', 'N/A')}**

### 5.2 核心亮点

{chr(10).join([f'- {highlight}' for highlight in summary.get('key_highlights', [])]) or '- 暂无'}

### 5.3 风险提示

{chr(10).join([f'- {risk}' for risk in summary.get('risk_factors', [])]) or '- 暂无'}

### 5.4 投资建议

{summary.get('investment_suggestion', '暂无投资建议')}

---

## 六、分析方法说明

本报告由 **FinancialAgent** 智能投研系统生成，采用以下分析方法：

1. **股票类型分类**: 基于公司经营范围关键词匹配，识别股票类型（周期股/成长股/防御股等）
2. **周期股分析**: 评估行业周期位置、产能利用率、现金流健康度、PB/CAPE 估值
3. **基本面分析**: 多维度财务指标分析（盈利、流动性、偿债、成长、效率）
4. **红利股分析**: 分红历史、连续年限、股息率与分红率、自由现金流覆盖率
5. **综合汇总**: 基于多维度分析给出最终投资建议

---
"""
    else:
        tail = f"""## 四、综合投资建议

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
"""

    md += dividend_section + tail + "\n> 本报告仅供参考，不构成投资建议。投资有风险，决策需谨慎。\n"
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

    # 构建并保存报告(memory_dir = jsonl 同目录,用于查找 `分析报告_分红_*.md`)
    md_content = build_markdown_report(results, memory_dir=output_dir)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return output_path


if __name__ == "__main__":
    # 示例用法
    jsonl_path = "D:/projects/FinancialAgent/data/000423/mmemory/langgraph_trace.jsonl"
    output_path = save_analysis_report(jsonl_path)
    print(f"分析报告已保存到: {output_path}")