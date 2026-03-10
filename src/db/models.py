"""
数据库 ORM 模型及 Pydantic 数据验证
"""    
from typing import Optional, List
from datetime import datetime
from enum import Enum
from peewee import *
from pydantic import BaseModel, Field, field_validator

# 数据库连接对象，将在DatabaseConnector中初始化
db = DatabaseProxy()  # 使用DatabaseProxy允许动态设置实际的数据库对象

# --- 0. 定义周期枚举 ---

class ReportPeriod(str, Enum):
    """
    财务报告周期枚举
    定义了常见的财务报告发布周期类型
    """
    Q1 = "Q1"          # 第一季度报告，通常在4月底前发布
    H1 = "H1"          # 半年度报告，通常在8月底前发布（Q2结束）
    Q3 = "Q3"          # 第三季度报告，通常在10月底前发布
    FY = "FY"          # 年度报告，通常在次年4月底前发布（Full Year）

# --- 1. SQLAlchemy ORM Models ---
# （用于数据库持久化）

class FinancialReport(Model):
    """
    财务报告 ORM 模型
    用于存储财务报告的基本元数据信息
    """
    
    id = AutoField(primary_key=True)  # 指标唯一标识符，主键
    company_name = CharField(max_length=255, null=False, index=True)  # 公司全名，用于查询索引
    company_short_name = CharField(max_length=255, null=False)   # 公司简称，用于查询索引
    stock_code = CharField(max_length=20, null=False, index=True)  # 股票代码，用于查询索引
    
    # 年份 + 周期 共同定义时间点
    report_year = IntegerField(null=False, index=True)  # 报告所属年份，如2023，用于查询索引
    report_period = CharField(max_length=10, null=False, index=True)  # 报告周期（Q1/H1/Q3/FY），用于查询索引

    source_file = CharField(max_length=500, null=True)  # 源PDF文件路径，用于追溯原始数据
    created_at = DateTimeField(default=datetime.now)  # 记录创建时间，自动填充当前时间

    class Meta:
        database = db
        table_name = 'financial_reports'

class FinancialMetric(Model):
    """
    财务指标 ORM 模型
    用于存储从财务报告中提取的具体财务数据指标
    """
    id = AutoField(primary_key=True)  # 指标唯一标识符，主键
    report = ForeignKeyField(FinancialReport, backref='metrics', on_delete='CASCADE')  # 外键，关联到财务报告
    metric_name = CharField(max_length=100, null=False)  # 指标名称，如"营业收入"、"净利润"等
    value = FloatField(null=False)  # 指标的具体数值
    unit = CharField(max_length=20, null=True)  # 数值单位，如"元"、"万元"、"%"等
    period = CharField(max_length=50, null=True)  # 报告期间，如"年度"、"季度"等
    source_context = TextField(null=True)  # 指标在原报告中的上下文内容，用于溯源验证
    page_number = IntegerField(null=True)  # 指标在原报告中的页码位置

    class Meta:
        database = db
        table_name = 'financial_metrics'


