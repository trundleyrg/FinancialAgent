"""股本结构 fetcher。

数据源优先级：
1. akshare stock_zh_a_spot_em()  实时行情（含 总股本/流通股本）
2. akshare stock_individual_basic_info_xq()  雪球基础信息
3. 本地推导：用 capital_change_events.cash_per_10_shares 与
   consolidated_cash_flow_statement.cash_for_dividend_and_interest
   反推 total_shares = cash_dividend_paid / (cash_per_10_shares / 10)

调用：
- fetch_share_structure(stock_code, year, period) -> Dict
- fetch_and_persist(stock_code, year, period) -> bool  直接写 DB
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.db.db_connector import get_db
from src.db.models import ShareStructure
from src.tools.chapter_extractor import PDFChapterExtractor
from src.utils.logger import manager

logger = manager.get_logger("Agent.ShareStructureFetcher", "market_data.log")


def _to_float(v: Any) -> Optional[float]:
    """兼容 pd.NA / None / 字符串数字。"""
    if v is None:
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _from_akshare_spot(stock_code: str) -> Optional[Dict[str, Any]]:
    """akshare stock_zh_a_spot_em → 取 total_shares / unrestricted_shares 等。

    列名约定（2024+）：'代码','名称','最新价','今开','昨收','最高','最低',
    '成交量','成交额','振幅','涨跌幅','涨跌额','换手率','量比','市盈率',
    '市净率','总市值','流通市值','总股本','流通股本','涨速','5分钟涨跌',
    '60日涨跌幅','年初至今涨跌幅'
    """
    try:
        import akshare as ak
    except ImportError:
        return None
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as exc:  # network / rate limit / etc
        logger.warning("akshare stock_zh_a_spot_em 失败 %s: %s", stock_code, exc)
        return None
    if df is None or df.empty:
        return None
    row = df[df["代码"] == stock_code]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "company_name": str(r.get("名称", "") or ""),
        "total_shares": _to_float(r.get("总股本")),
        "unrestricted_shares": _to_float(r.get("流通股本")),
    }


def _from_local_derivation(stock_code: str, year: int, period: str) -> Optional[Dict[str, Any]]:
    """🚨 DISABLED — 本地推导 total_shares 不可靠,已禁用。

    历史设计:
        用 cash_for_dividend_and_interest ÷ (SUM(cash_per_10_shares)/10) 反推总股本。

    为什么禁用:
        中文财报「分配股利、利润**或偿付利息**支付的现金」是合并口径,
        **含子公司分红 + 利息支付**,系统性偏高 ~20%(2024 实测 21%)。

        即便:
            - SUM 累加所有笔(不再漏中期+年终)
            - sanity check 与已知股本偏离 >50% 时丢弃
        仍然会:
            - 21% 偏差 < 50% 容差 → 通过检查
            - 推导值 7.78 亿 vs 真实 6.44 亿 → 覆盖正确数据
            - dividend skill 用错的 total_shares 算 payout_ratio → 系统性偏高

    任何容差阈值都不能同时满足:
        - 容差太小 → 冷启动正常股票也拒绝
        - 容差太大 → 利息污染通过覆盖真实值

    替代方案:
        1. **akshare stock_zh_a_spot_em()** — 实时行情接口,见 `_from_akshare_spot`
        2. **PDF「股份变动及股东情况」表** — 用 PDFChapterExtractor 读"股份总数(本次变动后)"
        3. **手工入库** — 调 share_structure_fetcher 后用 SQL 覆盖(或直接 INSERT)

    历史事故:
        - 2026-09-21 commit a9206b2: 此函数被用于 000423 → 写入 14.79 亿股(LIMIT 1 bug)
        - 后续又被利息污染推算出 7.78 亿股(覆盖我手搞的 6.44 亿)
        - 导致 dividend skill 2024 分红率误报 229.87%(真实 99.84%),波及全公司多年分析

    Returns:
        永远 None(函数保留仅为审计/追溯用途,签名稳定以便外部 monkeypatch)
    """
    logger.debug(
        "_from_local_derivation 已被禁用(系统偏差), stock=%s year=%s period=%s",
        stock_code, year, period,
    )
    return None


# sanity check 偏离容差 — 已无业务使用,保留为审计痕迹
_SANITY_DERIVATION_TOLERANCE = 0.50


def _shares_within_tolerance(
    conn, stock_code: str, derived_shares: float, tolerance: float = _SANITY_DERIVATION_TOLERANCE,
) -> bool:
    """🚨 UNUSED — 原 sanity check 工具函数,保留仅为审计/追溯。

    由于 _from_local_derivation 已禁用,本函数不再被任何业务路径调用。
    保留以备未来引入新的 derivation 方案时复用。
    """
    try:
        row = conn.execute(
            """
            SELECT total_shares FROM share_structure
            WHERE stock_code = ? AND total_shares IS NOT NULL AND total_shares > 0
            ORDER BY report_year DESC LIMIT 1
            """,
            [stock_code],
        ).fetchone()
    except Exception as exc:
        logger.warning("sanity check 查询 share_structure 失败: %s", exc)
        return True
    if not row or not row[0]:
        return True
    known = float(row[0])
    if known <= 0:
        return True
    deviation = abs(derived_shares - known) / known
    return deviation <= tolerance


# ──────────────────────────────────────────────────────────────────────────────
# PDF 路径:从年报「股份变动情况」表直接读取 total_shares
# 权威源,长期推荐,绕开 akshare 网络不稳 + cash flow 字段语义错位
# ──────────────────────────────────────────────────────────────────────────────

import re  # noqa: E402
from pathlib import Path  # noqa: E402


def _find_pdf_path(stock_code: str, year: int, period: str = "FY") -> Path | None:
    """在 data/{stock_code}/ 下找匹配年份的年报 PDF。

    命名约定:`<company>_<stock_code>_<year>.pdf` 或 `<stock_code>_<year>.pdf`。
    大部分项目用前者(从 CNInfo / 巨潮下载),也兼容简化命名。

    Args:
        stock_code: 6 位股票代码
        year: 报告年份
        period: "FY" | "Q1" | "H1" | "Q3"(目前只识别 FY)

    Returns:
        Path | None — 找到返回 Path,找不到返回 None
    """
    pdf_dir = Path("data") / stock_code
    if not pdf_dir.is_dir():
        return None
    if period != "FY":
        return None

    # 优先匹配含公司名的命名约定:xxx_<stock_code>_<year>.pdf
    matches = sorted(pdf_dir.glob(f"*_{stock_code}_{year}.pdf"))
    if matches:
        return matches[0]

    # 退化:简化命名 <stock_code>_<year>.pdf
    fallback = pdf_dir / f"{stock_code}_{year}.pdf"
    if fallback.exists():
        return fallback

    return None


def _parse_shares_value(raw: Any) -> float | None:
    """把 PDF 表格里的字符串解析成股数。

    Examples:
        "654,021,537" → 654021537.0
        "654021537"   → 654021537.0
        None / ""     → None

    单位识别留给调用方:本函数只做数字清洗。
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace(",", "").replace(" ", "")
    if s in {"-", "—", "/"}:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _from_pdf_share_structure(
    stock_code: str, year: int, period: str, pdf_path: str | Path,
) -> Optional[Dict[str, Any]]:
    """从年报 PDF「第七节 股份变动情况」表的"三、股份总数(本次变动后)"行读取总股本。

    **最权威**的数据源——直接从巨潮资讯网下载的原始 PDF 解析,
    绕开 akshare 网络不稳和 cash flow 字段语义错位问题。

    Returns:
        {
            "company_name": None,             # PDF 表不直接含公司名
            "total_shares": float,            # 股
            "unrestricted_shares": None,      # 未单独拆列,留 None(可后续扩展)
            "source_label": "PDF年报第七节股份变动情况表",
        }
        解析失败 → None
    """
    extractor = None
    try:
        extractor = PDFChapterExtractor(str(pdf_path))
        main_tables = extractor.extract_main_tables()
        tbl = main_tables.get("股份变动情况")
        if tbl is None:
            logger.warning(
                "%s %s PDF 中未找到「股份变动情况」表: %s",
                stock_code, year, pdf_path,
            )
            return None

        rows = tbl.table_data
        if not rows:
            return None

        # 找"三、股份总数"行(可能变体:三、股份总数 / 股份总数 / 三、股份合计)
        total_row = None
        for row in rows:
            row_text = " ".join(str(c) for c in row if c is not None)
            if re.search(r"[二三]、?\s*股份\s*(总数|合计)", row_text):
                total_row = row
                break

        if not total_row:
            logger.warning(
                "%s %s 股份变动表中找不到「股份总数」行: %s",
                stock_code, year, pdf_path,
            )
            return None

        # 取本行所有数字列的值,挑最大且 >1000 的(股份变动表里
        # 「本次变动后-数量」通常是最大数字,且单位为「股」不会 < 1000)
        numeric_values: list[float] = []
        for cell in total_row:
            val = _parse_shares_value(cell)
            if val is not None and val > 1000:
                numeric_values.append(val)

        if not numeric_values:
            logger.warning(
                "%s %s 股份总数行解析不出数值: row=%s",
                stock_code, year, total_row,
            )
            return None

        # 多个数字时:取**最后一个**(表格列顺序:
        # [本次变动前-数量, 比例, ...小计..., 本次变动后-数量, 比例])
        # 简化假设:总数行只有 1-2 个大数字(数量),最后一个 = 本次变动后
        total_shares = numeric_values[-1]

        return {
            "company_name": None,
            "total_shares": float(total_shares),
            "unrestricted_shares": None,
            "source_label": "PDF年报第七节股份变动情况表",
        }

    except Exception as exc:
        logger.warning(
            "PDF 解析 %s %s 异常: %s: %s",
            stock_code, year, type(exc).__name__, exc,
        )
        return None
    finally:
        if extractor is not None:
            try:
                extractor.close()
            except Exception:
                pass


