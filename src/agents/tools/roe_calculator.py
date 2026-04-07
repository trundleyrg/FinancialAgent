"""
ROE (净资产收益率) 计算工具

ROE = 净利润 / 净资产 × 100%
衡量公司使用股东权益创造利润的效率

数据来源:
- 净利润: ConsolidatedIncomeStatement.net_profit_attributable_to_parent
- 净资产: ConsolidatedBalanceSheet.total_equity_attributable_to_parent_company
"""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("Agent.ROE")


def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """安全除法，避免除零错误"""
    if denominator == 0 or denominator is None or numerator is None:
        return default
    return numerator / denominator


def _get_value(data: Dict[str, Any], *keys, default: float = 0.0) -> float:
    """
    从字典中获取值，支持多级键查找

    Args:
        data: 数据字典
        *keys: 键路径，如 "balance_sheet", "total_equity"
        default: 默认值

    Returns:
        数值
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    try:
        return float(result) if result is not None else default
    except (ValueError, TypeError):
        return default


def calculate_roe(
    income_statement: Dict[str, Any],
    balance_sheet: Dict[str, Any],
    use_average: bool = False,
    previous_income_statement: Optional[Dict[str, Any]] = None,
    previous_balance_sheet: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    计算净资产收益率 (ROE - Return on Equity)

    ROE = 净利润 / 净资产 × 100%
    衡量公司使用股东权益创造利润的效率

    Args:
        income_statement: 利润表数据（本期），包含:
            - net_profit_attributable_to_parent: 归属于母公司股东的净利润
            - net_profit: 净利润（备用字段）
        balance_sheet: 资产负债表数据（本期），包含:
            - total_equity_attributable_to_parent_company: 归属于母公司所有者权益合计
        use_average: 是否使用期初期末平均值计算（更准确，推荐）
        previous_income_statement: 上期利润表数据（当 use_average=True 时需要）
        previous_balance_sheet: 上期资产负债表数据（当 use_average=True 时需要）

    Returns:
        Dict 包含:
        - roe: 净资产收益率 (%)
        - net_profit: 净利润 (元)
        - equity: 净资产 (元)
        - calculation_method: 计算方法说明
        - is_valid: 计算是否有效

    Note:
        标准ROE计算公式:
        - 简单法: ROE = 本期净利润 / 期末净资产 × 100%
        - 加权平均法: ROE = 本期净利润 / ((期初净资产 + 期末净资产) / 2) × 100%

        加权平均法考虑了期初和期末净资产的变化，结果更为准确
    """
    try:
        # 提取净利润（归属于母公司股东）
        net_profit = _get_value(income_statement, "net_profit_attributable_to_parent")
        if net_profit == 0.0:
            net_profit = _get_value(income_statement, "net_profit")  # 备用字段

        if use_average and previous_income_statement and previous_balance_sheet:
            # 加权平均法：需要期初和期末数据
            current_equity = _get_value(balance_sheet, "total_equity_attributable_to_parent_company")
            previous_equity = _get_value(previous_balance_sheet, "total_equity_attributable_to_parent_company")

            if previous_equity and previous_equity > 0:
                avg_equity = (current_equity + previous_equity) / 2
                equity = avg_equity
                roe = _safe_divide(net_profit, avg_equity) * 100
                calculation_method = "加权平均法"
            else:
                # 期初数据不可用，降级为简单法
                equity = _get_value(balance_sheet, "total_equity_attributable_to_parent_company")
                roe = _safe_divide(net_profit, equity) * 100
                calculation_method = "简单法（期初数据不可用）"
        else:
            # 简单法：使用期末数据
            equity = _get_value(balance_sheet, "total_equity_attributable_to_parent_company")
            roe = _safe_divide(net_profit, equity) * 100
            calculation_method = "简单法（期末数据）"

        is_valid = net_profit != 0.0 and equity != 0.0

        logger.info(
            f"ROE计算完成: {roe:.2f}%, "
            f"净利润: {net_profit:.2f}元, 净资产: {equity:.2f}元, "
            f"方法: {calculation_method}"
        )

        return {
            "roe": round(roe, 4),
            "net_profit": round(net_profit, 2),
            "equity": round(equity, 2),
            "calculation_method": calculation_method,
            "is_valid": is_valid
        }

    except Exception as e:
        logger.error(f"计算ROE失败: {e}")
        return {
            "roe": 0.0,
            "net_profit": 0.0,
            "equity": 0.0,
            "calculation_method": "计算失败",
            "is_valid": False,
            "error": str(e)
        }