class ConsolidatedBalanceSheet(Model):
    """
    合并资产负债表 ORM 模型
    用于存储合并资产负债表的所有财务指标
    """
    id = AutoField(primary_key=True)
    company_name = CharField(max_length=255, null=False, index=True)
    stock_code = CharField(max_length=20, null=False, index=True)
    report_year = IntegerField(null=False, index=True)
    report_period = CharField(max_length=10, null=False, index=True)

    # 流动资产
    monetary_funds = FloatField(null=True, help_text="货币资金")  # 货币资金
    reserve_for_settlement = FloatField(null=True, help_text="结算备付金")  # 结算备付金
    funds_lent_out = FloatField(null=True, help_text="拆出资金")  # 拆出资金
    trading_financial_assets = FloatField(null=True, help_text="交易性金融资产")  # 交易性金融资产
    derivative_financial_assets = FloatField(null=True, help_text="衍生金融资产")  # 衍生金融资产
    notes_receivable = FloatField(null=True, help_text="应收票据")  # 应收票据
    accounts_receivable = FloatField(null=True, help_text="应收账款")  # 应收账款
    financing_receivables = FloatField(null=True, help_text="应收款项融资")  # 应收款项融资
    prepayments = FloatField(null=True, help_text="预付款项")  # 预付款项
    premiums_receivable = FloatField(null=True, help_text="应收保费")  # 应收保费
    reinsurance_receivables = FloatField(null=True, help_text="应收分保账款")  # 应收分保账款
    reinsurance_contract_reserves_receivable = FloatField(null=True, help_text="应收分保合同准备金")  # 应收分保合同准备金
    other_receivables = FloatField(null=True, help_text="其他应收款")  # 其他应收款
    interest_receivable = FloatField(null=True, help_text="其中：应收利息")  # 其中：应收利息
    dividend_receivable = FloatField(null=True, help_text="应收股利")  # 应收股利
    buy_back_securities_financial_assets = FloatField(null=True, help_text="买入返售金融资产")  # 买入返售金融资产
    inventory = FloatField(null=True, help_text="存货")  # 存货
    data_resources_inventory = FloatField(null=True, help_text="其中：数据资源")  # 其中：数据资源
    contract_assets = FloatField(null=True, help_text="合同资产")  # 合同资产
    assets_held_for_sale = FloatField(null=True, help_text="持有待售资产")  # 持有待售资产
    non_current_assets_due_within_one_year = FloatField(null=True, help_text="一年内到期的非流动资产")  # 一年内到期的非流动资产
    other_current_assets = FloatField(null=True, help_text="其他流动资产")  # 其他流动资产
    total_current_assets = FloatField(null=True, help_text="流动资产合计")  # 流动资产合计

    # 非流动资产
    loans_and_advances_granted = FloatField(null=True, help_text="发放贷款和垫款")  # 发放贷款和垫款
    debt_investments = FloatField(null=True, help_text="债权投资")  # 债权投资
    other_debt_investments = FloatField(null=True, help_text="其他债权投资")  # 其他债权投资
    long_term_receivables = FloatField(null=True, help_text="长期应收款")  # 长期应收款
    long_term_equity_investments = FloatField(null=True, help_text="长期股权投资")  # 长期股权投资
    other_equity_instrument_investments = FloatField(null=True, help_text="其他权益工具投资")  # 其他权益工具投资
    other_non_current_financial_assets = FloatField(null=True, help_text="其他非流动金融资产")  # 其他非流动金融资产
    investment_real_estate = FloatField(null=True, help_text="投资性房地产")  # 投资性房地产
    fixed_assets = FloatField(null=True, help_text="固定资产")  # 固定资产
    construction_in_progress = FloatField(null=True, help_text="在建工程")  # 在建工程
    productive_biological_assets = FloatField(null=True, help_text="生产性生物资产")  # 生产性生物资产
    oil_and_gas_assets = FloatField(null=True, help_text="油气资产")  # 油气资产
    right_of_use_assets = FloatField(null=True, help_text="使用权资产")  # 使用权资产
    intangible_assets = FloatField(null=True, help_text="无形资产")  # 无形资产
    data_resources_intangible = FloatField(null=True, help_text="其中：数据资源")  # 其中：数据资源
    development_expenditure = FloatField(null=True, help_text="开发支出")  # 开发支出
    data_resources_development = FloatField(null=True, help_text="其中：数据资源")  # 其中：数据资源
    goodwill = FloatField(null=True, help_text="商誉")  # 商誉
    long_term_prepaid_expenses = FloatField(null=True, help_text="长期待摊费用")  # 长期待摊费用
    deferred_tax_assets = FloatField(null=True, help_text="递延所得税资产")  # 递延所得税资产
    other_non_current_assets = FloatField(null=True, help_text="其他非流动资产")  # 其他非流动资产
    total_non_current_assets = FloatField(null=True, help_text="非流动资产合计")  # 非流动资产合计
    total_assets = FloatField(null=True, help_text="资产总计")  # 资产总计

    # 流动负债
    short_term_borrowings = FloatField(null=True, help_text="短期借款")  # 短期借款
    borrowings_from_central_bank = FloatField(null=True, help_text="向中央银行借款")  # 向中央银行借款
    funds_borrowed = FloatField(null=True, help_text="拆入资金")  # 拆入资金
    trading_financial_liabilities = FloatField(null=True, help_text="交易性金融负债")  # 交易性金融负债
    derivative_financial_liabilities = FloatField(null=True, help_text="衍生金融负债")  # 衍生金融负债
    notes_payable = FloatField(null=True, help_text="应付票据")  # 应付票据
    accounts_payable = FloatField(null=True, help_text="应付账款")  # 应付账款
    advance_from_customers = FloatField(null=True, help_text="预收款项")  # 预收款项
    contract_liabilities = FloatField(null=True, help_text="合同负债")  # 合同负债
    sell_repurchase_securities_funds = FloatField(null=True, help_text="卖出回购金融资产款")  # 卖出回购金融资产款
    deposits_and_interbank_placement = FloatField(null=True, help_text="吸收存款及同业存放")  # 吸收存款及同业存放
    proxy_trading_securities_funds = FloatField(null=True, help_text="代理买卖证券款")  # 代理买卖证券款
    proxy_underwriting_securities_funds = FloatField(null=True, help_text="代理承销证券款")  # 代理承销证券款
    employee_benefits_payable = FloatField(null=True, help_text="应付职工薪酬")  # 应付职工薪酬
    taxes_payable = FloatField(null=True, help_text="应交税费")  # 应交税费
    other_payables = FloatField(null=True, help_text="其他应付款")  # 其他应付款
    interest_payable = FloatField(null=True, help_text="其中：应付利息")  # 其中：应付利息
    dividend_payable = FloatField(null=True, help_text="应付股利")  # 应付股利
    commission_and_brokerage_payable = FloatField(null=True, help_text="应付手续费及佣金")  # 应付手续费及佣金
    reinsurance_payables = FloatField(null=True, help_text="应付分保账款")  # 应付分保账款
    liabilities_held_for_sale = FloatField(null=True, help_text="持有待售负债")  # 持有待售负债
    non_current_liabilities_due_within_one_year = FloatField(null=True, help_text="一年内到期的非流动负债")  # 一年内到期的非流动负债
    other_current_liabilities = FloatField(null=True, help_text="其他流动负债")  # 其他流动负债
    total_current_liabilities = FloatField(null=True, help_text="流动负债合计")  # 流动负债合计

    # 非流动负债
    insurance_contract_reserves = FloatField(null=True, help_text="保险合同准备金")  # 保险合同准备金
    long_term_borrowings = FloatField(null=True, help_text="长期借款")  # 长期借款
    bonds_payable = FloatField(null=True, help_text="应付债券")  # 应付债券
    preferred_stock_bonds = FloatField(null=True, help_text="其中：优先股")  # 其中：优先股
    perpetual_bonds = FloatField(null=True, help_text="永续债")  # 永续债
    lease_liabilities = FloatField(null=True, help_text="租赁负债")  # 租赁负债
    long_term_payables = FloatField(null=True, help_text="长期应付款")  # 长期应付款
    long_term_employee_benefits_payable = FloatField(null=True, help_text="长期应付职工薪酬")  # 长期应付职工薪酬
    estimated_liabilities = FloatField(null=True, help_text="预计负债")  # 预计负债
    deferred_income = FloatField(null=True, help_text="递延收益")  # 递延收益
    deferred_tax_liabilities = FloatField(null=True, help_text="递延所得税负债")  # 递延所得税负债
    other_non_current_liabilities = FloatField(null=True, help_text="其他非流动负债")  # 其他非流动负债
    total_non_current_liabilities = FloatField(null=True, help_text="非流动负债合计")  # 非流动负债合计
    total_liabilities = FloatField(null=True, help_text="负债合计")  # 负债合计

    # 所有者权益
    paid_in_capital = FloatField(null=True, help_text="实收资本")  # 实收资本
    other_equity_instruments = FloatField(null=True, help_text="其他权益工具")  # 其他权益工具
    preferred_stock_equity = FloatField(null=True, help_text="其中：优先股（权益）")  # 其中：优先股
    perpetual_bonds_equity = FloatField(null=True, help_text="永续债（权益）")  # 永续债
    capital_reserve = FloatField(null=True, help_text="资本公积")  # 资本公积
    treasury_stock = FloatField(null=True, help_text="减：库存股")  # 减：库存股
    other_comprehensive_income = FloatField(null=True, help_text="其他综合收益")  # 其他综合收益
    special_reserve = FloatField(null=True, help_text="专项储备")  # 专项储备
    surplus_reserve = FloatField(null=True, help_text="盈余公积")  # 盈余公积
    general_risk_reserve = FloatField(null=True, help_text="一般风险准备")  # 一般风险准备
    retained_earnings = FloatField(null=True, help_text="未分配利润")  # 未分配利润
    total_equity_attributable_to_parent_company = FloatField(null=True, help_text="归属于母公司所有者权益")  # 归属于母公司所有者权益
    minority_interest = FloatField(null=True, help_text="少数股东权益")  # 少数股东权益
    total_owners_equity = FloatField(null=True, help_text="所有者权益")  # 所有者权益
    total_liabilities_and_owners_equity = FloatField(null=True, help_text="负债和所有者权益")  # 负债和所有者权益

    class Meta:
        database = db
        table_name = 'consolidated_balance_sheet'


