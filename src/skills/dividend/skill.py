"""红利股分析 skill。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.graph.state import FinancialState
from src.skills._loader import read_skill_description
from src.skills.dividend.tools import (
    build_dividend_markdown,
    compute_dividend_stability_years,
    compute_debt_breakdown,
    compute_target_returns_table,
    extract_dividend_info,
    fetch_total_shares_by_year,
    filter_financial_data,
    get_dividend_stats_with_fallback,
    query_dividend_events,
    query_dividend_events_by_year,
    render_dividend_trend_chart,
    render_debt_structure_chart,
    _is_financial_data_empty,
)


def _fetch_total_shares(
    stock_code: str, year: int, period: str | None,
) -> float | None:
    """从 share_structure 表读 total_shares（股）。"""
    if not stock_code:
        return None
    try:
        row = get_db()._duckdb_conn.execute(
            """
            SELECT total_shares FROM share_structure
            WHERE stock_code = ? AND report_year = ? AND report_period = ?
            """,
            [stock_code, year, period or "FY"],
        ).fetchone()
    except Exception:
        return None
    if row and row[0] is not None:
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return None
    return None
from src.tools.calculation_tools import (
    calculate_liquidity,
    calculate_profitability,
    calculate_solvency,
)
from src.tools.db_tools import get_all_financial_data, get_multi_year_financial_data
from src.tools.market_data_tool import get_stock_market_data
from src.tools.skill_result_writer import save_skill_result
from src.tools.valuation_fetcher import load_valuation_percentile
from src.db.db_connector import get_db

logger = logging.getLogger("Skills.Dividend")

SKILL_DIR = Path(__file__).parent

_INSTRUCTION = SKILL_DIR.joinpath("SKILL.md").read_text(encoding="utf-8")
_USER_PROMPT = (
    "公司名称：{company_name}\n"
    "股票代码：{stock_code}\n"
    "报告期：{report_year}年 {report_period}\n"
    "\n请基于以上信息与下方财务/分析指标，给出详细的红利股分析报告。"
)

# 多年度财务趋势窗口（向 LLM 提供的近 N 年关键指标时间序列）。
# - 默认 5 年（与「连续分红年限」口径一致）。
# - 可被环境变量 DIVIDEND_TREND_YEARS 覆盖，便于在 CI / smoke test 中换窗口。
# - run() 形参 trend_years 优先级最高，传 None 时回落到此值。
import os
DEFAULT_TREND_YEARS = int(os.environ.get("DIVIDEND_TREND_YEARS", "5"))

DESCRIPTION = read_skill_description(SKILL_DIR / "SKILL.md")


def _maybe_compute_target_returns(
    stock_code: Optional[str],
    report_year: int,
    report_period: Optional[str],
    cur_total_shares: Optional[float],
    current_price: Optional[float],
) -> Optional[Dict[str, Any]]:
    """计算「目标股息率反推市值」表。关键字段齐备时返回完整 dict,否则 None。

    返回结构(= ``compute_target_returns_table`` 的输出,缺字段时 None):
        {
            "rows": [ {dividend_yield_pct, implied_price, implied_market_cap_yi}, ... ],
            "current_price": float | None,
            "current_price_source": str | None,   # 取自哪张表
            "current_price_date": str | None,     # 取价日期(ISO)
            ...
        }

    仅在 per_share_dividend + total_shares 都齐时才返回 rows,
    避免半残数据误导读者(``build_dividend_markdown`` 收到 None 就不渲染该 section)。
    """
    if not stock_code:
        return None
    try:
        res = compute_target_returns_table(
            stock_code=stock_code,
            report_year=report_year,
            period=report_period or "FY",
            target_yields=[3.0, 5.0],
        )
    except Exception as exc:
        logger.warning("compute_target_returns_table 异常 %s: %s", stock_code, exc)
        return None
    # 必要字段任一缺失 → 不渲染(避免错误数据)
    if "total_shares" in res["missing_fields"]:
        return None
    if "per_share_dividend" in res["missing_fields"]:
        return None
    if not res["rows"]:
        return None
    return res


def _target_returns_kwargs(
    res: Optional[Dict[str, Any]],
    fallback_current_price: Optional[float],
) -> Dict[str, Any]:
    """把 ``compute_target_returns_table`` 的输出摊成 ``build_dividend_markdown`` 的 kwargs。

    ``current_price`` 优先用 skill 自己从 ``market_data_tool`` 拿到的价
    (那条链路优先 stock_market_snapshot 估值快照,与 dividend_yield 同源);
    拿不到时退化到 ``compute_target_returns_table`` 内部查的价。
    来源表名与取价日期始终来自 ``compute_target_returns_table`` 的查询结果。

    res 为 None(关键字段缺失)时返回全 None,markdown 就不渲染该 section。
    """
    if not res or not res.get("rows"):
        return {
            "target_returns_table": None,
            "target_returns_current_price": None,
            "target_returns_current_price_source": None,
            "target_returns_current_price_date": None,
        }
    price = fallback_current_price
    if price is None:
        price = res.get("current_price")
    return {
        "target_returns_table": res["rows"],
        "target_returns_current_price": price,
        "target_returns_current_price_source": res.get("current_price_source"),
        "target_returns_current_price_date": res.get("current_price_date"),
    }


def run(
    state: FinancialState,
    llm,
    trend_years: int | None = None,
) -> Dict[str, Any]:
    """红利股分析 skill；返回 state delta。

    字段语义与原 `create_dividend_analysis(llm)` 节点保持一致：
    - 成功：`{"dividend_analysis": <dict>}`
    - 失败：`{"dividend_analysis": None, "error_msg": "..."}`

    Args:
        state: FinancialState（必传）。
        llm: 已构造好的 LangChain LLM 实例。
        trend_years: 多年财务时间序列窗口长度。None / 缺省 → DEFAULT_TREND_YEARS (默认 5)。
    """
    company_name = state.get("company_name")
    stock_code = state.get("stock_code")
    report_year = state.get("report_year")
    report_period = state.get("report_period")

    if not company_name or not report_year:
        logger.error("缺少公司信息，无法进行红利股分析")
        return {"dividend_analysis": None, "error_msg": "缺少公司信息"}

    years_window = trend_years if trend_years is not None else DEFAULT_TREND_YEARS
    if years_window < 1:
        years_window = 1

    logger.info(
        "开始红利股分析: %s (%s) %s %s trend_years=%d",
        company_name, stock_code, report_year, report_period, years_window,
    )

    try:
        # 1. 获取财务数据
        financial_data = get_all_financial_data(
            company_name=company_name,
            year=report_year,
            period=report_period,
            # stock_code 是稳定主键;只传 company_name 时,公司改名 /
            # 简称不一致 / 上游误传代码都会查不到数据 → 误报「财务数据为空」
            stock_code=stock_code,
        )

        # 1a. fail-fast:3 张表全空(PDF 解析失败 / 数据未入库)时直接
        # return,避免后续算出 0% payout_ratio 等噪音指标写进 DB / markdown。
        if _is_financial_data_empty(financial_data):
            logger.error(
                "财务数据为空 (%s %s %s),无法进行红利股分析",
                company_name, report_year, report_period,
            )
            return {
                "dividend_analysis": None,
                "error_msg": (
                    f"财务数据为空({company_name} {report_year} "
                    f"{report_period or '未知'}),无法进行红利股分析"
                ),
            }

        balance_sheet = financial_data.get("balance_sheet", {})
        income_statement = financial_data.get("income_statement", {})
        cash_flow = financial_data.get("cash_flow", {})

        # 1b. 近 N 年财务时间序列（用于看趋势）；缺失年份键缺失，不抛错。
        # prompt 里只塞关键字段（营收/净利/经营现金流/分红现金支出/总资产），
        # 避免大 prompt 触发 MiniMax M3.1-Flash-Preview 静默回空。
        multi_year_raw: Dict[str, Any] = {}
        multi_year_summary: Dict[str, Dict[str, Any]] = {}
        try:
            multi_year_raw = get_multi_year_financial_data(
                company_name=company_name,
                start_year=report_year - (years_window - 1),
                end_year=report_year,
                period=report_period or "FY",
                # 同上:用稳定主键寻址,不用可变的 company_name
                stock_code=stock_code,
            )
            for y, stmts in multi_year_raw.items():
                inc = stmts.get("consolidated_income_statement") or {}
                cf = stmts.get("consolidated_cash_flow_statement") or {}
                bs = stmts.get("consolidated_balance_sheet") or {}
                multi_year_summary[y] = {
                    "operating_revenue": inc.get("operating_revenue"),
                    "net_profit": inc.get("net_profit")
                        or inc.get("net_profit_attributable_to_parent")
                        or inc.get("total_profit"),
                    "net_cash_from_operations":
                        cf.get("net_cash_from_operations")
                        or cf.get("operating_cash_flow"),
                    "cash_for_dividend_and_interest":
                        cf.get("cash_for_dividend_and_interest"),
                    "total_assets": bs.get("total_assets"),
                }
        except Exception as exc:
            logger.warning("多年财务数据拉取失败 (%s): %s", company_name, exc)

        # 1b. 多年负债结构(有息 vs 无息) — 趋势表 + 二、关键指标用
        debt_by_year: Dict[str, Dict[str, Any]] = {}
        latest_interest_ratio: float | None = None
        latest_interest_debt: float | None = None
        try:
            for y, stmts in multi_year_raw.items():
                bs = stmts.get("consolidated_balance_sheet") or {}
                debt_by_year[y] = bs  # compute_debt_breakdown 直接吃这字段
            # 最新年份的指标(供 skill 写入 dividend_info)
            if multi_year_summary:
                latest_year = max(multi_year_summary.keys())
                i, ni, _t, i_pct, _ni_pct = compute_debt_breakdown(
                    debt_by_year.get(latest_year) or {}
                )
                latest_interest_ratio = i_pct
                latest_interest_debt = round(i / 1e8, 2)  # 亿元
                logger.info(
                    "最新负债结构 (%s): 有息=%.2f 亿, 占比=%.2f%%",
                    latest_year, latest_interest_debt, latest_interest_ratio,
                )
        except Exception as exc:
            logger.warning("多年负债结构计算失败: %s", exc)

        # 2. 计算分析指标
        profitability = calculate_profitability(income_statement, balance_sheet)
        liquidity = calculate_liquidity(balance_sheet)
        solvency = calculate_solvency(balance_sheet, income_statement)

        # 3. 提取分红相关数据
        # 优先用 capital_change_events(申报分红总额,无利息污染),
        # events 缺失时退回到 extract_dividend_info 内部的现金流字段。
        cur_dividend_events: list[dict[str, Any]] = []
        cur_total_shares: float | None = None
        if stock_code and report_year:
            cur_dividend_events = query_dividend_events(
                stock_code, report_year, report_period or "FY",
            )
            cur_total_shares = _fetch_total_shares(
                stock_code, report_year, report_period,
            )

        # 4. 获取市场数据（股价、PE、PB、股息率）— 先于 extract_dividend_info
        # 因为股息率 = per_share / current_price × 100,需要股价才能算。
        market_data: Dict[str, Any] = {}
        current_price: float | None = None
        pb_ratio: float | None = None
        if stock_code:
            market_data = get_stock_market_data(stock_code)
            dividend_stats = get_dividend_stats_with_fallback(stock_code, years=5)

            # 扁平化：从 pe_pb_history 取最近一日的 close/pb，
            # basic_info 不直接含 PE/PB/市值，置为 None 让 LLM 自行处理。
            pe_pb_history = market_data.get("pe_pb_history") or []
            latest = next(
                (r for r in reversed(pe_pb_history) if isinstance(r, dict) and not r.get("error")),
                None,
            )
            current_price = (latest or {}).get("close")
            pb_ratio = (latest or {}).get("pb")

        dividend_info = extract_dividend_info(
            financial_data,
            dividend_events=cur_dividend_events or None,
            total_shares=cur_total_shares,
            current_price=current_price,  # code 算 dividend_yield 用
        )

        if stock_code:
            dividend_info["market_dividend_stats"] = dividend_stats
            dividend_info["current_price"] = current_price
            dividend_info["pb_ratio"] = pb_ratio
            # PE / 总市值:get_stock_market_data 的 akshare 实时链路
            # (stock_zh_a_hist + 百度 PB)不返回 PE,但 DB 快照链路
            # (stock_market_snapshot,数据源 akshare_value_em)有完整
            # PE(TTM) / 总市值,故从 latest 记录里取。
            dividend_info["pe_ratio"] = (latest or {}).get("pe")
            dividend_info["market_cap"] = (latest or {}).get("market_cap")

            # PE / PB 历史分位:回答「现在贵不贵」。数据源同为
            # stock_market_snapshot(stock_value_em 写入的历史序列),
            # 样本不足 3 天时返回 {} —— 估值段会退回只显示 PE / PB。
            try:
                pct = load_valuation_percentile(stock_code)
            except Exception as exc:
                logger.debug("计算估值分位失败 %s: %s", stock_code, exc)
                pct = {}
            if pct:
                pe_d, pb_d = pct.get("pe_ratio") or {}, pct.get("pb_ratio") or {}
                dividend_info["pe_percentile"] = pe_d.get("percentile")
                dividend_info["pb_percentile"] = pb_d.get("percentile")
                dividend_info["pe_range"] = (pe_d.get("min"), pe_d.get("max"))
                dividend_info["pb_range"] = (pb_d.get("min"), pb_d.get("max"))
                dividend_info["valuation_samples"] = max(
                    pe_d.get("count") or 0, pb_d.get("count") or 0,
                )

            # 总股本:已在第 3 步用 _fetch_total_shares 取过,这里复用 cur_total_shares。
            dividend_info["total_shares"] = cur_total_shares

            # 连续分红年限：从 capital_change_events 反推
            stability_years = compute_dividend_stability_years(
                stock_code, report_year, report_period or "FY",
            )
            dividend_info["dividend_stability_years"] = stability_years

        # 把新指标(有息负债占比 / 有息负债额)塞进 dividend_info 供 LLM 提示
        if latest_interest_ratio is not None:
            dividend_info["interest_debt_ratio"] = latest_interest_ratio
        if latest_interest_debt is not None:
            dividend_info["interest_bearing_debt"] = latest_interest_debt

        analysis_metrics = {
            "profitability": profitability,
            "liquidity": liquidity,
            "solvency": solvency,
            "dividend_info": dividend_info,
            "market_data": market_data,
            "multi_year_summary": multi_year_summary,
        }

        # 5. 拼装 prompt（SKILL.md 指令 + 财务数据 + 分析指标 + 多年度趋势）
        # 财务数据先 filter 到 dividend 真正消费的字段 (~22 个)，
        # 避免送入全量 230 字段（MiniMax M3.1-Flash-Preview 会在大 prompt 下静默回空）。
        filtered_fd = filter_financial_data(financial_data)
        system_msg = (
            _INSTRUCTION
            + "\n\n## 财务数据（" + str(report_year) + "）\n"
            + json.dumps(filtered_fd, ensure_ascii=False, indent=2)
            + "\n\n## 分析指标\n"
            + json.dumps(analysis_metrics, ensure_ascii=False, indent=2)
            + "\n\n## 多年度财务趋势（近 5 年，单位：人民币元）\n"
            + json.dumps(multi_year_summary, ensure_ascii=False, indent=2)
        )
        user_msg = _USER_PROMPT.format(
            company_name=company_name,
            stock_code=stock_code or "未知",
            report_year=report_year,
            report_period=report_period or "未知",
        )

        # 6. 调用 LLM（JSON 输出）
        # 把 system_msg / user_msg 套一层 {var} 模板，避免 ChatPromptTemplate
        # 把 JSON 中的 {x: y} 当成占位符解析（f-string 嵌套字段报错）。
        # 兜底：llm is None 时（NO_LLM=1 / LLM 配置失败 / 网络故障）走 code-only 分支，
        # 只用代码计算的指标装配结果，避免 ``| None`` 链构造抛 ``Runnable`` 错。
        if llm is None:
            result = {
                "investment_rating": "HOLD",
                "reasoning": (
                    "code-only 模式(未调用 LLM)。基于财务数据 + 资本事件 + 负债结构,"
                    "评级默认值。请人工复核或恢复 LLM 后重跑。"
                ),
                "dividend_yield": dividend_info.get("dividend_yield"),
                "payout_ratio": dividend_info.get("payout_ratio"),
                "dividend_stability_years": dividend_info.get("dividend_stability_years"),
                "cash_flow_coverage": dividend_info.get("cash_flow_coverage"),
                "interest_debt_ratio": dividend_info.get("interest_debt_ratio"),
                "interest_bearing_debt": dividend_info.get("interest_bearing_debt"),
                "financial_health_score": dividend_info.get("financial_health_score"),
                "profitability": profitability,
                "solvency": solvency,
                # 估值:PE / PB / 总市值由 code 从 DB 快照算,不依赖 LLM。
                # LLM 链路下这两个字段也会在下方被 result 的 LLM 输出覆盖。
                "valuation": {
                    "pe_ratio": dividend_info.get("pe_ratio"),
                    "pb_ratio": dividend_info.get("pb_ratio"),
                    "market_cap": dividend_info.get("market_cap"),
                    "current_price": dividend_info.get("current_price"),
                    # PE / PB 历史分位 — 回答「现在贵不贵」
                    "pe_percentile": dividend_info.get("pe_percentile"),
                    "pb_percentile": dividend_info.get("pb_percentile"),
                    "pe_range": dividend_info.get("pe_range"),
                    "pb_range": dividend_info.get("pb_range"),
                    "valuation_samples": dividend_info.get("valuation_samples"),
                },
                "risk_factors": dividend_info.get("risk_factors", []),
            }
        else:
            chain = (
                ChatPromptTemplate.from_messages([
                    ("system", "{system}"),
                    ("human", "{user}"),
                ])
                | llm | JsonOutputParser()
            )
            result = None
            # 整链重试：MiniMax M3.1-Flash-Preview 偶发返回空 → JsonOutputParser
            # 抛 OutputParserException（"Invalid json output"）。链级重试可覆盖
            # LLM 层 4 次空响应仍未恢复的情况。
            import time as _time
            for _chain_attempt in range(3):
                try:
                    result = chain.invoke({"system": system_msg, "user": user_msg})
                    break
                except Exception as chain_exc:
                    if "Invalid json output" in str(chain_exc) and _chain_attempt < 2:
                        _time.sleep(1.5)
                        continue
                    raise chain_exc

        # 兜底：MiniMax 在缺估值数据时倾向回 null investment_rating，
        # 此处补默认 HOLD 并在 reasoning 末尾加备注，便于 SQL 检索。
        if not result.get("investment_rating"):
            result["investment_rating"] = "HOLD"
            result.setdefault("reasoning", "")
            result["reasoning"] = (
                result["reasoning"] + " [自动兜底：缺估值/股息率数据，默认 HOLD]"
            ).strip()

        logger.info(
            "红利股分析完成: %s, 评级: %s",
            company_name, result.get("investment_rating", "UNKNOWN"),
        )

        # 持久化趋势图 + 表格(失败仅 log warning,不影响 skill 整体)
        chart_path: str | None = None
        table_path: str | None = None
        table_dict: dict[str, Any] | None = None
        trend_table = None
        if stock_code and report_year:
            try:
                chart_dir = Path("data") / stock_code / "memory" / "charts"
                chart_dir.mkdir(parents=True, exist_ok=True)
                png_path = chart_dir / f"dividend_trend_{report_year}.png"
                csv_path = png_path.with_suffix(".csv")

                # 多年度 events(每年申报分红事件 + 当年总股本),用于按年算
                # 申报分红总额——分子纯净,不含现金流量表里的偿付利息。
                start_year = report_year - (years_window - 1)
                period_str = report_period or "FY"
                events_by_year = query_dividend_events_by_year(
                    stock_code, start_year, report_year, period_str,
                )
                shares_by_year = fetch_total_shares_by_year(
                    stock_code, start_year, report_year, period_str,
                )

                _, trend_table = render_dividend_trend_chart(
                    multi_year_summary, png_path,
                    title=f"{company_name} - 分红股关键指标趋势",
                    metric_explanations={
                        "分红率(%)": (
                            "申报分红 / 归母净利润 × 100 "
                            "(申报分红 = Σ (每10股派息 / 10) × 当年总股本, "
                            "取自 capital_change_events 表的 cash_dividend / "
                            "combination 事件;事件缺失年份退回到 "
                            "cash_for_dividend_and_interest 字段,仅作估算)"
                        ),
                    },
                    dividend_events_by_year=events_by_year or None,
                    total_shares_by_year=shares_by_year or None,
                    debt_by_year=debt_by_year or None,
                )
                trend_table.to_csv(csv_path, index_label="年份")
                chart_path = str(png_path)
                table_path = str(csv_path)
                table_dict = trend_table.to_dict(orient="index")
                logger.info("分红趋势图已生成: %s", chart_path)
            except Exception as exc:
                logger.warning("分红趋势图/表生成失败: %s", exc)

        # 独立的负债结构图(与分红率表格分开展示)
        debt_chart_path: str | None = None
        debt_table_path: str | None = None
        if stock_code and report_year and debt_by_year:
            try:
                memory_dir = Path("data") / stock_code / "memory"
                chart_dir = memory_dir / "charts"
                chart_dir.mkdir(parents=True, exist_ok=True)
                debt_png = chart_dir / f"debt_structure_{report_year}.png"
                debt_csv = chart_dir / f"debt_structure_{report_year}.csv"

                render_debt_structure_chart(
                    debt_by_year, debt_png,
                    title=f"{company_name} - 负债结构(有息 vs 无息)",
                )

                # 构造负债结构表(便于 markdown 嵌入 + 持久化 CSV)
                import pandas as _pd
                rows = []
                for y in sorted(debt_by_year.keys()):
                    i, ni, total, i_pct, _ = compute_debt_breakdown(debt_by_year[y])
                    rows.append({
                        "年份": y,
                        "有息负债(亿元)": round(i / 1e8, 2),
                        "无息负债(亿元)": round(ni / 1e8, 2),
                        "总负债(亿元)": round(total / 1e8, 2) if total > 0 else 0.0,
                        "有息占比(%)": i_pct,
                    })
                debt_df = _pd.DataFrame(rows).set_index("年份")
                debt_df.to_csv(debt_csv, index_label="年份")
                debt_chart_path = str(debt_png)
                debt_table_path = str(debt_csv)
                logger.info("负债结构图已生成: %s", debt_chart_path)
            except Exception as exc:
                logger.warning("负债结构图/表生成失败: %s", exc)

        # 持久化独立红利分析 markdown 报告(图在上、表在下 + LLM 结论)。
        # 失败仅 log warning,不影响 skill 整体;markdown 路径回填到 input_context。
        markdown_path: str | None = None
        if stock_code and report_year and isinstance(result, dict):
            try:
                memory_dir = Path("data") / stock_code / "memory"
                memory_dir.mkdir(parents=True, exist_ok=True)
                md_filename = (
                    f"分析报告_分红_{company_name}_{stock_code}_{report_year}.md"
                )
                md_path = memory_dir / md_filename
                # 图相对路径相对 markdown 文件目录(memory/charts/...)
                chart_rel: str | None = None
                if chart_path:
                    chart_rel = (
                        Path(chart_path).relative_to(memory_dir)
                        .as_posix()
                    )
                # 负债结构图与表的相对路径(memory/charts/...)
                debt_chart_rel: str | None = None
                if debt_chart_path:
                    debt_chart_rel = (
                        Path(debt_chart_path).relative_to(memory_dir)
                        .as_posix()
                    )
                # 读回 CSV 作为 markdown 嵌入表
                debt_df_for_md = None
                if debt_table_path:
                    import pandas as _pd_debt
                    debt_df_for_md = _pd_debt.read_csv(
                        debt_table_path, index_col="年份"
                    )

                md_content = build_dividend_markdown(
                    result,
                    chart_path=chart_rel,
                    table=trend_table,
                    company_name=company_name,
                    stock_code=stock_code,
                    report_year=report_year,
                    report_period=report_period,
                    # 报告期窗口长度,用于在 markdown 备注里告诉读者
                    # 「连续分红年限」等长期口径的统计可能因窗口短而被低估。
                    trend_years=years_window,
                    # skill 自己算的 payout_ratio(events 口径)覆盖 LLM 输出,
                    # 避免 LLM 估算与 trend chart 同年点不一致。
                    payout_ratio_override=dividend_info.get("payout_ratio"),
                    # 同上:dividend_yield(per_share / current_price)由 code 算,
                    # 避免 LLM 在缺股价时臆测(常见,因为 akshare get_stock_pe_pb_history
                    # 网络不稳,current_price 经常 None)。
                    dividend_yield_override=dividend_info.get("dividend_yield"),
                    # 有息负债占比(多年负债结构,code 算) — 趋势表 + 关键指标二用
                    interest_debt_ratio_override=latest_interest_ratio,
                    interest_bearing_debt_override=latest_interest_debt,
                    # 独立的负债结构 section(图 + 表,与分红率表格分开展示)
                    debt_chart_path=debt_chart_rel,
                    debt_table=debt_df_for_md,
                    # 七、目标股息率反推市值(用户提交历史代码变更阶段新增)
                    # 用 compute_target_returns_table 查 DB 实算,缺关键字段时
                    # 整表跳过(在 build_dividend_markdown 内做 None-check)。
                    **_target_returns_kwargs(
                        _maybe_compute_target_returns(
                            stock_code, report_year, report_period,
                            cur_total_shares, current_price,
                        ),
                        # markdown 的「当前价格」基线行优先用 skill 自己从
                        # market_data_tool 拿到的价(带 PE/PB 的快照优先);
                        # 拿不到时退化到 compute_target_returns_table 的价。
                        current_price,
                    ),
                )
                md_path.write_text(md_content, encoding="utf-8")
                markdown_path = str(md_path)
                logger.info("红利分析 markdown 已生成: %s", markdown_path)
            except Exception as exc:
                logger.warning("红利分析 markdown 生成失败: %s", exc)

        # 持久化到 skill_analysis_results（失败仅日志，不影响返回）
        save_skill_result(
            "dividend", state, result,
            input_context={
                "financial_data": financial_data,
                "analysis_metrics": analysis_metrics,
                "multi_year_raw": multi_year_raw,
                "chart_path": chart_path,
                "table_path": table_path,
                "table_dict": table_dict,
                "markdown_path": markdown_path,
            },
        )

        return {"dividend_analysis": result}

    except Exception as e:
        logger.error("红利股分析失败: %s", e)
        return {
            "dividend_analysis": None,
            "error_msg": f"红利股分析失败: {e}",
        }