def fetch_share_structure(
    stock_code: str, year: int, period: str = "FY",
) -> Dict[str, Any]:
    """获取股本结构，akshare 优先，本地推导兜底。

    Returns:
        {
          "stock_code": "000423",
          "report_year": 2024,
          "report_period": "FY",
          "total_shares": float | None,           # 股
          "unrestricted_shares": float | None,    # 股
          "company_name": str | None,
          "source": "akshare_spot" | "pdf_year_report" | "none",
          "error": str | None,
        }
    """
    stock_code = stock_code.strip().zfill(6)
    result: Dict[str, Any] = {
        "stock_code": stock_code,
        "report_year": year,
        "report_period": period,
        "total_shares": None,
        "unrestricted_shares": None,
        "company_name": None,
        "source": "none",
        "error": None,
    }

    # 1. akshare 实时
    live = _from_akshare_spot(stock_code)
    if live and live.get("total_shares"):
        result.update({k: v for k, v in live.items() if v is not None})
        result["source"] = "akshare_spot"
        return result

    # 2. PDF 年报第七节「股份变动情况」表(权威源,长期推荐)
    pdf_path = _find_pdf_path(stock_code, year, period)
    if pdf_path:
        pdf_data = _from_pdf_share_structure(stock_code, year, period, pdf_path)
        if pdf_data and pdf_data.get("total_shares"):
            result["total_shares"] = pdf_data["total_shares"]
            result["unrestricted_shares"] = pdf_data.get("unrestricted_shares")
            if pdf_data.get("company_name"):
                result["company_name"] = pdf_data["company_name"]
            result["source"] = "pdf_year_report"
            return result

    result["error"] = "all sources failed"
    return result