class ParentCompanyBalanceSheet(Model):
    """
    母公司资产负债表 ORM 模型
    用于存储母公司资产负债表的所有财务指标
    """
    id = AutoField(primary_key=True)
    company_name = CharField(max_length=255, null=False, index=True)
    stock_code = CharField(max_length=20, null=False, index=True)
    report_year = IntegerField(null=False, index=True)
    report_period = CharField(max_length=10, null=False, index=True)

    # 流动资产
    monetary_funds = FloatField(null=True, help_text="货币资金")  # 货币资金
    trading_financial_assets = FloatField(null=True, help_text="交易性金融资产")  # 交易性金融资产
    derivative_financial_assets = FloatField(null=True, help_text="衍生金融资产")  # 衍生金融资产
    notes_receivable = FloatField(null=True, help_text="应收票据")  # 应收票据
    accounts_receivable = FloatField(null=True, help_text="应收账款")  # 应收账款
    financing_receivables = FloatField(null=True, help_text="应收款项融资")  # 应收款项融资
    prepayments = FloatField(null=True, help_text="预付款项")  # 预付款项
    other_receivables = FloatField(null=True, help_text="其他应收款")  # 其他应收款
    interest_receivable = FloatField(null=True, help_text="其中：应收利息")  # 其中：应收利息
    dividend_receivable = FloatField(null=True, help_text="应收股利")  # 应收股利
    inventory = FloatField(null=True, help_text="存货")  # 存货
    data_resources_inventory = FloatField(null=True, help_text="其中：数据资源")  # 其中：数据资源
    contract_assets = FloatField(null=True, help_text="合同资产")  # 合同资产
    assets_held_for_sale = FloatField(null=True, help_text="持有待售资产")  # 持有待售资产
    non_current_assets_due_within_one_year = FloatField(null=True, help_text="一年内到期的非流动资产")  # 一年内到期的非流动资产
    other_current_assets = FloatField(null=True, help_text="其他流动资产")  # 其他流动资产
    total_current_assets = FloatField(null=True, help_text="流动资产合计")  # 流动资产合计

    # 非流动资产
    debt_investments = FloatField(null=True, help_text="债权投资")  # 债权投资
    other_debt_investments = FloatField(null=True, help_text="其他债权投资")  # 其他债权投资
    long_term_receivables = FloatField(null=True, help_text="长期应收款")  # 长期应收款
    long_term_equity_investments = FloatField(null=True, help_text="长期股权投资")  # 长期股权投资
    other_equity_instrument_investments = FloatField(null=True, help_text="其他权益工具投资")  # 其他权益工具投资
    other_non_current_financial_assets = FloatField(null=True, help_text="其他非流动金融资产")  # 其他非流动金融资产
    investment_real_estate = FloatField(null=True, help_text="投资性房地产")  # 投资性房地产
    fixed_assets = FloatField(null=True, help_text="固定资产")  # 固定资产
    construction_in_progress = FloatField(null=True, help_text="在建工程")  # 在建工程
    productive_biological_assets = FloatField(null=True, help_text="生产性生物资产")  # 生产性生物资产
    oil_and_gas_assets = FloatField(null=True, help_text="油气资产")  # 油气资产
    right_of_use_assets = FloatField(null=True, help_text="使用权资产")  # 使用权资产
    intangible_assets = FloatField(null=True, help_text="无形资产")  # 无形资产
    data_resources_intangible = FloatField(null=True, help_text="其中：数据资源")  # 其中：数据资源
    development_expenditure = FloatField(null=True, help_text="开发支出")  # 开发支出
    data_resources_development = FloatField(null=True, help_text="其中：数据资源")  # 其中：数据资源
    goodwill = FloatField(null=True, help_text="商誉")  # 商誉
    long_term_prepaid_expenses = FloatField(null=True, help_text="长期待摊费用")  # 长期待摊费用
    deferred_tax_assets = FloatField(null=True, help_text="递延所得税资产")  # 递延所得税资产
    other_non_current_assets = FloatField(null=True, help_text="其他非流动资产")  # 其他非流动资产
    total_non_current_assets = FloatField(null=True, help_text="非流动资产合计")  # 非流动资产合计
    total_assets = FloatField(null=True, help_text="资产总计")  # 资产总计

    # 流动负债
    short_term_borrowings = FloatField(null=True, help_text="短期借款")  # 短期借款
    trading_financial_liabilities = FloatField(null=True, help_text="交易性金融负债")  # 交易性金融负债
    derivative_financial_liabilities = FloatField(null=True, help_text="衍生金融负债")  # 衍生金融负债
    notes_payable = FloatField(null=True, help_text="应付票据")  # 应付票据
    accounts_payable = FloatField(null=True, help_text="应付账款")  # 应付账款
    advance_from_customers = FloatField(null=True, help_text="预收款项")  # 预收款项
    contract_liabilities = FloatField(null=True, help_text="合同负债")  # 合同负债
    employee_benefits_payable = FloatField(null=True, help_text="应付职工薪酬")  # 应付职工薪酬
    taxes_payable = FloatField(null=True, help_text="应交税费")  # 应交税费
    other_payables = FloatField(null=True, help_text="其他应付款")  # 其他应付款
    interest_payable = FloatField(null=True, help_text="其中：应付利息")  # 其中：应付利息
    dividend_payable = FloatField(null=True, help_text="应付股利")  # 应付股利
    liabilities_held_for_sale = FloatField(null=True, help_text="持有待售负债")  # 持有待售负债
    non_current_liabilities_due_within_one_year = FloatField(null=True, help_text="一年内到期的非流动负债")  # 一年内到期的非流动负债
    other_current_liabilities = FloatField(null=True, help_text="其他流动负债")  # 其他流动负债
    total_current_liabilities = FloatField(null=True, help_text="流动负债合计")  # 流动负债合计

    # 非流动负债
    long_term_borrowings = FloatField(null=True, help_text="长期借款")  # 长期借款
    bonds_payable = FloatField(null=True, help_text="应付债券")  # 应付债券
    preferred_stock_bonds = FloatField(null=True, help_text="其中：优先股")  # 其中：优先股
    perpetual_bonds = FloatField(null=True, help_text="永续债")  # 永续债
    lease_liabilities = FloatField(null=True, help_text="租赁负债")  # 租赁负债
    long_term_payables = FloatField(null=True, help_text="长期应付款")  # 长期应付款
    long_term_employee_benefits_payable = FloatField(null=True, help_text="长期应付职工薪酬")  # 长期应付职工薪酬
    estimated_liabilities = FloatField(null=True, help_text="预计负债")  # 预计负债
    deferred_income = FloatField(null=True, help_text="递延收益")  # 递延收益
    deferred_tax_liabilities = FloatField(null=True, help_text="递延所得税负债")  # 递延所得税负债
    other_non_current_liabilities = FloatField(null=True, help_text="其他非流动负债")  # 其他非流动负债
    total_non_current_liabilities = FloatField(null=True, help_text="非流动负债合计")  # 非流动负债合计
    total_liabilities = FloatField(null=True, help_text="负债合计")  # 负债合计

    # 所有者权益
    paid_in_capital = FloatField(null=True, help_text="实收资本")  # 实收资本
    other_equity_instruments = FloatField(null=True, help_text="其他权益工具")  # 其他权益工具
    preferred_stock_equity = FloatField(null=True, help_text="其中：优先股")  # 其中：优先股
    perpetual_bonds_equity = FloatField(null=True, help_text="永续债")  # 永续债
    capital_reserve = FloatField(null=True, help_text="资本公积")  # 资本公积
    treasury_stock = FloatField(null=True, help_text="减：库存股")  # 减：库存股
    other_comprehensive_income = FloatField(null=True, help_text="其他综合收益")  # 其他综合收益
    special_reserve = FloatField(null=True, help_text="专项储备")  # 专项储备
    surplus_reserve = FloatField(null=True, help_text="盈余公积")  # 盈余公积
    retained_earnings = FloatField(null=True, help_text="未分配利润")  # 未分配利润
    total_owners_equity = FloatField(null=True, help_text="所有者权益")  # 所有者权益
    total_liabilities_and_owners_equity = FloatField(null=True, help_text="负债和所有者权益")  # 负债和所有者权益

    class Meta:
        database = db
        table_name = 'parent_company_balance_sheet'


