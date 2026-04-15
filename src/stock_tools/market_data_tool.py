"""
市场数据工具

通过 akshare 获取 A 股实时行情、估值指标（PE/PB）和分红历史
"""
import akshare as ak
import traceback

from typing import Dict, Any, List, Optional
import datetime

from src.utils.logger import manager

logger = manager.get_logger("Agent.MarketData", "market_data.log")


def _normalize_stock_code(stock_code: str) -> str:
    """标准化股票代码（去除市场前缀，保留 6 位数字）"""
    code = stock_code.strip().upper()
    for prefix in ("SH", "SZ", "BJ", "SH.", "SZ.", "BJ."):
        if code.startswith(prefix):
            code = code[len(prefix):]
    return code.zfill(6)


def _ensure_market_prefix(stock_code: str) -> str:
    """
    确保股票代码带有市场前缀

    根据代码范围自动判断交易所并补充前缀：
    - SZ (深圳): 000xxx, 001xxx, 002xxx, 003xxx, 200xxx
    - SH (上海): 600xxx, 601xxx, 603xxx, 605xxx, 688xxx
    - BJ (北京): 830xxx, 870xxx, 889xxx

    Args:
        stock_code: 6 位股票代码，如 "000423" 或 "SZ000423"

    Returns:
        带市场前缀的股票代码，如 "SZ000423"
    """
    code = _normalize_stock_code(stock_code)

    # 已在外部做了标准化，此时 code 一定是 6 位纯数字
    if code.startswith(("000", "001", "002", "003", "200")):
        return "SZ" + code
    elif code.startswith(("600", "601", "603", "605", "688")):
        return "SH" + code
    elif code.startswith(("830", "870", "889")):
        return "BJ" + code
    else:
        # 未知代码，默认深交所
        logger.warning(f"未知股票代码 {code}，默认使用深交所")
        return "SZ" + code


def get_stock_basic_info(stock_code: str) -> Dict[str, Any]:
    """
    获取股票基础信息（名称、行业、地区、上市日期等）

    使用 akshare 获取股票基础信息，只返回 xq.md 中标记为"是否返回"=1 的字段。

    Args:
        stock_code: 6 位股票代码，如 "000423" 或 "SZ000423"

    Returns:
        {
            "org_name_cn": str,              # 公司中文全称
            "org_short_name_cn": str,        # 公司中文简称
            "main_operation_business": str,  # 主营业务
            "operating_scope": str,          # 经营范围
            "org_cn_introduction": str,      # 公司简介
            "org_website": str,              # 官网
            "listed_date": str,              # 上市日期（时间戳）
            "provincial_name": str,          # 所在省份
            "classi_name": str,              # 分类名称
            "affiliate_industry": dict,      # 所属行业 {"ind_code": str, "ind_name": str}
            "error": str | None
        }
    """
    # xq.md 中"是否返回"=1 的字段列表
    RETURN_FIELDS = {
        "org_name_cn",
        "org_short_name_cn",
        "main_operation_business",
        "operating_scope",
        "org_cn_introduction",
        "org_website",
        "listed_date",
        "provincial_name",
        "classi_name",
        "affiliate_industry",
    }

    try:
        # 标准化股票代码并添加市场前缀（xq API 需要前缀如 SZ000423）
        code = _ensure_market_prefix(stock_code)

        stock_individual_basic_info_xq_df = ak.stock_individual_basic_info_xq(symbol=code)
        result = {
            row["item"]: row["value"]
            for _, row in stock_individual_basic_info_xq_df.iterrows()
            if row["item"] in RETURN_FIELDS
        }
        return result
    except Exception:
        logger.error(traceback.format_exc())
        return {"error": traceback.format_exc()}




