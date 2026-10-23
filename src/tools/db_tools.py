"""数据库查询工具（薄适配层）。

LLM 工具签名保持向后兼容；内部全部走 StatementRepository / ReportRepository。
"""
import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Agent.DB")


def _looks_like_stock_code(value: str) -> bool:
    """判断字符串是否形似 A 股股票代码(6 位纯数字,允许 sh/sz/bj 前缀)。

    用于识别「上游误把股票代码传进 company_name」的情况 —— 此时若照
    常拿去匹配 company_name 列必然落空,让 skill 误报「财务数据为空」。
    """
    v = value.strip().upper()
    for prefix in ("SH.", "SZ.", "BJ.", "SH", "SZ", "BJ"):
        if v.startswith(prefix):
            v = v[len(prefix):]
            break
    return len(v) == 6 and v.isdigit()

# 短别名 → 规范名（仅这 6 张有别名；新报表按规范名调 repo）
_STATEMENT_ALIASES = {
    "balance_sheet":            "consolidated_balance_sheet",
    "parent_balance_sheet":     "parent_company_balance_sheet",
    "income_statement":         "consolidated_income_statement",
    "parent_income_statement":  "parent_company_income_statement",
    "cash_flow":                "consolidated_cash_flow_statement",
    "parent_cash_flow":         "parent_company_cash_flow_statement",
}

_db = None
_stmt_repo = None
_report_repo = None


def _get_repos():
    """延迟初始化：首次调用时建 connector + repo。"""
    global _db, _stmt_repo, _report_repo
    if _db is None:
        from src.db.db_connector import get_db
        from src.db import StatementRepository, ReportRepository

        _db = get_db()
        _stmt_repo = StatementRepository(_db)
        _report_repo = ReportRepository(_db)
    return _stmt_repo, _report_repo


def _resolve_statement(name: str) -> str:
    """接受规范名或短别名；都返回规范名。"""
    from src.db.repository.statements import list_statements
    if name in list_statements():
        return name
    if name in _STATEMENT_ALIASES:
        return _STATEMENT_ALIASES[name]
    raise ValueError(f"未知 statement: {name}")


def _key(
    stock_code: Optional[str] = None,
    company_name: Optional[str] = None,
    year: Optional[int] = None,
    period: Optional[str] = None,
):
    """轻量本地构造 ReportKey，避免循环导入。"""
    from src.db import ReportKey
    return ReportKey(
        stock_code=stock_code, company_name=company_name,
        year=year, period=period,
    )


def _get_statement(
    company_name: str, year: int, period: str, default_table: str,
) -> Dict[str, Any]:
    """三个 get_*_statement 共用的查询逻辑。"""
    stmts, _ = _get_repos()
    out = stmts.get_statement(
        _key(company_name=company_name, year=year, period=period),
        _resolve_statement(default_table),
    )
    return out if out is not None else {}


def get_balance_sheet(
    company_name: str, year: int, period: str,
    table_name: str = "consolidated_balance_sheet",
) -> Dict[str, Any]:
    """获取资产负债表数据。"""
    try:
        return _get_statement(company_name, year, period, table_name)
    except Exception as e:
        logger.error(f"获取资产负债表失败: {e}")
        return {}


def get_income_statement(
    company_name: str, year: int, period: str,
    table_name: str = "consolidated_income_statement",
) -> Dict[str, Any]:
    """获取利润表数据。"""
    try:
        return _get_statement(company_name, year, period, table_name)
    except Exception as e:
        logger.error(f"获取利润表失败: {e}")
        return {}


def get_cash_flow(
    company_name: str, year: int, period: str,
    table_name: str = "consolidated_cash_flow_statement",
) -> Dict[str, Any]:
    """获取现金流量表数据。"""
    try:
        return _get_statement(company_name, year, period, table_name)
    except Exception as e:
        logger.error(f"获取现金流量表失败: {e}")
        return {}