class ConsolidatedIncomeStatement(Model):
    """
    合并利润表 ORM 模型
    用于存储合并利润表的所有财务指标
    """
    id = AutoField(primary_key=True)
    company_name = CharField(max_length=255, null=False, index=True)
    stock_code = CharField(max_length=20, null=False, index=True)
    report_year = IntegerField(null=False, index=True)
    report_period = CharField(max_length=10, null=False, index=True)

    # 营业收入与成本
    total_operating_revenue = FloatField(null=True, help_text="一、营业总收入")  # 一、营业总收入
    operating_revenue = FloatField(null=True, help_text="其中：营业收入")  # 其中：营业收入
    interest_income = FloatField(null=True, help_text="利息收入")  # 利息收入
    earned_premium = FloatField(null=True, help_text="已赚保费")  # 已赚保费
    commission_and_fee_income = FloatField(null=True, help_text="手续费及佣金收入")  # 手续费及佣金收入
    total_operating_costs = FloatField(null=True, help_text="二、营业总成本")  # 二、营业总成本
    operating_costs = FloatField(null=True, help_text="其中：营业成本")  # 其中：营业成本
    interest_expense = FloatField(null=True, help_text="利息支出")  # 利息支出
    commission_and_fee_expense = FloatField(null=True, help_text="手续费及佣金支出")  # 手续费及佣金支出
    surrender_value = FloatField(null=True, help_text="退保金")  # 退保金
    claims_expenses_net = FloatField(null=True, help_text="赔付支出净额")  # 赔付支出净额
    net_withdrawal_of_insurance_contract_reserves = FloatField(null=True, help_text="提取保险责任准备金净额")  # 提取保险责任准备金净额
    policyholder_dividend_expense = FloatField(null=True, help_text="保单红利支出")  # 保单红利支出
    reinsurance_expense = FloatField(null=True, help_text="分保费用")  # 分保费用
    taxes_and_surcharges = FloatField(null=True, help_text="税金及附加")  # 税金及附加
    selling_expenses = FloatField(null=True, help_text="销售费用")  # 销售费用
    administrative_expenses = FloatField(null=True, help_text="管理费用")  # 管理费用
    research_and_development_expenses = FloatField(null=True, help_text="研发费用")  # 研发费用
    financial_expenses = FloatField(null=True, help_text="财务费用")  # 财务费用
    interest_expense_detail = FloatField(null=True, help_text="其中：利息费用")  # 其中：利息费用
    interest_income_detail = FloatField(null=True, help_text="利息收入")  # 利息收入

    # 其他收益与损益
    other_income = FloatField(null=True, help_text="加：其他收益")  # 加：其他收益
    investment_income = FloatField(null=True, help_text="投资收益")  # 投资收益
    investment_income_from_associates = FloatField(null=True, help_text="其中：对联营企业和合营企业的投资收益")  # 其中：对联营企业和合营企业的投资收益
    financial_asset_derecognition_income = FloatField(null=True, help_text="以摊余成本计量的金融资产终止确认收益")  # 以摊余成本计量的金融资产终止确认收益
    exchange_gains = FloatField(null=True, help_text="汇兑收益")  # 汇兑收益
    net_hedge_gain = FloatField(null=True, help_text="净敞口套期收益")  # 净敞口套期收益
    fair_value_change_income = FloatField(null=True, help_text="公允价值变动收益")  # 公允价值变动收益
    credit_impairment_loss = FloatField(null=True, help_text="信用减值损失")  # 信用减值损失
    asset_impairment_loss = FloatField(null=True, help_text="资产减值损失")  # 资产减值损失
    asset_disposal_income = FloatField(null=True, help_text="资产处置收益")  # 资产处置收益
    operating_profit = FloatField(null=True, help_text="三、营业利润")  # 三、营业利润
    non_operating_income = FloatField(null=True, help_text="加：营业外收入")  # 加：营业外收入
    non_operating_expenses = FloatField(null=True, help_text="减：营业外支出")  # 减：营业外支出
    total_profit = FloatField(null=True, help_text="四、利润总额")  # 四、利润总额
    income_tax_expense = FloatField(null=True, help_text="减：所得税费用")  # 减：所得税费用
    net_profit = FloatField(null=True, help_text="五、净利润")  # 五、净利润

    # 按经营持续性分类
    continuing_operation_net_profit = FloatField(null=True, help_text="1.持续经营净利润")  # 1.持续经营净利润
    discontinued_operation_net_profit = FloatField(null=True, help_text="2.终止经营净利润")  # 2.终止经营净利润

    # 按所有权归属分类
    net_profit_attributable_to_parent = FloatField(null=True, help_text="1.归属于母公司股东的净利润")  # 1.归属于母公司股东的净利润
    minority_interest_net_profit = FloatField(null=True, help_text="2.少数股东损益")  # 2.少数股东损益

    # 其他综合收益
    other_comprehensive_income_after_tax = FloatField(null=True, help_text="六、其他综合收益的税后净额")  # 六、其他综合收益的税后净额
    other_comprehensive_income_attributable_to_parent = FloatField(null=True, help_text="（一）归属母公司所有者的其他综合收益的税后净额")  # （一）归属母公司所有者的其他综合收益的税后净额
    oci_not_recognized_in_profit = FloatField(null=True, help_text="1．不能重分类进损益的其他综合收益")  # 1．不能重分类进损益的其他综合收益
    defined_benefit_plan_change = FloatField(null=True, help_text="（1）重新计量设定受益计划变动额")  # （1）重新计量设定受益计划变动额
    equity_method_oci_not_transfer = FloatField(null=True, help_text="（2）权益法下不能转损益的其他综合收益")  # （2）权益法下不能转损益的其他综合收益
    other_equity_instrument_fv_change = FloatField(null=True, help_text="（3）其他权益工具投资公允价值变动")  # （3）其他权益工具投资公允价值变动
    entity_credit_risk_fv_change = FloatField(null=True, help_text="（4）企业自身信用风险公允价值变动")  # （4）企业自身信用风险公允价值变动
    oci_recognized_in_profit = FloatField(null=True, help_text="2．将重分类进损益的其他综合收益")  # 2．将重分类进损益的其他综合收益
    equity_method_oci_transfer = FloatField(null=True, help_text="（1）权益法下可转损益的其他综合收益")  # （1）权益法下可转损益的其他综合收益
    other_debt_investment_fv_change = FloatField(null=True, help_text="（2）其他债权投资公允价值变动")  # （2）其他债权投资公允价值变动
    financial_asset_reclassification_oci = FloatField(null=True, help_text="（3）金融资产重分类计入其他综合收益的金额")  # （3）金融资产重分类计入其他综合收益的金额
    other_debt_investment_impairment = FloatField(null=True, help_text="（4）其他债权投资信用减值准备")  # （4）其他债权投资信用减值准备
    cash_flow_hedge_reserve = FloatField(null=True, help_text="（5）现金流量套期储备")  # （5）现金流量套期储备
    foreign_currency_translation = FloatField(null=True, help_text="（6）外币财务报表折算差额")  # （6）外币财务报表折算差额
    other_oci = FloatField(null=True, help_text="（7）其他")  # （7）其他
    oci_attributable_to_minority = FloatField(null=True, help_text="（二）归属于少数股东的其他综合收益的税后净额")  # （二）归属于少数股东的其他综合收益的税后净额

    # 综合收益与每股收益
    total_comprehensive_income = FloatField(null=True, help_text="七、综合收益总额")  # 七、综合收益总额
    comprehensive_income_attributable_to_parent = FloatField(null=True, help_text="（一）归属于母公司所有者的综合收益总额")  # （一）归属于母公司所有者的综合收益总额
    comprehensive_income_attributable_to_minority = FloatField(null=True, help_text="（二）归属于少数股东的综合收益总额")  # （二）归属于少数股东的综合收益总额
    basic_eps = FloatField(null=True, help_text="（一）基本每股收益(元/股)")  # （一）基本每股收益
    diluted_eps = FloatField(null=True, help_text="（二）稀释每股收益(元/股)")  # （二）稀释每股收益

    class Meta:
        database = db
        table_name = 'consolidated_income_statement'


