"""
财务计算工具

提供各种财务指标的计算函数
"""
from typing import Dict, Any, Optional, List, Callable
import logging

logger = logging.getLogger("Agent.Calculation")


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
        *keys: 键路径，如 "balance_sheet", "monetary_funds"
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


def calculate_profitability(income_statement: Dict[str, Any]) -> Dict[str, float]:
    """
    计算盈利能力指标

    Args:
        income_statement: 利润表数据

    Returns:
        盈利能力指标字典
    """
    try:
        revenue = _get_value(income_statement, "operating_revenue")
        gross_profit = _get_value(income_statement, "gross_profit")
        net_profit = _get_value(income_statement, "net_profit")
        total_assets = _get_value(income_statement, "total_assets")  # 需要从资产负债表获取
        equity = _get_value(income_statement, "equity")  # 需要从资产负债表获取

        # 毛利率
        gross_margin = _safe_divide(gross_profit, revenue) * 100

        # 净利率
        net_margin = _safe_divide(net_profit, revenue) * 100

        # ROE (净资产收益率) - 需要期初期末平均值，这里简化处理
        roe = _safe_divide(net_profit, equity) * 100

        # ROA (资产收益率) - 需要期初期末平均值，这里简化处理
        roa = _safe_divide(net_profit, total_assets) * 100

        return {
            "gross_margin": round(gross_margin, 2),
            "net_margin": round(net_margin, 2),
            "roe": round(roe, 2),
            "roa": round(roa, 2)
        }
    except Exception as e:
        logger.error(f"计算盈利能力指标失败: {e}")
        return {
            "gross_margin": 0.0,
            "net_margin": 0.0,
            "roe": 0.0,
            "roa": 0.0
        }


def calculate_liquidity(balance_sheet: Dict[str, Any]) -> Dict[str, float]:
    """
    计算流动性指标

    Args:
        balance_sheet: 资产负债表数据

    Returns:
        流动性指标字典
    """
    try:
        # 流动资产
        current_assets = _get_value(balance_sheet, "current_assets")

        # 流动负债
        current_liabilities = _get_value(balance_sheet, "current_liabilities")

        # 货币资金
        monetary_funds = _get_value(balance_sheet, "monetary_funds")

        # 存货
        inventory = _get_value(balance_sheet, "inventory")

        # 流动比率
        current_ratio = _safe_divide(current_assets, current_liabilities)

        # 速动比率 (流动资产 - 存货) / 流动负债
        quick_assets = current_assets - inventory
        quick_ratio = _safe_divide(quick_assets, current_liabilities)

        # 现金比率 (货币资金 / 流动负债)
        cash_ratio = _safe_divide(monetary_funds, current_liabilities)

        return {
            "current_ratio": round(current_ratio, 2),
            "quick_ratio": round(quick_ratio, 2),
            "cash_ratio": round(cash_ratio, 2)
        }
    except Exception as e:
        logger.error(f"计算流动性指标失败: {e}")
        return {
            "current_ratio": 0.0,
            "quick_ratio": 0.0,
            "cash_ratio": 0.0
        }


