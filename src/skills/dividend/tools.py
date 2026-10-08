"""红利股 skill 专属工具：从财务数据提取分红信息，DB 优先读分红统计。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

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
    )