class ParentCompanyIncomeStatement(Model):
    """
    母公司利润表 ORM 模型
    用于存储母公司利润表的所有财务指标
    """
    id = AutoField(primary_key=True)
    company_name = CharField(max_length=255, null=False, index=True)
    stock_code = CharField(max_length=20, null=False, index=True)
    report_year = IntegerField(null=False, index=True)
    report_period = CharField(max_length=10, null=False, index=True)

    # 营业收入与成本
    operating_revenue = FloatField(null=True, help_text="一、营业收入")  # 一、营业收入
    operating_costs = FloatField(null=True, help_text="减：营业成本")  # 减：营业成本
    taxes_and_surcharges = FloatField(null=True, help_text="税金及附加")  # 税金及附加
    selling_expenses = FloatField(null=True, help_text="销售费用")  # 销售费用
    administrative_expenses = FloatField(null=True, help_text="管理费用")  # 管理费用
    research_and_development_expenses = FloatField(null=True, help_text="研发费用")  # 研发费用
    financial_expenses = FloatField(null=True, help_text="财务费用")  # 财务费用
    interest_expense = FloatField(null=True, help_text="其中：利息费用")  # 其中：利息费用
    interest_income = FloatField(null=True, help_text="利息收入")  # 利息收入

    # 其他收益与损益
    other_income = FloatField(null=True, help_text="加：其他收益")  # 加：其他收益
    investment_income = FloatField(null=True, help_text="投资收益")  # 投资收益
    investment_income_from_associates = FloatField(null=True, help_text="其中：对联营企业和合营企业的投资收益")  # 其中：对联营企业和合营企业的投资收益
    financial_asset_derecognition_income = FloatField(null=True, help_text="以摊余成本计量的金融资产终止确认收益")  # 以摊余成本计量的金融资产终止确认收益
    net_hedge_gain = FloatField(null=True, help_text="净敞口套期收益")  # 净敞口套期收益
    fair_value_change_income = FloatField(null=True, help_text="公允价值变动收益")  # 公允价值变动收益
    credit_impairment_loss = FloatField(null=True, help_text="信用减值损失")  # 信用减值损失
    asset_impairment_loss = FloatField(null=True, help_text="资产减值损失")  # 资产减值损失
    asset_disposal_income = FloatField(null=True, help_text="资产处置收益")  # 资产处置收益
    operating_profit = FloatField(null=True, help_text="二、营业利润")  # 二、营业利润
    non_operating_income = FloatField(null=True, help_text="加：营业外收入")  # 加：营业外收入
    non_operating_expenses = FloatField(null=True, help_text="减：营业外支出")  # 减：营业外支出
    total_profit = FloatField(null=True, help_text="三、利润总额")  # 三、利润总额
    income_tax_expense = FloatField(null=True, help_text="减：所得税费用")  # 减：所得税费用
    net_profit = FloatField(null=True, help_text="四、净利润")  # 四、净利润
    continuing_operation_net_profit = FloatField(null=True, help_text="（一）持续经营净利润")  # （一）持续经营净利润
    discontinued_operation_net_profit = FloatField(null=True, help_text="（二）终止经营净利润")  # （二）终止经营净利润

    # 其他综合收益
    other_comprehensive_income_after_tax = FloatField(null=True, help_text="五、其他综合收益的税后净额")  # 五、其他综合收益的税后净额
    oci_not_recognized_in_profit = FloatField(null=True, help_text="（一）不能重分类进损益的其他综合收益")  # （一）不能重分类进损益的其他综合收益
    defined_benefit_plan_change = FloatField(null=True, help_text="1.重新计量设定受益计划变动额")  # 1.重新计量设定受益计划变动额
    equity_method_oci_not_transfer = FloatField(null=True, help_text="2.权益法下不能转损益的其他综合收益")  # 2.权益法下不能转损益的其他综合收益
    other_equity_instrument_fv_change = FloatField(null=True, help_text="3.其他权益工具投资公允价值变动")  # 3.其他权益工具投资公允价值变动
    entity_credit_risk_fv_change = FloatField(null=True, help_text="4.企业自身信用风险公允价值变动")  # 4.企业自身信用风险公允价值变动
    oci_recognized_in_profit = FloatField(null=True, help_text="（二）将重分类进损益的其他综合收益")  # （二）将重分类进损益的其他综合收益
    equity_method_oci_transfer = FloatField(null=True, help_text="1.权益法下可转损益的其他综合收益")  # 1.权益法下可转损益的其他综合收益
    other_debt_investment_fv_change = FloatField(null=True, help_text="2.其他债权投资公允价值变动")  # 2.其他债权投资公允价值变动
    financial_asset_reclassification_oci = FloatField(null=True, help_text="3.金融资产重分类计入其他综合收益的金额")  # 3.金融资产重分类计入其他综合收益的金额
    other_debt_investment_impairment = FloatField(null=True, help_text="4.其他债权投资信用减值准备")  # 4.其他债权投资信用减值准备
    cash_flow_hedge_reserve = FloatField(null=True, help_text="5.现金流量套期储备")  # 5.现金流量套期储备
    foreign_currency_translation = FloatField(null=True, help_text="6.外币财务报表折算差额")  # 6.外币财务报表折算差额
    other_oci = FloatField(null=True, help_text="7.其他")  # 7.其他
    total_comprehensive_income = FloatField(null=True, help_text="六、综合收益总额")  # 六、综合收益总额
    basic_eps = FloatField(null=True, help_text="（一）基本每股收益(元/股)")  # （一）基本每股收益
    diluted_eps = FloatField(null=True, help_text="（二）稀释每股收益(元/股)")  # （二）稀释每股收益

    class Meta:
        database = db
        table_name = 'parent_company_income_statement'