def _resolve_lookup_name(
    company_name: Optional[str],
    stock_code: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """决定用 stock_code 还是 company_name 寻址。

    ``stock_code`` 是稳定主键；``company_name`` 是可变字段 —— 公司改名、
    简称不一致、或上游误传股票代码,都会让按 company_name 的查询查不到数据,
    最终让 skill 直接 fail-fast(「财务数据为空」)。

    判定规则:
      1. 有 stock_code → 用 stock_code(最稳)
      2. 无 stock_code,但 company_name 看着像 6 位股票代码 → 不把它当公司名
         用(否则 SQL 会拿 "600285" 去匹配 company_name 列,必然落空)
      3. 其余情况 → 用 company_name(向后兼容旧调用方)

    Returns:
        ``(company_name, stock_code)``,已按上述规则归一,直接喂给 ``_key``。
    """
    code = (stock_code or "").strip() or None
    name = (company_name or "").strip() or None

    if code:
        # 传了 stock_code 就以它为准;若 company_name 形似股票代码则丢弃,
        # 避免 ReportKey.to_filter 的"stock_code 优先"逻辑把两者混用。
        if name and _looks_like_stock_code(name):
            name = None
        return name, code

    if name and _looks_like_stock_code(name):
        # company_name 是股票代码但没给 stock_code:无法可靠寻址,
        # 交由调用方保证至少有一个可用键(ReportKey.__post_init__ 会校验)。
        return None, name

    return name, None


def get_all_financial_data(
    company_name: Optional[str], year: int, period: str,
    stock_code: Optional[str] = None,
) -> Dict[str, Any]:
    """获取 3 张合并表（向后兼容的旧形状）。

    Args:
        company_name: 公司名（可变字段,仅在无 stock_code 时用于寻址）。
        year / period: 报告期定位。
        stock_code: 6 位股票代码。**建议总是传** —— 它是稳定主键,
            比 company_name 更可靠(公司改名 / 简称不一致时仍能查到)。
    """
    stmts, _ = _get_repos()
    name, code = _resolve_lookup_name(company_name, stock_code)
    key = _key(company_name=name, stock_code=code, year=year, period=period)
    return {
        "balance_sheet":    stmts.get_statement(key, "consolidated_balance_sheet"),
        "income_statement": stmts.get_statement(key, "consolidated_income_statement"),
        "cash_flow":        stmts.get_statement(key, "consolidated_cash_flow_statement"),
    }


def get_multi_year_financial_data(
    company_name: Optional[str], start_year: int, end_year: int, period: str = "FY",
    stock_code: Optional[str] = None,
) -> Dict[str, Any]:
    """获取多年财务数据（旧形状：{year_str: {3 张合并表}}）。

    缺失年份键缺失 — 不抛错。

    Args:
        company_name: 公司名（可变字段,仅在无 stock_code 时用于寻址）。
        start_year / end_year: 年份窗口。
        period: 报告期间。
        stock_code: 6 位股票代码。**建议总是传** —— 见 ``get_all_financial_data``。
    """
    stmts, _ = _get_repos()
    name, code = _resolve_lookup_name(company_name, stock_code)
    key = _key(company_name=name, stock_code=code, period=period)
    multi = stmts.get_multi_year_all_statements(key, start_year, end_year)
    return {
        str(y): {
            k: multi[y].get(k) for k in (
                "consolidated_balance_sheet",
                "consolidated_income_statement",
                "consolidated_cash_flow_statement",
            )
        }
        for y in sorted(multi)
    }


def check_company_data_availability(
    company_name: str, stock_code: Optional[str] = None, years: int = 10,
) -> Dict[str, Any]:
    """检查公司在数据库中是否存在近 N 年的数据。"""
    _, report_repo = _get_repos()
    try:
        if stock_code:
            key = _key(stock_code=stock_code)
        else:
            key = _key(company_name=company_name)
        return report_repo.check_data_availability(key, years=years)
    except Exception as e:
        logger.error(f"检查数据可用性失败: {e}")
        current_year = datetime.datetime.now().year
        return {
            "has_data": False,
            "available_years": [],
            "missing_years": list(range(current_year - years + 1, current_year + 1)),
            "data_coverage": 0.0,
            "has_latest_year": False,
            "error": str(e),
        }


def get_db_tools() -> List[callable]:
    """获取所有数据库工具（LLM 工具列表）。"""
    return [
        get_balance_sheet,
        get_income_statement,
        get_cash_flow,
        get_all_financial_data,
        get_multi_year_financial_data,
        check_company_data_availability,
    ]