def calculate_roe_from_db(
    db_connector,
    company_name: str,
    stock_code: str,
    report_year: int,
    report_period: str = "FY",
    use_average: bool = True
) -> Dict[str, Any]:
    """
    从数据库查询数据并计算ROE

    Args:
        db_connector: 数据库连接器
        company_name: 公司名称
        stock_code: 股票代码
        report_year: 报告年份
        report_period: 报告期间 (Q1, H1, Q3, FY)
        use_average: 是否使用加权平均法

    Returns:
        ROE计算结果字典
    """
    try:
        # 查询本期利润表
        income_records = db_connector.filter_records(
            "consolidated_income_statement",
            company_name=company_name,
            stock_code=stock_code,
            report_year=report_year,
            report_period=report_period
        )

        # 查询本期资产负债表
        balance_records = db_connector.filter_records(
            "consolidated_balance_sheet",
            company_name=company_name,
            stock_code=stock_code,
            report_year=report_year,
            report_period=report_period
        )

        if not income_records or not balance_records:
            logger.warning(f"未找到 {company_name} {report_year}{report_period} 的财报数据")
            return {
                "roe": 0.0,
                "net_profit": 0.0,
                "equity": 0.0,
                "calculation_method": "数据不足",
                "is_valid": False
            }

        # 转换记录为字典
        income_record = income_records[0]
        balance_record = balance_records[0]

        if hasattr(income_record, '__dict__'):
            income_data = income_record.__dict__
            balance_data = balance_record.__dict__
        else:
            income_data = dict(income_record)
            balance_data = dict(balance_record)

        # 移除Peewee内部字段
        for key in ['_database', '_dirty', 'id', '_state']:
            income_data.pop(key, None)
            balance_data.pop(key, None)

        # 如果使用加权平均法，查询上期数据
        previous_income_data = None
        previous_balance_data = None

        if use_average:
            # 计算上一个报告期
            if report_period == "FY":
                # 年报需要上年同期数据
                prev_year = report_year - 1
                prev_period = "FY"
            elif report_period == "Q1":
                # 一季报需要上年年报
                prev_year = report_year - 1
                prev_period = "FY"
            elif report_period == "H1":
                # 半年报需要上年同期半年报
                prev_year = report_year - 1
                prev_period = "H1"
            elif report_period == "Q3":
                # 三季报需要上年同期三季报
                prev_year = report_year - 1
                prev_period = "Q3"
            else:
                prev_year = report_year - 1
                prev_period = "FY"

            # 查询上期利润表
            prev_income_records = db_connector.filter_records(
                "consolidated_income_statement",
                company_name=company_name,
                stock_code=stock_code,
                report_year=prev_year,
                report_period=prev_period
            )

            # 查询上期资产负债表
            prev_balance_records = db_connector.filter_records(
                "consolidated_balance_sheet",
                company_name=company_name,
                stock_code=stock_code,
                report_year=prev_year,
                report_period=prev_period
            )

            if prev_income_records and prev_balance_records:
                prev_income = prev_income_records[0]
                prev_balance = prev_balance_records[0]

                if hasattr(prev_income, '__dict__'):
                    previous_income_data = prev_income.__dict__
                    previous_balance_data = prev_balance.__dict__
                else:
                    previous_income_data = dict(prev_income)
                    previous_balance_data = dict(prev_balance)

                for key in ['_database', '_dirty', 'id', '_state']:
                    previous_income_data.pop(key, None)
                    previous_balance_data.pop(key, None)

        # 计算ROE
        return calculate_roe(
            income_statement=income_data,
            balance_sheet=balance_data,
            use_average=use_average,
            previous_income_statement=previous_income_data,
            previous_balance_sheet=previous_balance_data
        )

    except Exception as e:
        logger.error(f"从数据库计算ROE失败: {e}")
        return {
            "roe": 0.0,
            "net_profit": 0.0,
            "equity": 0.0,
            "calculation_method": "计算失败",
            "is_valid": False,
            "error": str(e)
        }