class ConsolidatedCashFlowStatement(Model):
    """
    合并现金流量表 ORM 模型
    用于存储合并现金流量表的所有财务指标
    """
    id = AutoField(primary_key=True)
    company_name = CharField(max_length=255, null=False, index=True)
    stock_code = CharField(max_length=20, null=False, index=True)
    report_year = IntegerField(null=False, index=True)
    report_period = CharField(max_length=10, null=False, index=True)

    # 经营活动产生的现金流量
    cash_from_sales = FloatField(null=True, help_text="销售商品、提供劳务收到的现金")  # 销售商品、提供劳务收到的现金
    deposit_from_customers = FloatField(null=True, help_text="客户存款和同业存放款项净增加额")  # 客户存款和同业存放款项净增加额
    borrowing_from_central_bank = FloatField(null=True, help_text="向中央银行借款净增加额")  # 向中央银行借款净增加额
    borrowing_from_financial_institutions = FloatField(null=True, help_text="向其他金融机构拆入资金净增加额")  # 向其他金融机构拆入资金净增加额
    premium_from_insurance = FloatField(null=True, help_text="收到原保险合同保费取得的现金")  # 收到原保险合同保费取得的现金
    net_cash_from_reinsurance = FloatField(null=True, help_text="收到再保业务现金净额")  # 收到再保业务现金净额
    policyholder_deposits = FloatField(null=True, help_text="保户储金及投资款净增加额")  # 保户储金及投资款净增加额
    interest_and_commission_received = FloatField(null=True, help_text="收取利息、手续费及佣金的现金")  # 收取利息、手续费及佣金的现金
    borrowed_funds = FloatField(null=True, help_text="拆入资金净增加额")  # 拆入资金净增加额
    repurchase_agreement_funds = FloatField(null=True, help_text="回购业务资金净增加额")  # 回购业务资金净增加额
    net_cash_from_securities_trading = FloatField(null=True, help_text="代理买卖证券收到的现金净额")  # 代理买卖证券收到的现金净额
    tax_refund = FloatField(null=True, help_text="收到的税费返还")  # 收到的税费返还
    other_cash_from_operations = FloatField(null=True, help_text="收到其他与经营活动有关的现金")  # 收到其他与经营活动有关的现金
    operating_cash_inflows = FloatField(null=True, help_text="经营活动现金流入小计")  # 经营活动现金流入小计
    cash_for_goods = FloatField(null=True, help_text="购买商品、接受劳务支付的现金")  # 购买商品、接受劳务支付的现金
    loans_to_customers = FloatField(null=True, help_text="客户贷款及垫款净增加额")  # 客户贷款及垫款净增加额
    deposits_with_central_bank = FloatField(null=True, help_text="存放中央银行和同业款项净增加额")  # 存放中央银行和同业款项净增加额
    cash_for_claims = FloatField(null=True, help_text="支付原保险合同赔付款项的现金")  # 支付原保险合同赔付款项的现金
    lending_funds = FloatField(null=True, help_text="拆出资金净增加额")  # 拆出资金净增加额
    interest_and_commission_paid = FloatField(null=True, help_text="支付利息、手续费及佣金的现金")  # 支付利息、手续费及佣金的现金
    policyholder_dividend_paid = FloatField(null=True, help_text="支付保单红利的现金")  # 支付保单红利的现金
    cash_to_employees = FloatField(null=True, help_text="支付给职工及为职工支付的现金")  # 支付给职工及为职工支付的现金
    taxes_paid = FloatField(null=True, help_text="支付的各项税费")  # 支付的各项税费
    other_cash_for_operations = FloatField(null=True, help_text="支付其他与经营活动有关的现金")  # 支付其他与经营活动有关的现金
    operating_cash_outflows = FloatField(null=True, help_text="经营活动现金流出小计")  # 经营活动现金流出小计
    net_cash_from_operations = FloatField(null=True, help_text="经营活动产生的现金流量净额")  # 经营活动产生的现金流量净额

    # 投资活动产生的现金流量
    cash_from_investment_disposal = FloatField(null=True, help_text="收回投资收到的现金")  # 收回投资收到的现金
    investment_income_received = FloatField(null=True, help_text="取得投资收益收到的现金")  # 取得投资收益收到的现金
    cash_from_fixed_asset_disposal = FloatField(null=True, help_text="处置固定资产、无形资产和其他长期资产收回的现金净额")  # 处置固定资产、无形资产和其他长期资产收回的现金净额
    cash_from_subsidiary_disposal = FloatField(null=True, help_text="处置子公司及其他营业单位收到的现金净额")  # 处置子公司及其他营业单位收到的现金净额
    other_cash_from_investing = FloatField(null=True, help_text="收到其他与投资活动有关的现金")  # 收到其他与投资活动有关的现金
    investing_cash_inflows = FloatField(null=True, help_text="投资活动现金流入小计")  # 投资活动现金流入小计
    cash_for_fixed_assets = FloatField(null=True, help_text="购建固定资产、无形资产和其他长期资产支付的现金")  # 购建固定资产、无形资产和其他长期资产支付的现金
    cash_for_investments = FloatField(null=True, help_text="投资支付的现金")  # 投资支付的现金
    pledged_loans = FloatField(null=True, help_text="质押贷款净增加额")  # 质押贷款净增加额
    cash_for_subsidiary_acquisition = FloatField(null=True, help_text="取得子公司及其他营业单位支付的现金净额")  # 取得子公司及其他营业单位支付的现金净额
    other_cash_for_investing = FloatField(null=True, help_text="支付其他与投资活动有关的现金")  # 支付其他与投资活动有关的现金
    investing_cash_outflows = FloatField(null=True, help_text="投资活动现金流出小计")  # 投资活动现金流出小计
    net_cash_from_investing = FloatField(null=True, help_text="投资活动产生的现金流量净额")  # 投资活动产生的现金流量净额

    # 筹资活动产生的现金流量
    cash_from_capital_contribution = FloatField(null=True, help_text="吸收投资收到的现金")  # 吸收投资收到的现金
    capital_contribution_from_minority = FloatField(null=True, help_text="其中：子公司吸收少数股东投资收到的现金")  # 其中：子公司吸收少数股东投资收到的现金
    cash_from_borrowing = FloatField(null=True, help_text="取得借款收到的现金")  # 取得借款收到的现金
    other_cash_from_financing = FloatField(null=True, help_text="收到其他与筹资活动有关的现金")  # 收到其他与筹资活动有关的现金
    financing_cash_inflows = FloatField(null=True, help_text="筹资活动现金流入小计")  # 筹资活动现金流入小计
    cash_for_debt_repayment = FloatField(null=True, help_text="偿还债务支付的现金")  # 偿还债务支付的现金
    cash_for_dividend_and_interest = FloatField(null=True, help_text="分配股利、利润或偿付利息支付的现金")  # 分配股利、利润或偿付利息支付的现金
    dividend_to_minority = FloatField(null=True, help_text="其中：子公司支付给少数股东的股利、利润")  # 其中：子公司支付给少数股东的股利、利润
    other_cash_for_financing = FloatField(null=True, help_text="支付其他与筹资活动有关的现金")  # 支付其他与筹资活动有关的现金
    financing_cash_outflows = FloatField(null=True, help_text="筹资活动现金流出小计")  # 筹资活动现金流出小计
    net_cash_from_financing = FloatField(null=True, help_text="筹资活动产生的现金流量净额")  # 筹资活动产生的现金流量净额

    # 现金及现金等价物
    exchange_rate_effect = FloatField(null=True, help_text="四、汇率变动对现金及现金等价物的影响")  # 四、汇率变动对现金及现金等价物的影响
    net_increase_in_cash = FloatField(null=True, help_text="五、现金及现金等价物净增加额")  # 五、现金及现金等价物净增加额
    beginning_cash = FloatField(null=True, help_text="加：期初现金及现金等价物余额")  # 加：期初现金及现金等价物余额
    ending_cash = FloatField(null=True, help_text="六、期末现金及现金等价物余额")  # 六、期末现金及现金等价物余额 

    class Meta:
        database = db
        table_name = 'consolidated_cash_flow_statement'


