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


def _compute_payout_from_events(
    events: list[dict[str, Any]],
    total_shares: float | None,
    net_profit: float | None,
) -> float | None:
    """从申报分红事件算分红率(%):Σ(cash_per_10_shares/10 × total_shares) / net_profit × 100。

    只统计 event_type ∈ ('cash_dividend', 'combination') 且 cash_per_10_shares > 0
    的事件,其他事件类型(送股/转增/配股)跳过,因为它们不含现金。

    返回 None 时调用方应退回到现金流字段(``cash_for_dividend_and_interest``)。
    """
    if not events or not total_shares or total_shares <= 0:
        return None
    if net_profit is None or net_profit <= 0:
        return None
    total: float = 0.0
    for ev in events:
        ev_type = ev.get("event_type")
        cps = ev.get("cash_per_10_shares")
        if ev_type not in ("cash_dividend", "combination"):
            continue
        if cps is None or cps <= 0:
            continue
        total += float(cps) / 10.0 * float(total_shares)
    if total <= 0:
        return None
    return round(total / net_profit * 100, 2)


def _is_financial_data_empty(
    financial_data: dict[str, Any] | None,
    keys: tuple[str, ...] = (
        "balance_sheet", "income_statement", "cash_flow",
    ),
) -> bool:
    """判断财务数据是否实质为空(所有 3 张表都没有任何非 None 字段)。

    用于 fail-fast:PDF 解析失败或数据未入库时,3 张表全空,
    不让 skill 继续算 0% 噪音指标并写入 DB / markdown。
    """
    if not financial_data:
        return True
    for key in keys:
        table = financial_data.get(key)
        if isinstance(table, dict) and any(v is not None for v in table.values()):
            return False
    return True


def _sum_dividend_from_events(
    events: list[dict[str, Any]],
    total_shares: float | None,
) -> float | None:
    """从申报分红事件算申报分红总额(元):Σ(cash_per_10_shares / 10) × total_shares。

    与 ``_compute_payout_from_events`` 同口径但**不**做百分比/舍入,返回原始绝对金额。
    返回 None 时调用方应退回到现金流字段。无事件或 total_shares 无效时返回 None。
    """
    if not events or not total_shares or total_shares <= 0:
        return None
    total: float = 0.0
    has_any = False
    for ev in events:
        ev_type = ev.get("event_type")
        cps = ev.get("cash_per_10_shares")
        if ev_type not in ("cash_dividend", "combination"):
            continue
        if cps is None or cps <= 0:
            continue
        total += float(cps) / 10.0 * float(total_shares)
        has_any = True
    return total if has_any else None


def _fmt_split_qty(qty: float) -> str:
    """10送/转数量显示:整数无小数,小数保留 1 位。例:3.0→"3"、2.5→"2.5"。"""
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.1f}"


def _build_dividend_extra_columns(
    multi_year_summary: dict[str, dict[str, Any]],
    events_by_year: dict[str, list[dict[str, Any]]] | None,
    total_shares_by_year: dict[str, float] | None,
) -> dict[str, list[Any]]:
    """给趋势表追加 2 列(不影响 3 列 chart series):
    - 分红总金额(亿元):events 路径优先,退到 cash_for_dividend_and_interest 字段
    - 拆股情况:"10送X转Y" / "10送X" / "10转Y" / "无"

    返回的 list 顺序与 ``sorted(multi_year_summary.keys())`` 对齐,直接
    喂给 ``pd.DataFrame[列名] = ...`` 即可扩展表格。
    """
    years = sorted(multi_year_summary.keys())
    amounts: list[float] = []
    splits: list[str] = []
    for y in years:
        events = (events_by_year or {}).get(str(y), [])
        shares = (total_shares_by_year or {}).get(str(y))

        # 分红总金额:events 算的绝对金额(元)→ 亿元
        total_yuan = _sum_dividend_from_events(events, shares)
        if total_yuan is None or total_yuan <= 0:
            cash_div = (multi_year_summary.get(y) or {}).get(
                "cash_for_dividend_and_interest"
            )
            total_yuan = float(cash_div) if cash_div else 0.0
        amounts.append(round(total_yuan / 1e8, 2))  # 元 → 亿元

        # 拆股情况:按年累计送股 + 转增
        bonus = sum(float(ev.get("bonus_shares_per_10") or 0) for ev in events)
        cap = sum(
            float(ev.get("capitalized_shares_per_10") or 0) for ev in events
        )
        if bonus > 0 and cap > 0:
            splits.append(
                f"10送{_fmt_split_qty(bonus)}转{_fmt_split_qty(cap)}"
            )
        elif bonus > 0:
            splits.append(f"10送{_fmt_split_qty(bonus)}")
        elif cap > 0:
            splits.append(f"10转{_fmt_split_qty(cap)}")
        else:
            splits.append("无")

    return {
        "分红总金额(亿元)": amounts,
        "拆股情况": splits,
    }