def fetch_and_persist(
    stock_code: str, year: int, period: str = "FY",
) -> bool:
    """fetch_share_structure → 写入 share_structure 表（先删旧行再插）。"""
    data = fetch_share_structure(stock_code, year, period)
    if not data.get("total_shares"):
        logger.warning(
            "未获取到 %s %s %s 股本结构: source=%s error=%s",
            stock_code, year, period, data.get("source"), data.get("error"),
        )
        return False

    db = get_db()
    company_name = data.get("company_name") or stock_code
    # 先删旧的 (stock_code, year, period)
    db._duckdb_conn.execute(
        """
        DELETE FROM share_structure
        WHERE stock_code = ? AND report_year = ? AND report_period = ?
        """,
        [stock_code, year, period],
    )
    row = {
        "company_name": company_name,
        "stock_code": stock_code,
        "report_year": year,
        "report_period": period,
        "total_shares": data["total_shares"],
        "unrestricted_shares": data.get("unrestricted_shares"),
    }
    db._duckdb_conn.execute(
        """
        INSERT INTO share_structure
            (company_name, stock_code, report_year, report_period,
             total_shares, unrestricted_shares)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            row["company_name"], row["stock_code"], row["report_year"],
            row["report_period"], row["total_shares"], row["unrestricted_shares"],
        ],
    )
    logger.info(
        "写入 share_structure: %s %s %s total_shares=%s source=%s",
        stock_code, year, period, data["total_shares"], data["source"],
    )
    return True