class ParentCompanyCashFlowStatement(Model):
    """
    母公司现金流量表 ORM 模型
    用于存储母公司现金流量表的所有财务指标
    """
    id = AutoField(primary_key=True)
    company_name = CharField(max_length=255, null=False, index=True)
    stock_code = CharField(max_length=20, null=False, index=True)
    report_year = IntegerField(null=False, index=True)
    report_period = CharField(max_length=10, null=False, index=True)

    # 经营活动产生的现金流量
    cash_from_sales = FloatField(null=True, help_text="销售商品、提供劳务收到的现金")  # 销售商品、提供劳务收到的现金
    tax_refund = FloatField(null=True, help_text="收到的税费返还")  # 收到的税费返还
    other_cash_from_operations = FloatField(null=True, help_text="收到其他与经营活动有关的现金")  # 收到其他与经营活动有关的现金
    operating_cash_inflows = FloatField(null=True, help_text="经营活动现金流入小计")  # 经营活动现金流入小计
    cash_for_goods = FloatField(null=True, help_text="购买商品、接受劳务支付的现金")  # 购买商品、接受劳务支付的现金
    cash_to_employees = FloatField(null=True, help_text="支付给职工及为职工支付的现金")  # 支付给职工及为职工支付的现金
    taxes_paid = FloatField(null=True, help_text="支付的各项税费")  # 支付的各项税费
    other_cash_for_operations = FloatField(null=True, help_text="支付其他与经营活动有关的现金")  # 支付其他与经营活动有关的现金
    operating_cash_outflows = FloatField(null=True, help_text="经营活动现金流出小计")  # 经营活动现金流出小计
    net_cash_from_operations = FloatField(null=True, help_text="经营活动产生的现金流量净额")  # 经营活动产生的现金流量净额

    # 投资活动产生的现金流量
    cash_from_investment_disposal = FloatField(null=True, help_text="收回投资收到的现金")  # 收回投资收到的现金
    investment_income_received = FloatField(null=True, help_text="取得投资收益收到的现金")  # 取得投资收益收到的现金
    cash_from_fixed_asset_disposal = FloatField(null=True, help_text="处置固定资产、无形资产和其他长期资产收回的现金净额")  # 处置固定资产、无形资产和其他长期资产收回的现金净额
    cash_from_subsidiary_disposal = FloatField(null=True, help_text="处置子公司及其他营业单位收到的现金净额")  # 处置子公司及其他营业单位收到 the cash net
    other_cash_from_investing = FloatField(null=True, help_text="收到其他与投资活动有关的现金")  # 收到其他与投资活动有关的现金
    investing_cash_inflows = FloatField(null=True, help_text="投资活动现金流入小计")  # 投资活动现金流入小计
    cash_for_fixed_assets = FloatField(null=True, help_text="购建固定资产、无形资产和其他长期资产支付的现金")  # 购建固定资产、无形资产和其他长期资产支付的现金
    cash_for_investments = FloatField(null=True, help_text="投资支付的现金")  # 投资支付的现金
    cash_for_subsidiary_acquisition = FloatField(null=True, help_text="取得子公司及其他营业单位支付的现金净额")  # 取得子公司及其他营业单位支付的现金净额
    other_cash_for_investing = FloatField(null=True, help_text="支付其他与投资活动有关的现金")  # 支付其他与投资活动有关的现金
    investing_cash_outflows = FloatField(null=True, help_text="投资活动现金流出小计")  # 投资活动现金流出小计
    net_cash_from_investing = FloatField(null=True, help_text="投资活动产生的现金流量净额")  # 投资活动产生的现金流量净额

    # 筹资活动产生的现金流量
    cash_from_capital_contribution = FloatField(null=True, help_text="吸收投资收到的现金")  # 吸收投资收到的现金
    cash_from_borrowing = FloatField(null=True, help_text="取得借款收到的现金")  # 取得借款收到的现金
    other_cash_from_financing = FloatField(null=True, help_text="收到其他与筹资活动有关的现金")  # 收到其他与筹资活动有关的现金
    financing_cash_inflows = FloatField(null=True, help_text="筹资活动现金流入小计")  # 筹资活动现金流入小计
    cash_for_debt_repayment = FloatField(null=True, help_text="偿还债务支付的现金")  # 偿还债务支付的现金
    cash_for_dividend_and_interest = FloatField(null=True, help_text="分配股利、利润或偿付利息支付的现金")  # 分配股利、利润或偿付利息支付的现金
    other_cash_for_financing = FloatField(null=True, help_text="支付其他与筹资活动有关的现金")  # 支付其他与筹资活动有关的现金
    financing_cash_outflows = FloatField(null=True, help_text="筹资活动现金流出小计")  # 筹资活动现金流出小计
    net_cash_from_financing = FloatField(null=True, help_text="筹资活动产生的现金流量净额")  # 筹资活动产生的现金流量净额

    # 现金及现金等价物
    exchange_rate_effect = FloatField(null=True, help_text="四、汇率变动对现金及现金等价物的影响")  # 四、汇率变动对现金及现金等价物的影响
    net_increase_in_cash = FloatField(null=True, help_text="五、现金及现金等价物净增加额")  # 五、现金及现金等价物净增加额
    beginning_cash = FloatField(null=True, help_text="加：期初现金及现金等价物余额")  # 加：期初现金及现金等价物余额
    ending_cash = FloatField(null=True, help_text="六、期末现金及现金等价物余额")  # 六、期末现金及现金等价物余额 

    class Meta:
        database = db
        table_name = 'parent_company_cash_flow_statement'