def get_stock_market_data(stock_code: str) -> Dict[str, Any]:
    """
    获取股票实时市场数据（价格、市值、PE、PB）

    使用东方财富实时行情接口，覆盖沪深京三市所有 A 股。

    Args:
        stock_code: 股票代码，如 "000423" 或 "SH600519"

    Returns:
        {
            "stock_code": str,
            "stock_name": str,
            "current_price": float,       # 当前股价（元）
            "market_cap": float,          # 总市值（元）
            "pe_ratio": float,            # 动态市盈率
            "pb_ratio": float,            # 市净率
            "ps_ratio": float,            # 市销率
            "pcf_ratio": float,           # 市现率
            "52w_high": float,            # 52 周最高价
            "52w_low": float,             # 52 周最低价
            "turnover_rate": float,       # 换手率（%）
            "volume_ratio": float,        # 量比
            "data_date": str,             # 数据日期
            "error": str | None           # 错误信息
        }
    """
    code = _normalize_stock_code(stock_code)
    result: Dict[str, Any] = {
        "stock_code": code,
        "stock_name": "",
        "current_price": 0.0,
        "market_cap": 0.0,
        "pe_ratio": 0.0,
        "pb_ratio": 0.0,
        "ps_ratio": 0.0,
        "pcf_ratio": 0.0,
        "52w_high": 0.0,
        "52w_low": 0.0,
        "turnover_rate": 0.0,
        "volume_ratio": 0.0,
        "data_date": datetime.date.today().isoformat(),
        "error": None,
    }
    try:
        def _float(val, default=0.0) -> float:
            try:
                v = float(val)
                return v if v == v else default  # NaN check
            except (TypeError, ValueError):
                return default

        # 1. 获取实时行情（一次性获取所有扩展数据：PE/PB/PS/PCF/市值等）
        df_spot = ak.stock_zh_a_spot_em()
        row_spot = df_spot[df_spot["代码"] == code]
        if row_spot.empty:
            result["error"] = f"未找到股票代码 {code} 的行情数据"
            logger.warning(result["error"])
            return result

        rs = row_spot.iloc[0]
        # 实时行情列名：代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅,
        #                最高, 最低, 今开, 昨收, 量比, 换手率, 市盈率-动态, 市净率,
        #                总市值, 流通市值, ... (可能还有市销率、市现率)
        result["stock_name"] = str(rs.get("名称", ""))
        result["current_price"] = _float(rs.get("最新价"))
        result["market_cap"] = _float(rs.get("总市值"))
        result["pe_ratio"] = _float(rs.get("市盈率-动态"))
        result["pb_ratio"] = _float(rs.get("市净率"))
        result["ps_ratio"] = _float(rs.get("市销率", 0))      # 可能不存在
        result["pcf_ratio"] = _float(rs.get("市现率", 0))     # 可能不存在
        result["52w_high"] = _float(rs.get("最高"))
        result["52w_low"] = _float(rs.get("最低"))
        result["turnover_rate"] = _float(rs.get("换手率"))
        result["volume_ratio"] = _float(rs.get("量比"))
        result["data_date"] = datetime.date.today().isoformat()

        # 2. 从乐咕乐股获取 PE/PB（如果实时行情没有）
        if result["pe_ratio"] == 0.0 or result["pb_ratio"] == 0.0:
            try:
                df_indicator = ak.stock_a_indicator_lg(symbol=code)
                if df_indicator is not None and not df_indicator.empty:
                    latest = df_indicator.iloc[-1]
                    if result["pe_ratio"] == 0.0:
                        result["pe_ratio"] = _float(latest.get("pe"))
                    if result["pb_ratio"] == 0.0:
                        result["pb_ratio"] = _float(latest.get("pb"))
            except Exception:
                pass

        # 3. 如果实时行情缺少 52w_high/low，尝试从近一年历史数据计算
        if result["52w_high"] == 0.0 or result["52w_low"] == 0.0:
            df_year = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=(datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y%m%d"),
                end_date=datetime.date.today().strftime("%Y%m%d"),
                adjust="qfq"
            )
            if df_year is not None and not df_year.empty:
                result["52w_high"] = _float(df_year["最高"].max())
                result["52w_low"] = _float(df_year["最低"].min())

        logger.info(
            f"市场数据获取成功: {code} {result['stock_name']}, "
            f"价格={result['current_price']}, PE={result['pe_ratio']}, PB={result['pb_ratio']}"
        )
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        result["error"] = str(e)
        logger.error(f"获取股票市场数据失败 {code}: {e}")

    return result


