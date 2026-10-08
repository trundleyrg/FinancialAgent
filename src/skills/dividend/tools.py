"""红利股 skill 专属工具：从财务数据提取分红信息，DB 优先读分红统计。"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.db.db_connector import get_db
from src.tools.market_data_tool import get_dividend_stats

logger = logging.getLogger("Skills.Dividend")


# dividend skill 真正消费的所有字段（来自 extract_dividend_info +
# calculate_profitability/liquidity/solvency）。送进 LLM prompt 前用
# filter_financial_data 过滤掉无关字段以减小体积 — MiniMax M3.1-Flash-Preview
# 在 sys prompt 含全量 230 字段时会静默回空响应（~10K 字符触发），过滤后通常 < 2K。
DIVIDEND_RELEVANT_FIELDS: Dict[str, list] = {
    "balance_sheet": [
        "total_assets", "total_liabilities",
        "total_owners_equity", "total_equity",
        "current_assets", "current_liabilities",
        "monetary_funds", "inventory",
    ],
    "income_statement": [
        "operating_revenue",
        "gross_profit", "operating_costs", "operating_cost",
        "net_profit", "net_profit_attributable_to_parent", "total_profit",
        "operating_profit", "ebit",
        "interest_expense", "financial_expenses", "equity",
    ],
    "cash_flow": [
        "net_cash_from_operations", "operating_cash_flow",
        "cash_for_dividend_and_interest",
        "cash_for_fixed_assets",
    ],
}


def filter_financial_data(financial_data: Dict[str, Any]) -> Dict[str, Any]:
    """把全量财务数据过滤到 dividend skill 真正消费的字段。

    保留 None 值字段（None 会序列化为 null，便于 LLM 看出字段缺失）；
    完全缺失的字段则不写入 dict。
    """
    result: Dict[str, Any] = {}
    for table, fields in DIVIDEND_RELEVANT_FIELDS.items():
        raw = financial_data.get(table) or {}
        result[table] = {k: raw.get(k) for k in fields if k in raw}
    return result


def _pick_net_profit(income_statement: Dict[str, Any]) -> float:
    """净利润字段在 PDF 中常用别名：net_profit / net_profit_attributable_to_parent / total_profit。

    优先级：合并口径 → 母公司口径 → 总利润。
    """
    for key in ("net_profit", "net_profit_attributable_to_parent", "total_profit"):
        v = income_statement.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def _compute_dividend_stability_years(
    stock_code: str, current_year: int, period: str = "FY",
) -> int:
    """从 capital_change_events 推算截至 current_year 的连续分红年数。

    算法：从 current_year 往前逐 year 查找 cash_dividend 事件，只要该年
    有任意一笔 cash_per_10_shares > 0 的事件，年数 +1；遇到首断则停止。
    """
    try:
        conn = get_db()._duckdb_conn
    except Exception:
        return 0
    years = 0
    for back in range(0, 10):
        year = current_year - back
        row = conn.execute(
            """
            SELECT COUNT(*) FROM capital_change_events
            WHERE stock_code = ?
              AND report_year = ?
              AND report_period = ?
              AND event_type = 'cash_dividend'
              AND cash_per_10_shares IS NOT NULL
              AND cash_per_10_shares > 0
            """,
            [stock_code, year, period],
        ).fetchone()
        if row and row[0] > 0:
            years += 1
        else:
            break
    return years


def extract_dividend_info(financial_data: Dict[str, Any]) -> Dict[str, Any]:
    """从财务数据中提取分红相关信息。

    数据来源优先级：
    1. 现金流量表 cash_for_dividend_and_interest（实际现金分红支出）
    2. 计算自由现金流 = 经营活动现金流 - 购建固定资产现金支出
    3. 净利润字段多别名（net_profit / net_profit_attributable_to_parent / total_profit）

    Args:
        financial_data: 财务数据字典（含 balance_sheet / income_statement / cash_flow）

    Returns:
        分红信息字典
    """
    income_statement = financial_data.get("income_statement", {})
    cash_flow = financial_data.get("cash_flow", {})

    net_profit = _pick_net_profit(income_statement)
    operating_cash_flow = (
        cash_flow.get("net_cash_from_operations", 0)
        or cash_flow.get("operating_cash_flow", 0)
        or 0
    )

    # 实际现金分红支出（来自现金流量表"分配股利、利润或偿付利息支付的现金"）
    cash_dividend_paid = cash_flow.get("cash_for_dividend_and_interest", 0) or 0

    # 自由现金流 = 经营现金流 - 购建固定资产等资本支出
    capex = cash_flow.get("cash_for_fixed_assets", 0) or 0
    free_cash_flow = operating_cash_flow - capex

    payout_ratio = (cash_dividend_paid / net_profit * 100) if net_profit > 0 else 0.0
    fcf_coverage = (free_cash_flow / cash_dividend_paid) if cash_dividend_paid > 0 else 0.0

    return {
        "net_profit": net_profit,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
        "cash_dividend_paid": cash_dividend_paid,   # 实际现金分红支出（元）
        "payout_ratio": round(payout_ratio, 2),      # 分红率（%）
        "fcf_coverage": round(fcf_coverage, 2),      # 自由现金流对分红覆盖倍数
    }


def compute_dividend_stability_years(
    stock_code: str, current_year: int, period: str = "FY",
) -> int:
    """包装 `_compute_dividend_stability_years`，供 skill 调用并写入 state。"""
    return _compute_dividend_stability_years(stock_code, current_year, period)


def get_dividend_stats_with_fallback(
    stock_code: str, years: int = 5,
) -> Dict[str, Any]:
    """DB 优先读 CapitalChangeEventRepository；空时退到 akshare 实时拉取。"""
    try:
        from src.db import CapitalChangeEventRepository, ReportKey
        from src.db.db_connector import get_db
        repo = CapitalChangeEventRepository(get_db())
        events = repo.list_events(ReportKey(stock_code=stock_code))
        if events:
            stats = repo.aggregate_dividend_stats(
                ReportKey(stock_code=stock_code), years=years,
            )
            stats["source"] = "db"
            stats["total_event_count"] = len(events)
            return stats
    except Exception as exc:
        logger.warning(
            "DB 分红读取失败 (%s): %s — fallback 到实时拉取",
            stock_code, exc,
        )
    stats = get_dividend_stats(stock_code, years=years)
    if isinstance(stats, dict):
        stats["source"] = "live"
    return stats


def render_dividend_trend_chart(
    multi_year_summary: dict[str, dict[str, Any]],
    output_path: str | Path,
    title: str | None = None,
    metric_explanations: dict[str, str] | None = None,
) -> tuple[Path, pd.DataFrame]:
    """把 dividend skill 的 multi_year_summary 渲染成 3 子图趋势 + 表格。

    子图 1: 营业收入(亿元)
    子图 2: 归母净利润(亿元)
    子图 3: 分红率(%) = cash_for_dividend_and_interest / net_profit * 100
            缺失年份该指标为 None,subplot 自然跳过。

    Args:
        multi_year_summary: 与 skill.py 里的 multi_year_summary 同形
            {year_str: {"operating_revenue": float|None, "net_profit": float|None,
                         "cash_for_dividend_and_interest": float|None, ...}}
        output_path: PNG 写入路径。
        title: 整图标题。None 时使用通用默认"分红股关键指标趋势"。
        metric_explanations: {metric 显示名: 解释文本(计算公式/定义)},
            渲染到图片下方居中。常见用法:把分红率的计算公式传进来。
            例:{"分红率(%)": "现金分红 / 归母净利润 × 100"}
            None 或空 dict 不渲染。

    Returns:
        (chart_path, table) 二元组:
        - chart_path: 写入的 PNG 路径(Path)。
        - table: build_trend_table() 的结果(DataFrame),
                 index=年份字符串(字典序), columns=3 个 metric(中文 label)。
    """
    from src.tools.visualization import render_trend_chart_and_table

    series: dict[str, dict[str, float]] = {}
    for year, m in multi_year_summary.items():
        net_profit = m.get("net_profit")
        cash_div = m.get("cash_for_dividend_and_interest")
        payout_ratio: float | None = None
        if cash_div is not None and net_profit is not None and net_profit > 0:
            payout_ratio = round(cash_div / net_profit * 100, 2)
        series[str(year)] = {
            "营业收入(亿元)": (
                m["operating_revenue"] / 1e8
                if m.get("operating_revenue") is not None else None  # type: ignore[dict-item]
            ),
            "归母净利润(亿元)": (
                net_profit / 1e8 if net_profit else None  # type: ignore[dict-item]
            ),
            "分红率(%)": payout_ratio,
        }
    return render_trend_chart_and_table(
        series,
        output_path=output_path,
        title=title if title is not None else "分红股关键指标趋势",
        x_label="年份",
        metric_explanations=metric_explanations,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 红利分析 markdown 报告
# ──────────────────────────────────────────────────────────────────────────────

from decimal import ROUND_HALF_UP, Decimal


def _round_half_up(x: float, n: int) -> float:
    """四舍五入(标准数学四舍五入,非银行家舍入)保留 n 位小数。

    Python 内置 ``round()`` 和 ``f"{x:.2f}"`` 都用 ROUND_HALF_EVEN(银行家舍入),
    0.5 时往偶数方向走(round(0.5) == 0, round(1.5) == 2)。这跟中文用户
    习惯的「四舍五入」(ROUND_HALF_UP, 0.5 一律往上入)不一致,改用 Decimal。
    """
    if not isinstance(x, (int, float)):
        return x  # type: ignore[return-value]
    if isinstance(x, float) and x != x:  # NaN
        return x
    if isinstance(x, float) and x in (float("inf"), float("-inf")):
        return x
    quant = Decimal(10) ** -n
    return float(Decimal(str(x)).quantize(quant, rounding=ROUND_HALF_UP))


def _md_escape_cell(value: Any) -> str:
    """转义 markdown 表格 cell 里的 `|` 和换行,避免破坏表格结构。"""
    if value is None:
        return ""
    s = str(value)
    s = s.replace("|", "\\|")
    s = s.replace("\r\n", "\n").replace("\n", "<br>")
    return s


def _md_format_number(value: Any) -> str:
    """表格数字 cell:float → 四舍五入 2 位小数、int → 原样、NaN/None → "N/A"。

    用于趋势表和 LLM 结论表的所有数字 cell,与「四舍五入」习惯保持一致。
    """
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return "N/A"
        return f"{_round_half_up(value, 2):.2f}"
    return _md_escape_cell(value)


def _md_format_value(value: Any) -> str:
    """把 LLM 输出值格式化成表格显示文本。None → "N/A"、float → 2 位小数。

    数字部分委托 ``_md_format_number``,保证 2 位小数 + 四舍五入口径一致。
    """
    if value is None:
        return "N/A"
    if isinstance(value, float):
        if value != value:  # NaN
            return "N/A"
    return _md_format_number(value)


def _df_to_markdown_table(df: pd.DataFrame) -> str:
    """把 DataFrame 转成 markdown 表格(首列用 index 名 / index 值)。

    数字 cell 走 ``_md_format_number`` 做四舍五入 2 位小数,字符串 cell 走
    ``_md_escape_cell`` 仅做转义。index 如果是 int(如年份)按数字格式。
    """
    cols = list(df.columns)
    header_cells = [_md_escape_cell(df.index.name or "")] + [
        _md_escape_cell(c) for c in cols
    ]
    lines = [
        "| " + " | ".join(header_cells) + " |",
        "|" + "|".join(["------"] * len(header_cells)) + "|",
    ]
    for idx, row in df.iterrows():
        idx_cell = (
            _md_format_number(idx) if isinstance(idx, (int, float)) and not isinstance(idx, bool)
            else _md_escape_cell(idx)
        )
        cells = [idx_cell] + [_md_format_number(row[c]) for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_dividend_markdown(
    result: Dict[str, Any],
    *,
    chart_path: Optional[str] = None,
    table: Optional[pd.DataFrame] = None,
    company_name: Optional[str] = None,
    stock_code: Optional[str] = None,
    report_year: Optional[int] = None,
    report_period: Optional[str] = None,
) -> str:
    """把 dividend skill 的 LLM 结果 + 趋势图 + 趋势表渲染成自包含 markdown 报告。

    章节顺序固定(图在上、表格在下):
    1. 标题 + 元数据
    2. 一、关键指标趋势:图(若有) + 多年趋势表(若有)
    3. 二、关键指标:股息率 / 分红率 / 连续分红年限 / 现金流覆盖 / 健康度评分
    4. 三-五、盈利能力 / 偿债能力 / 估值(子表)
    5. 六、风险因素(列表)
    6. 七、投资评级 + 推理文本

    Args:
        result: LLM 输出的 dict,字段参见 src/skills/dividend/SKILL.md。
            顶层: dividend_yield / payout_ratio / dividend_stability_years /
            cash_flow_coverage / financial_health_score / investment_rating /
            reasoning / risk_factors;
            嵌套: profitability {gross_margin, net_margin, roe},
            solvency {debt_to_asset}, valuation {pe_ratio, pb_ratio}。
        chart_path: 嵌入 markdown 的图路径(通常是相对 markdown 文件目录的相对路径,
            例 "charts/dividend_trend_2024.png");None 时跳过一、图。
        table: 多年趋势 DataFrame(由 build_trend_table 生成);
               None 或空 DataFrame 时跳过一、表。
        company_name / stock_code / report_year / report_period: 用于标题与元数据;
            缺省时回落到 "未知xxx"。

    Returns:
        完整 markdown 字符串(UTF-8,LF 换行)。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 标题 + 元数据
    title = f"# 红利股分析报告 - {company_name or '未知公司'}"
    if stock_code:
        title += f" ({stock_code})"
    if report_year is not None:
        title += f" {report_year}年报"

    header_lines: list[str] = [title, ""]
    header_lines.append(f"> 生成时间: {timestamp}")
    if report_year is not None:
        header_lines.append(
            f"> 报告期: {report_year}年 {report_period or '未知'}"
        )
    header_lines += ["", "---", ""]

    # 2. 一、关键指标趋势(图 + 表)
    trend_lines: list[str] = ["## 一、关键指标趋势", ""]
    if chart_path:
        alt = f"{company_name or '公司'} 红利股关键指标趋势"
        trend_lines.append(f"![{alt}]({chart_path})")
        trend_lines.append("")
    if table is not None and not table.empty:
        trend_lines.append(_df_to_markdown_table(table))
        trend_lines.append("")
    if not chart_path and (table is None or table.empty):
        trend_lines.append("*（趋势图/表数据缺失）*")
        trend_lines.append("")
    trend_lines += ["---", ""]

    # 3. 二、关键指标
    key_rows = [
        ("股息率(%)", result.get("dividend_yield")),
        ("分红率(%)", result.get("payout_ratio")),
        ("连续分红年限(年)", result.get("dividend_stability_years")),
        ("自由现金流对分红覆盖率(倍)", result.get("cash_flow_coverage")),
        ("财务健康度评分(0-100)", result.get("financial_health_score")),
    ]
    key_lines = ["## 二、关键指标", ""]
    key_lines.append("| 指标 | 数值 |")
    key_lines.append("|------|------|")
    for name, value in key_rows:
        key_lines.append(f"| {name} | {_md_format_value(value)} |")
    key_lines += ["", "---", ""]

    # 4. 三-五、子能力指标
    profit = result.get("profitability") or {}
    solv = result.get("solvency") or {}
    val = result.get("valuation") or {}

    sub_sections: list[tuple[str, list[tuple[str, Any]]]] = [
        ("## 三、盈利能力", [
            ("毛利率(%)", profit.get("gross_margin")),
            ("净利率(%)", profit.get("net_margin")),
            ("ROE(%)", profit.get("roe")),
        ]),
        ("## 四、偿债能力", [
            ("资产负债率(%)", solv.get("debt_to_asset")),
        ]),
        ("## 五、估值", [
            ("市盈率(倍)", val.get("pe_ratio")),
            ("市净率(倍)", val.get("pb_ratio")),
        ]),
    ]
    sub_lines: list[str] = []
    for heading, rows in sub_sections:
        sub_lines += [heading, "", "| 指标 | 数值 |", "|------|------|"]
        for name, value in rows:
            sub_lines.append(f"| {name} | {_md_format_value(value)} |")
        sub_lines.append("")
    sub_lines += ["---", ""]

    # 5. 六、风险因素
    risk_lines = ["## 六、风险因素", ""]
    risks = result.get("risk_factors")
    if isinstance(risks, list) and risks:
        for r in risks:
            risk_lines.append(f"- {_md_escape_cell(r)}")
    else:
        risk_lines.append("- 暂无")
    risk_lines += ["", "---", ""]

    # 6. 七、投资评级与理由
    rating = result.get("investment_rating", "N/A")
    reasoning = result.get("reasoning") or "暂无分析理由"
    rating_lines = [
        "## 七、投资评级与理由",
        "",
        f"**投资评级: {rating}**",
        "",
        reasoning,
        "",
    ]

    return "\n".join(
        header_lines + trend_lines + key_lines + sub_lines +
        risk_lines + rating_lines,
    )