def query_dividend_events(
    stock_code: str, year: int, period: str = "FY",
) -> list[dict[str, Any]]:
    """查 capital_change_events 表,返回某年的现金分红事件列表。

    返回字段:cash_per_10_shares, bonus_shares_per_10, capitalized_shares_per_10,
    event_type, event_date, scheme_description。
    失败(DB 异常/未连接)返回 []。
    """
    try:
        conn = get_db()._duckdb_conn
    except Exception:
        return []
    rows = conn.execute(
        """
        SELECT cash_per_10_shares, bonus_shares_per_10, capitalized_shares_per_10,
               event_type, event_date, scheme_description
        FROM capital_change_events
        WHERE stock_code = ?
          AND report_year = ?
          AND report_period = ?
          AND event_type IN (
              'cash_dividend', 'bonus_share',
              'capitalized_share', 'combination'
          )
          AND (cash_per_10_shares > 0
               OR bonus_shares_per_10 > 0
               OR capitalized_shares_per_10 > 0)
        ORDER BY event_date
        """,
        [stock_code, year, period],
    ).fetchall()
    return [
        {
            "cash_per_10_shares": r[0],
            "bonus_shares_per_10": r[1],
            "capitalized_shares_per_10": r[2],
            "event_type": r[3],
            "event_date": r[4],
            "scheme_description": r[5],
        }
        for r in rows
    ]


def query_dividend_events_by_year(
    stock_code: str, start_year: int, end_year: int, period: str = "FY",
) -> dict[str, list[dict[str, Any]]]:
    """按年聚合 cash_dividend/combination 事件;返回 ``{year_str: [event_dict, ...]}``。

    用于多年趋势图——每点的分红率优先按当年事件表计算,缺失时退到现金流字段。
    包含送股/转增字段(bonus_shares_per_10, capitalized_shares_per_10)以支持
    拆股情况汇总。
    """
    try:
        conn = get_db()._duckdb_conn
    except Exception:
        return {}
    rows = conn.execute(
        """
        SELECT report_year, cash_per_10_shares, bonus_shares_per_10,
               capitalized_shares_per_10, event_type, event_date,
               scheme_description
        FROM capital_change_events
        WHERE stock_code = ?
          AND report_year BETWEEN ? AND ?
          AND report_period = ?
          AND event_type IN (
              'cash_dividend', 'bonus_share',
              'capitalized_share', 'combination'
          )
          AND (cash_per_10_shares > 0
               OR bonus_shares_per_10 > 0
               OR capitalized_shares_per_10 > 0)
        ORDER BY report_year, event_date
        """,
        [stock_code, start_year, end_year, period],
    ).fetchall()
    result: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        d = {
            "cash_per_10_shares": r[1],
            "bonus_shares_per_10": r[2],
            "capitalized_shares_per_10": r[3],
            "event_type": r[4],
            "event_date": r[5],
            "scheme_description": r[6],
        }
        result.setdefault(str(r[0]), []).append(d)
    return result


def fetch_total_shares_by_year(
    stock_code: str, start_year: int, end_year: int, period: str = "FY",
) -> dict[str, float]:
    """按年聚合 share_structure.total_shares;返回 ``{year_str: shares}``。

    注意:同一公司在不同年份的 total_shares 可能因送转/增发而变化——分年取值
    才能让 ``(cash_per_10_shares / 10) × total_shares`` 算申报分红总额时用对股本。
    """
    try:
        conn = get_db()._duckdb_conn
    except Exception:
        return {}
    rows = conn.execute(
        """
        SELECT report_year, total_shares FROM share_structure
        WHERE stock_code = ?
          AND report_year BETWEEN ? AND ?
          AND report_period = ?
          AND total_shares IS NOT NULL
        """,
        [stock_code, start_year, end_year, period],
    ).fetchall()
    return {str(r[0]): float(r[1]) for r in rows if r[1] is not None}