class ShareStructure(Model):
    """
    股份结构 ORM 模型
    用于记录股份变动情况表中变动后的最新股份情况
    """
    id = AutoField(primary_key=True)
    company_name = CharField(max_length=255, null=False, index=True)
    stock_code = CharField(max_length=20, null=False, index=True)
    report_year = IntegerField(null=False, index=True)
    report_period = CharField(max_length=10, null=False, index=True)

    # 有限售条件股份（变动后）
    restricted_shares = FloatField(null=True, help_text="有限售条件股份数量")
    restricted_shares_ratio = FloatField(null=True, help_text="有限售条件股份比例(%)")
    
    # 有限售条件股份 - 细分
    state_shares = FloatField(null=True, help_text="国家持股数量")
    state_shares_ratio = FloatField(null=True, help_text="国家持股比例(%)")
    state_owned_legal_person_shares = FloatField(null=True, help_text="国有法人持股数量")
    state_owned_legal_person_shares_ratio = FloatField(null=True, help_text="国有法人持股比例(%)")
    other_domestic_shares = FloatField(null=True, help_text="其他内资持股数量")
    other_domestic_shares_ratio = FloatField(null=True, help_text="其他内资持股比例(%)")
    domestic_non_state_owned_legal_person_shares = FloatField(null=True, help_text="境内非国有法人持股数量")
    domestic_non_state_owned_legal_person_shares_ratio = FloatField(null=True, help_text="境内非国有法人持股比例(%)")
    domestic_natural_person_shares = FloatField(null=True, help_text="境内自然人持股数量")
    domestic_natural_person_shares_ratio = FloatField(null=True, help_text="境内自然人持股比例(%)")
    foreign_shares = FloatField(null=True, help_text="外资持股数量")
    foreign_shares_ratio = FloatField(null=True, help_text="外资持股比例(%)")
    foreign_legal_person_shares = FloatField(null=True, help_text="境外法人持股数量")
    foreign_legal_person_shares_ratio = FloatField(null=True, help_text="境外法人持股比例(%)")
    foreign_natural_person_shares = FloatField(null=True, help_text="境外自然人持股数量")
    foreign_natural_person_shares_ratio = FloatField(null=True, help_text="境外自然人持股比例(%)")
    
    # 无限售条件流通股份（变动后）
    unrestricted_shares = FloatField(null=True, help_text="无限售条件流通股份数量")
    unrestricted_shares_ratio = FloatField(null=True, help_text="无限售条件流通股份比例(%)")
    
    # 无限售条件流通股份 - 细分
    rmb_common_shares = FloatField(null=True, help_text="人民币普通股数量")
    rmb_common_shares_ratio = FloatField(null=True, help_text="人民币普通股比例(%)")
    domestic_listed_foreign_shares = FloatField(null=True, help_text="境内上市的外资股数量")
    domestic_listed_foreign_shares_ratio = FloatField(null=True, help_text="境内上市的外资股比例(%)")
    foreign_listed_foreign_shares = FloatField(null=True, help_text="境外上市的外资股数量")
    foreign_listed_foreign_shares_ratio = FloatField(null=True, help_text="境外上市的外资股比例(%)")
    other_shares = FloatField(null=True, help_text="其他股份数量")
    other_shares_ratio = FloatField(null=True, help_text="其他股份比例(%)")
    
    # 股份总数（变动后）
    total_shares = FloatField(null=True, help_text="股份总数")
    total_shares_ratio = FloatField(null=True, help_text="股份总数比例(%)")

    class Meta:
        database = db
        table_name = 'share_structure'

# --- 2. Pydantic V2 Models (用于结构化输出提取) ---

class MetricItem(BaseModel):
    """
    单条指标的提取定义
    用于LLM结构化输出，包含指标的数值、单位、上下文和页码信息
    """
    value: float = Field(..., description="指标的具体数值")  # 指标的浮点数值
    unit: str = Field(default="元", description="数值单位，如：元、万元、亿元、%")  # 数值的计量单位，默认为"元"
    context: str = Field(..., description="数据所在的原文句子或表格行内容，用于溯源")  # 原始数据的上下文，用于验证和溯源
    page: int = Field(..., description="数据来源的页码")  # 数据在PDF中的页码位置

class FinancialExtractionSchema(BaseModel):
    """
    LLM 结构化提取 Schema
    定义了LLM从财务报告中提取结构化数据的标准格式
    """
    company_name: str = Field(..., description="公司名称")  # 财报所属公司的全名
    report_year: int = Field(..., description="财报所属年份")  # 财报报告的年份
    report_period: ReportPeriod = Field(
        ..., 
        description="财报周期：Q1(一季报), H1(半年报), Q3(三季报), FY(年报)"
    )  # 财报的发布周期，与年份共同确定具体的财务报告期
    
    # 核心财务指标
    operating_revenue: MetricItem = Field(..., description="营业收入")  # 公司主营业务产生的收入总额
    net_profit: MetricItem = Field(..., description="归属于上市公司股东的净利润")  # 扣除所有成本费用和税项后的净利润
    gross_margin: MetricItem = Field(..., description="毛利率")  # 毛利润与营业收入的比率，反映公司盈利能力
    profit_margin: MetricItem = Field(..., description="净利润率")  # 净利润与营业收入的比率，反映公司盈利水平
    roe: MetricItem = Field(..., description="加权平均净资产收益率 (ROE)")  # 净利润与净资产的比率，衡量股东权益的回报率

    @field_validator('gross_margin', 'profit_margin', 'roe', mode='before')
    @classmethod
    def handle_percentage_strings(cls, v):
        """
        处理 LLM 可能返回的带百分号的字符串 (如 "25.5%") 
        或者将 0.255 统一格式化为百分比数值。
        """
        if isinstance(v, dict) and 'value' in v:
            val = v['value']
            if isinstance(val, str) and '%' in val:
                try:
                    v['value'] = float(val.replace('%', ''))
                    v['unit'] = '%'
                except ValueError:
                    pass
        return v