def get_stock_valuation_history(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    获取股票历史估值数据（每日 PE/PB）

    数据来源：乐咕乐股（涵盖近 10 年日频 PE/PB）

    Args:
        stock_code: 6 位股票代码
        start_date: 开始日期，格式 "YYYY-MM-DD"，默认近一年
        end_date:   结束日期，格式 "YYYY-MM-DD"，默认今天

    Returns:
        按日期升序排列的估值列表，每项包含 date / pe / pb
    """
    code = _normalize_stock_code(stock_code)
    if end_date is None:
        end_date = datetime.date.today().isoformat()
    if start_date is None:
        start_date = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()

    try:
        import akshare as ak

        df = ak.stock_a_indicator_lg(symbol=code)
        # 列名：trade_date, pe, pb, ps, dv_ratio, dv_ttm, total_mv
        if df is None or df.empty:
            logger.warning(f"估值历史数据为空: {code}")
            return []

        df = df.rename(columns={"trade_date": "date"})
        df["date"] = df["date"].astype(str)
        df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
        df = df.sort_values("date")

        records = []
        for _, row in df.iterrows():
            def _f(v):
                try:
                    fv = float(v)
                    return fv if fv == fv else 0.0
                except (TypeError, ValueError):
                    return 0.0

            records.append({
                "date": str(row.get("date", "")),
                "pe": _f(row.get("pe")),
                "pb": _f(row.get("pb")),
                "ps": _f(row.get("ps", 0)),
                "dv_ratio": _f(row.get("dv_ratio", 0)),   # 股息率（%）
                "total_mv": _f(row.get("total_mv", 0)),    # 总市值（万元）
            })

        logger.info(f"估值历史获取成功: {code}, 共 {len(records)} 条")
        return records

    except Exception as e:
        logger.error(f"获取估值历史失败 {code}: {e}")
        return []


def get_dividend_history(stock_code: str) -> List[Dict[str, Any]]:
    """
    获取股票历史分红数据

    Args:
        stock_code: 6 位股票代码

    Returns:
        按公告日期降序排列的分红列表，每项包含：
        - report_date:    分红方案公告日
        - dividend_date:  除权除息日
        - cash_per_share: 每股分红（元，税前）
        - shares_before:  分红前股本（万股）
        - payout_ratio:   分红方案描述
    """
    code = _normalize_stock_code(stock_code)
    try:
        import akshare as ak

        df = ak.stock_history_dividend_detail(code=code, indicator="分红")
        if df is None or df.empty:
            logger.warning(f"无分红历史数据: {code}")
            return []

        records = []
        for _, row in df.iterrows():
            def _s(v):
                return str(v).strip() if v is not None else ""

            def _f(v, default=0.0):
                try:
                    fv = float(str(v).replace(",", ""))
                    return fv if fv == fv else default
                except (TypeError, ValueError):
                    return default

            records.append({
                "report_date": _s(row.get("公告日期", "")),
                "dividend_date": _s(row.get("除权除息日", "")),
                "cash_per_share": _f(row.get("派息(税前)(元)", row.get("每股送转", 0))),
                "payout_ratio": _s(row.get("方案说明", "")),
            })

        records.sort(key=lambda x: x["report_date"], reverse=True)
        logger.info(f"分红历史获取成功: {code}, 共 {len(records)} 条")
        return records

    except ImportError:
        logger.error("akshare 未安装")
        return []
    except Exception as e:
        logger.error(f"获取分红历史失败 {code}: {e}")
        return []


def get_dividend_stats(stock_code: str, years: int = 5) -> Dict[str, Any]:
    """
    统计近 N 年的分红情况

    Args:
        stock_code: 股票代码
        years:      统计年数，默认 5 年

    Returns:
        {
            "total_dividends":        int,    # 分红总次数
            "consecutive_years":      int,    # 连续分红年数
            "avg_cash_per_share":     float,  # 近 N 年平均每股分红（元）
            "max_cash_per_share":     float,  # 最高每股分红（元）
            "dividend_years":         list,   # 有分红记录的年份列表
            "latest_cash_per_share":  float,  # 最近一次每股分红（元）
        }
    """
    history = get_dividend_history(stock_code)
    cutoff_year = datetime.date.today().year - years

    recent = []
    for item in history:
        date_str = item.get("report_date", "") or item.get("dividend_date", "")
        try:
            year = int(date_str[:4])
            if year >= cutoff_year:
                recent.append({**item, "year": year})
        except (ValueError, IndexError):
            continue

    if not recent:
        return {
            "total_dividends": 0,
            "consecutive_years": 0,
            "avg_cash_per_share": 0.0,
            "max_cash_per_share": 0.0,
            "dividend_years": [],
            "latest_cash_per_share": 0.0,
        }

    dividend_years = sorted(set(r["year"] for r in recent))
    cash_values = [r["cash_per_share"] for r in recent if r["cash_per_share"] > 0]

    # 连续分红年数（从最近一年往前数）
    consecutive = 0
    current_year = datetime.date.today().year
    for y in range(current_year, current_year - years - 1, -1):
        if y in dividend_years:
            consecutive += 1
        else:
            break

    return {
        "total_dividends": len(recent),
        "consecutive_years": consecutive,
        "avg_cash_per_share": round(sum(cash_values) / len(cash_values), 4) if cash_values else 0.0,
        "max_cash_per_share": max(cash_values) if cash_values else 0.0,
        "dividend_years": dividend_years,
        "latest_cash_per_share": recent[0]["cash_per_share"] if recent else 0.0,
    }


def get_market_data_tools():
    """返回所有市场数据工具函数列表"""
    return [
        get_stock_market_data,
        get_stock_valuation_history,
        get_dividend_history,
        get_dividend_stats,
    ]