def extract_dividend_info(
    financial_data: Dict[str, Any],
    *,
    dividend_events: list[dict[str, Any]] | None = None,
    total_shares: float | None = None,
) -> Dict[str, Any]:
    """从财务数据 + 申报分红事件中提取分红相关信息。

    数据来源优先级：
    1. **分红率分子**优先用 ``capital_change_events``(申报分红总额,无利息污染):
       Σ(cash_per_10_shares / 10) × total_shares
    2. 缺失/不传时回退到现金流量表 cash_for_dividend_and_interest(含利息,仅作估算)
    3. 自由现金流 = 经营活动现金流 - 购建固定资产现金支出
    4. 净利润字段多别名(net_profit / net_profit_attributable_to_parent / total_profit)

    Args:
        financial_data: 财务数据字典(含 balance_sheet / income_statement / cash_flow)
        dividend_events: 现金分红事件列表(可空),每条至少含
            ``event_type``('cash_dividend' / 'combination')和 ``cash_per_10_shares``。
        total_shares: 报告期总股本(股),用于把 cash_per_10_shares 换算到绝对金额。

    Returns:
        分红信息字典,额外带 ``payout_source`` 字段('capital_change_events' /
        'cash_flow' / 'none')用于诊断当前走的是哪条路径。
    """
    income_statement = financial_data.get("income_statement", {})
    cash_flow = financial_data.get("cash_flow", {})

    net_profit = _pick_net_profit(income_statement)
    operating_cash_flow = (
        cash_flow.get("net_cash_from_operations", 0)
        or cash_flow.get("operating_cash_flow", 0)
        or 0
    )

    # 自由现金流 = 经营现金流 - 购建固定资产等资本支出
    capex = cash_flow.get("cash_for_fixed_assets", 0) or 0
    free_cash_flow = operating_cash_flow - capex

    # 分子:优先用申报分红事件(events 纯净,无利息污染)
    events_total = _sum_dividend_from_events(
        dividend_events or [], total_shares,
    )
    if events_total is not None and events_total > 0:
        # events 路径:从原始 cash_per_10_shares 直接算申报分红总额(不经过 payout_ratio 舍入)
        cash_dividend_paid = events_total
        payout_source = "capital_change_events"
        payout_ratio = (
            (cash_dividend_paid / net_profit * 100) if net_profit > 0 else 0.0
        )
    else:
        # 退路:现金流量表(含利息,仅作估算)
        cash_dividend_paid = (
            cash_flow.get("cash_for_dividend_and_interest", 0) or 0
        )
        payout_source = "cash_flow"
        payout_ratio = (
            (cash_dividend_paid / net_profit * 100) if net_profit > 0 else 0.0
        )

    fcf_coverage = (
        (free_cash_flow / cash_dividend_paid)
        if cash_dividend_paid > 0 else 0.0
    )

    return {
        "net_profit": net_profit,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
        "cash_dividend_paid": cash_dividend_paid,
        "payout_ratio": round(payout_ratio, 2),       # 分红率(%)
        "fcf_coverage": round(fcf_coverage, 2),       # 自由现金流对分红覆盖倍数
        "payout_source": payout_source,               # 'capital_change_events' / 'cash_flow'
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
    *,
    dividend_events_by_year: dict[str, list[dict[str, Any]]] | None = None,
    total_shares_by_year: dict[str, float] | None = None,
) -> tuple[Path, pd.DataFrame]:
    """把 dividend skill 的 multi_year_summary 渲染成 3 子图趋势 + 表格。

    子图 1: 营业收入(亿元)
    子图 2: 归母净利润(亿元)
    子图 3: 分红率(%) — 优先按当年 capital_change_events 算的申报分红
            总额 / 归母净利润;事件缺失时退回到
            cash_for_dividend_and_interest / net_profit × 100(估算,含利息)。
            缺失年份该指标为 None,subplot 自然跳过。

    Args:
        multi_year_summary: 与 skill.py 里的 multi_year_summary 同形
            {year_str: {"operating_revenue": float|None, "net_profit": float|None,
                         "cash_for_dividend_and_interest": float|None, ...}}
        output_path: PNG 写入路径。
        title: 整图标题。None 时使用通用默认"分红股关键指标趋势"。
        metric_explanations: {metric 显示名: 解释文本(计算公式/定义)},
            渲染到图片下方居中。常见用法:把分红率的计算公式传进来。
            例:{"分红率(%)": "申报分红 / 归母净利润 × 100 (来自 capital_change_events)"}
            None 或空 dict 不渲染。
        dividend_events_by_year: {year_str: [event_dict, ...]},可选。
            event_dict 字段:cash_per_10_shares (float), event_type (str)。
        total_shares_by_year: {year_str: float},可选。events 路径需要。

    Returns:
        (chart_path, table) 二元组:
        - chart_path: 写入的 PNG 路径(Path)。
        - table: 趋势 DataFrame,index=年份字符串(字典序),包含 5 列:
                 营业收入(亿元) / 归母净利润(亿元) / 分红率(%) /
                 分红总金额(亿元) / 拆股情况。
                 前 3 列用于绘图(line plot 不吃字符串),后 2 列只展示在表里。
    """
    from src.tools.visualization import render_trend_chart_and_table

    series: dict[str, dict[str, float]] = {}
    for year, m in multi_year_summary.items():
        net_profit = m.get("net_profit")
        cash_div = m.get("cash_for_dividend_and_interest")
        payout_ratio: float | None = None

        # 优先 events 路径(无利息污染)
        events_for_year = (dividend_events_by_year or {}).get(str(year), [])
        shares_for_year = (total_shares_by_year or {}).get(str(year))
        events_payout = _compute_payout_from_events(
            events_for_year, shares_for_year, net_profit,
        )
        if events_payout is not None:
            payout_ratio = events_payout
        elif cash_div is not None and net_profit is not None and net_profit > 0:
            # 退路:现金流字段(含利息,估算)
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
    chart_path, table = render_trend_chart_and_table(
        series,
        output_path=output_path,
        title=title if title is not None else "分红股关键指标趋势",
        x_label="年份",
        metric_explanations=metric_explanations,
    )

    # 追加 2 列到 table:分红总金额 + 拆股情况(只展示,不进 chart)
    extras = _build_dividend_extra_columns(
        multi_year_summary, dividend_events_by_year, total_shares_by_year,
    )
    for col_name, col_data in extras.items():
        table[col_name] = col_data

    # ── 列顺序重排:派生指标(分红率)挪到最后一列 ────────────────────────
    # 默认顺序:[营业收入, 归母净利润, 分红率, 分红总金额, 拆股情况]
    # 期望顺序:[营业收入, 归母净利润, 分红总金额, 拆股情况, 分红率]
    # 理由:阅读流 = 基本面 → 派息结构 → 派生比率
    _payout_col = "分红率(%)"
    if _payout_col in table.columns:
        ordered_cols = [c for c in table.columns if c != _payout_col] + [_payout_col]
        table = table[ordered_cols]

    return chart_path, table


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
    payout_ratio_override: Optional[float] = None,
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
        payout_ratio_override: 用 skill 算的(events 表口径)分红率覆盖 LLM 输出。
            缺省时用 ``result.get("payout_ratio")``;典型用法:skill.py 把自己算的
            payout_ratio 传进来,避免 LLM 估算出偏差。

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
        # 口径注释:分红率 = 现金分红 / 归母净利润,送转股未折算进比率,
        # 防止投资者误读(纯派现股票 100% 准确,送转股票偏低)。
        trend_lines.append(
            "> **口径说明**:分红率(%) = 现金分红总额 / 归母净利润 × 100。"
            "送转股(10送X / 10转X)未折算进比率,"
            "详见「拆股情况」列。"
        )
        trend_lines.append("")
    if not chart_path and (table is None or table.empty):
        trend_lines.append("*（趋势图/表数据缺失）*")
        trend_lines.append("")
    trend_lines += ["---", ""]

    # 3. 二、关键指标
    # 分红率优先用 skill 算的(events 口径,无利息污染),回落到 LLM 输出
    payout_value = (
        payout_ratio_override
        if payout_ratio_override is not None
        else result.get("payout_ratio")
    )
    key_rows = [
        ("股息率(%)", result.get("dividend_yield")),
        ("分红率(%)", payout_value),
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