def calculate_solvency(balance_sheet: Dict[str, Any], income_statement: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """
    计算偿债能力指标

    Args:
        balance_sheet: 资产负债表数据
        income_statement: 利润表数据（可选，用于计算利息保障倍数）

    Returns:
        偿债能力指标字典
    """
    try:
        # 总负债
        total_liabilities = _get_value(balance_sheet, "total_liabilities")

        # 总资产
        total_assets = _get_value(balance_sheet, "total_assets")

        # 股东权益
        total_equity = _get_value(balance_sheet, "total_equity")

        # 资产负债率
        debt_to_asset = _safe_divide(total_liabilities, total_assets) * 100

        # 产权比率 (总负债 / 股东权益)
        debt_to_equity = _safe_divide(total_liabilities, total_equity)

        # 利息保障倍数（需要财务费用和利润数据）
        interest_coverage = 0.0
        if income_statement:
            ebit = _get_value(income_statement, "ebit")  # 息税前利润
            interest_expense = _get_value(income_statement, "interest_expense")  # 利息支出
            if interest_expense and interest_expense > 0:
                interest_coverage = _safe_divide(ebit, interest_expense)

        return {
            "debt_to_asset": round(debt_to_asset, 2),
            "debt_to_equity": round(debt_to_equity, 2),
            "interest_coverage": round(interest_coverage, 2)
        }
    except Exception as e:
        logger.error(f"计算偿债能力指标失败: {e}")
        return {
            "debt_to_asset": 0.0,
            "debt_to_equity": 0.0,
            "interest_coverage": 0.0
        }


def calculate_growth(current_data: Dict[str, Any], previous_data: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """
    计算成长性指标

    Args:
        current_data: 当前期数据（包含 income_statement 等）
        previous_data: 上期数据（可选）

    Returns:
        成长性指标字典
    """
    try:
        current_income = current_data.get("income_statement", {})
        previous_income = previous_data.get("income_statement", {}) if previous_data else {}

        current_revenue = _get_value(current_income, "operating_revenue")
        previous_revenue = _get_value(previous_income, "operating_revenue")

        current_net_profit = _get_value(current_income, "net_profit")
        previous_net_profit = _get_value(previous_income, "net_profit")

        # 营收增长率
        revenue_growth = 0.0
        if previous_revenue and previous_revenue > 0:
            revenue_growth = ((current_revenue - previous_revenue) / previous_revenue) * 100

        # 净利润增长率
        profit_growth = 0.0
        if previous_net_profit and previous_net_profit > 0:
            profit_growth = ((current_net_profit - previous_net_profit) / previous_net_profit) * 100

        return {
            "revenue_growth": round(revenue_growth, 2),
            "profit_growth": round(profit_growth, 2)
        }
    except Exception as e:
        logger.error(f"计算成长性指标失败: {e}")
        return {
            "revenue_growth": 0.0,
            "profit_growth": 0.0
        }


def calculate_cyclical_metrics(
    balance_sheet: Dict[str, Any],
    income_statement: Dict[str, Any],
    cash_flow: Dict[str, Any]
) -> Dict[str, Any]:
    """
    计算周期股专用指标

    Args:
        balance_sheet: 资产负债表数据
        income_statement: 利润表数据
        cash_flow: 现金流量表数据

    Returns:
        周期股专用指标字典
    """
    try:
        # 总资产 (用于计算产能利用率等)
        total_assets = _get_value(balance_sheet, "total_assets")

        # 固定资产
        fixed_assets = _get_value(balance_sheet, "fixed_assets")

        # 存货
        inventory = _get_value(balance_sheet, "inventory")

        # 营业收入
        revenue = _get_value(income_statement, "operating_revenue")

        # 营业成本
        operating_cost = _get_value(income_statement, "operating_cost")

        # 经营活动现金流净额
        operating_cash_flow = _get_value(cash_flow, "operating_cash_flow")

        # 资本支出 (投资活动现金流净额 - 无形资产等)
        capex = _get_value(cash_flow, "investing_cash_flow")

        # 产能利用率 (简化计算：营业收入 / 总资产)
        capacity_utilization = _safe_divide(revenue, total_assets) * 100

        # 存货周转天数 (简化计算)
        inventory_turnover = 0.0
        if operating_cost > 0 and inventory > 0:
            inventory_turnover = (inventory / operating_cost) * 365

        # 固定资产周转率
        fixed_asset_turnover = _safe_divide(revenue, fixed_assets) if fixed_assets > 0 else 0.0

        # 现金流健康度 (经营活动现金流 / 净利润)
        net_profit = _get_value(income_statement, "net_profit")
        cash_flow_health = _safe_divide(operating_cash_flow, net_profit) if net_profit > 0 else 0.0

        return {
            "capacity_utilization": round(capacity_utilization, 2),
            "inventory_turnover_days": round(inventory_turnover, 2),
            "fixed_asset_turnover": round(fixed_asset_turnover, 2),
            "cash_flow_health": round(cash_flow_health, 2),
            "capex_intensity": "high" if abs(capex) > total_assets * 0.1 else "low"
        }
    except Exception as e:
        logger.error(f"计算周期股指标失败: {e}")
        return {
            "capacity_utilization": 0.0,
            "inventory_turnover_days": 0.0,
            "fixed_asset_turnover": 0.0,
            "cash_flow_health": 0.0,
            "capex_intensity": "unknown"
        }


def get_calculation_tools() -> List[Callable]:
    """
    获取所有计算工具

    Returns:
        计算工具函数列表
    """
    return [
        calculate_profitability,
        calculate_liquidity,
        calculate_solvency,
        calculate_growth,
        calculate_cyclical_metrics
    ]
