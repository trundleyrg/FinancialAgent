"""
数据库 ORM 模型及 Pydantic 数据验证
"""    
from typing import Optional, List
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship
from pydantic import BaseModel, Field, field_validator

Base = declarative_base()

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

class FinancialReport(Base):
    """
    财务报告 ORM 模型
    用于存储财务报告的基本元数据信息
    """
    __tablename__ = 'financial_reports'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # 报告唯一标识符，自增主键
    company_name = Column(String(255), nullable=False, index=True)  # 公司全名，用于查询索引
    stock_code = Column(String(20), nullable=False, index=True)  # 股票代码，用于查询索引
    
    # 年份 + 周期 共同定义时间点
    report_year = Column(Integer, nullable=False, index=True)  # 报告所属年份，如2023，用于查询索引
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)  # 报告周期（Q1/H1/Q3/FY），用于查询索引
    
    shares_total = Column(Float, nullable=False)  # 股份总数

    source_file = Column(String(500))  # 源PDF文件路径，用于追溯原始数据
    created_at = Column(DateTime, default=datetime.now)  # 记录创建时间，自动填充当前时间
    metrics = relationship("FinancialMetric", back_populates="report")  # 关联的财务指标列表

class FinancialMetric(Base):
    """
    财务指标 ORM 模型
    用于存储从财务报告中提取的具体财务数据指标
    """
    __tablename__ = 'financial_metrics'
    id = Column(Integer, primary_key=True, autoincrement=True)  # 指标唯一标识符，自增主键
    report_id = Column(Integer, ForeignKey('financial_reports.id'))  # 外键，关联到财务报告
    metric_name = Column(String(100), nullable=False)  # 指标名称，如"营业收入"、"净利润"等
    value = Column(Float, nullable=False)  # 指标的具体数值
    unit = Column(String(20))  # 数值单位，如"元"、"万元"、"%"等
    period = Column(String(50))  # 报告期间，如"年度"、"季度"等
    source_context = Column(Text)  # 指标在原报告中的上下文内容，用于溯源验证
    page_number = Column(Integer)  # 指标在原报告中的页码位置
    report = relationship("FinancialReport", back_populates="metrics")  # 关联回财务报告


class ConsolidatedBalanceSheet(Base):
    """
    合并资产负债表 ORM 模型
    用于存储合并资产负债表的所有财务指标
    """
    __tablename__ = 'consolidated_balance_sheet'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)

    # 流动资产
    monetary_funds = Column(Float, comment="货币资金")  # 货币资金
    reserve_for_settlement = Column(Float, comment="结算备付金")  # 结算备付金
    funds_lent_out = Column(Float, comment="拆出资金")  # 拆出资金
    trading_financial_assets = Column(Float, comment="交易性金融资产")  # 交易性金融资产
    derivative_financial_assets = Column(Float, comment="衍生金融资产")  # 衍生金融资产
    notes_receivable = Column(Float, comment="应收票据")  # 应收票据
    accounts_receivable = Column(Float, comment="应收账款")  # 应收账款
    financing_receivables = Column(Float, comment="应收款项融资")  # 应收款项融资
    prepayments = Column(Float, comment="预付款项")  # 预付款项
    premiums_receivable = Column(Float, comment="应收保费")  # 应收保费
    reinsurance_receivables = Column(Float, comment="应收分保账款")  # 应收分保账款
    reinsurance_contract_reserves_receivable = Column(Float, comment="应收分保合同准备金")  # 应收分保合同准备金
    other_receivables = Column(Float, comment="其他应收款")  # 其他应收款
    interest_receivable = Column(Float, comment="其中：应收利息")  # 其中：应收利息
    dividend_receivable = Column(Float, comment="应收股利")  # 应收股利
    buy_back_securities_financial_assets = Column(Float, comment="买入返售金融资产")  # 买入返售金融资产
    inventory = Column(Float, comment="存货")  # 存货
    data_resources_inventory = Column(Float, comment="其中：数据资源")  # 其中：数据资源
    contract_assets = Column(Float, comment="合同资产")  # 合同资产
    assets_held_for_sale = Column(Float, comment="持有待售资产")  # 持有待售资产
    non_current_assets_due_within_one_year = Column(Float, comment="一年内到期的非流动资产")  # 一年内到期的非流动资产
    other_current_assets = Column(Float, comment="其他流动资产")  # 其他流动资产
    total_current_assets = Column(Float, comment="流动资产合计")  # 流动资产合计

    # 非流动资产
    loans_and_advances_granted = Column(Float, comment="发放贷款和垫款")  # 发放贷款和垫款
    debt_investments = Column(Float, comment="债权投资")  # 债权投资
    other_debt_investments = Column(Float, comment="其他债权投资")  # 其他债权投资
    long_term_receivables = Column(Float, comment="长期应收款")  # 长期应收款
    long_term_equity_investments = Column(Float, comment="长期股权投资")  # 长期股权投资
    other_equity_instrument_investments = Column(Float, comment="其他权益工具投资")  # 其他权益工具投资
    other_non_current_financial_assets = Column(Float, comment="其他非流动金融资产")  # 其他非流动金融资产
    investment_real_estate = Column(Float, comment="投资性房地产")  # 投资性房地产
    fixed_assets = Column(Float, comment="固定资产")  # 固定资产
    construction_in_progress = Column(Float, comment="在建工程")  # 在建工程
    productive_biological_assets = Column(Float, comment="生产性生物资产")  # 生产性生物资产
    oil_and_gas_assets = Column(Float, comment="油气资产")  # 油气资产
    right_of_use_assets = Column(Float, comment="使用权资产")  # 使用权资产
    intangible_assets = Column(Float, comment="无形资产")  # 无形资产
    data_resources_intangible = Column(Float, comment="其中：数据资源（无形资产）")  # 其中：数据资源
    development_expenditure = Column(Float, comment="开发支出")  # 开发支出
    data_resources_development = Column(Float, comment="其中：数据资源（开发支出）")  # 其中：数据资源
    goodwill = Column(Float, comment="商誉")  # 商誉
    long_term_prepaid_expenses = Column(Float, comment="长期待摊费用")  # 长期待摊费用
    deferred_tax_assets = Column(Float, comment="递延所得税资产")  # 递延所得税资产
    other_non_current_assets = Column(Float, comment="其他非流动资产")  # 其他非流动资产
    total_non_current_assets = Column(Float, comment="非流动资产合计")  # 非流动资产合计
    total_assets = Column(Float, comment="资产总计")  # 资产总计

    # 流动负债
    short_term_borrowings = Column(Float, comment="短期借款")  # 短期借款
    borrowings_from_central_bank = Column(Float, comment="向中央银行借款")  # 向中央银行借款
    funds_borrowed = Column(Float, comment="拆入资金")  # 拆入资金
    trading_financial_liabilities = Column(Float, comment="交易性金融负债")  # 交易性金融负债
    derivative_financial_liabilities = Column(Float, comment="衍生金融负债")  # 衍生金融负债
    notes_payable = Column(Float, comment="应付票据")  # 应付票据
    accounts_payable = Column(Float, comment="应付账款")  # 应付账款
    advance_from_customers = Column(Float, comment="预收款项")  # 预收款项
    contract_liabilities = Column(Float, comment="合同负债")  # 合同负债
    sell_repurchase_securities_funds = Column(Float, comment="卖出回购金融资产款")  # 卖出回购金融资产款
    deposits_and_interbank_placement = Column(Float, comment="吸收存款及同业存放")  # 吸收存款及同业存放
    proxy_trading_securities_funds = Column(Float, comment="代理买卖证券款")  # 代理买卖证券款
    proxy_underwriting_securities_funds = Column(Float, comment="代理承销证券款")  # 代理承销证券款
    employee_benefits_payable = Column(Float, comment="应付职工薪酬")  # 应付职工薪酬
    taxes_payable = Column(Float, comment="应交税费")  # 应交税费
    other_payables = Column(Float, comment="其他应付款")  # 其他应付款
    interest_payable = Column(Float, comment="其中：应付利息")  # 其中：应付利息
    dividend_payable = Column(Float, comment="应付股利")  # 应付股利
    commission_and_brokerage_payable = Column(Float, comment="应付手续费及佣金")  # 应付手续费及佣金
    reinsurance_payables = Column(Float, comment="应付分保账款")  # 应付分保账款
    liabilities_held_for_sale = Column(Float, comment="持有待售负债")  # 持有待售负债
    non_current_liabilities_due_within_one_year = Column(Float, comment="一年内到期的非流动负债")  # 一年内到期的非流动负债
    other_current_liabilities = Column(Float, comment="其他流动负债")  # 其他流动负债
    total_current_liabilities = Column(Float, comment="流动负债合计")  # 流动负债合计

    # 非流动负债
    insurance_contract_reserves = Column(Float, comment="保险合同准备金")  # 保险合同准备金
    long_term_borrowings = Column(Float, comment="长期借款")  # 长期借款
    bonds_payable = Column(Float, comment="应付债券")  # 应付债券
    preferred_stock_bonds = Column(Float, comment="其中：优先股")  # 其中：优先股
    perpetual_bonds = Column(Float, comment="永续债")  # 永续债
    lease_liabilities = Column(Float, comment="租赁负债")  # 租赁负债
    long_term_payables = Column(Float, comment="长期应付款")  # 长期应付款
    long_term_employee_benefits_payable = Column(Float, comment="长期应付职工薪酬")  # 长期应付职工薪酬
    estimated_liabilities = Column(Float, comment="预计负债")  # 预计负债
    deferred_income = Column(Float, comment="递延收益")  # 递延收益
    deferred_tax_liabilities = Column(Float, comment="递延所得税负债")  # 递延所得税负债
    other_non_current_liabilities = Column(Float, comment="其他非流动负债")  # 其他非流动负债
    total_non_current_liabilities = Column(Float, comment="非流动负债合计")  # 非流动负债合计
    total_liabilities = Column(Float, comment="负债合计")  # 负债合计

    # 所有者权益
    paid_in_capital = Column(Float, comment="实收资本（或股本）")  # 实收资本（或股本）
    other_equity_instruments = Column(Float, comment="其他权益工具")  # 其他权益工具
    preferred_stock_equity = Column(Float, comment="其中：优先股（权益）")  # 其中：优先股
    perpetual_bonds_equity = Column(Float, comment="永续债（权益）")  # 永续债
    capital_reserve = Column(Float, comment="资本公积")  # 资本公积
    treasury_stock = Column(Float, comment="减：库存股")  # 减：库存股
    other_comprehensive_income = Column(Float, comment="其他综合收益")  # 其他综合收益
    special_reserve = Column(Float, comment="专项储备")  # 专项储备
    surplus_reserve = Column(Float, comment="盈余公积")  # 盈余公积
    general_risk_reserve = Column(Float, comment="一般风险准备")  # 一般风险准备
    retained_earnings = Column(Float, comment="未分配利润")  # 未分配利润
    total_equity_attributable_to_parent_company = Column(Float, comment="归属于母公司所有者权益（或股东权益）合计")  # 归属于母公司所有者权益（或股东权益）合计
    minority_interest = Column(Float, comment="少数股东权益")  # 少数股东权益
    total_owners_equity = Column(Float, comment="所有者权益（或股东权益）合计")  # 所有者权益（或股东权益）合计
    total_liabilities_and_owners_equity = Column(Float, comment="负债和所有者权益（或股东权益）总计")  # 负债和所有者权益（或股东权益）总计


class ParentCompanyBalanceSheet(Base):
    """
    母公司资产负债表 ORM 模型
    用于存储母公司资产负债表的所有财务指标
    """
    __tablename__ = 'parent_company_balance_sheet'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)

    # 流动资产
    monetary_funds = Column(Float, comment="货币资金")  # 货币资金
    trading_financial_assets = Column(Float, comment="交易性金融资产")  # 交易性金融资产
    derivative_financial_assets = Column(Float, comment="衍生金融资产")  # 衍生金融资产
    notes_receivable = Column(Float, comment="应收票据")  # 应收票据
    accounts_receivable = Column(Float, comment="应收账款")  # 应收账款
    financing_receivables = Column(Float, comment="应收款项融资")  # 应收款项融资
    prepayments = Column(Float, comment="预付款项")  # 预付款项
    other_receivables = Column(Float, comment="其他应收款")  # 其他应收款
    interest_receivable = Column(Float, comment="其中：应收利息")  # 其中：应收利息
    dividend_receivable = Column(Float, comment="应收股利")  # 应收股利
    inventory = Column(Float, comment="存货")  # 存货
    data_resources_inventory = Column(Float, comment="其中：数据资源")  # 其中：数据资源
    contract_assets = Column(Float, comment="合同资产")  # 合同资产
    assets_held_for_sale = Column(Float, comment="持有待售资产")  # 持有待售资产
    non_current_assets_due_within_one_year = Column(Float, comment="一年内到期的非流动资产")  # 一年内到期的非流动资产
    other_current_assets = Column(Float, comment="其他流动资产")  # 其他流动资产
    total_current_assets = Column(Float, comment="流动资产合计")  # 流动资产合计

    # 非流动资产
    debt_investments = Column(Float, comment="债权投资")  # 债权投资
    other_debt_investments = Column(Float, comment="其他债权投资")  # 其他债权投资
    long_term_receivables = Column(Float, comment="长期应收款")  # 长期应收款
    long_term_equity_investments = Column(Float, comment="长期股权投资")  # 长期股权投资
    other_equity_instrument_investments = Column(Float, comment="其他权益工具投资")  # 其他权益工具投资
    other_non_current_financial_assets = Column(Float, comment="其他非流动金融资产")  # 其他非流动金融资产
    investment_real_estate = Column(Float, comment="投资性房地产")  # 投资性房地产
    fixed_assets = Column(Float, comment="固定资产")  # 固定资产
    construction_in_progress = Column(Float, comment="在建工程")  # 在建工程
    productive_biological_assets = Column(Float, comment="生产性生物资产")  # 生产性生物资产
    oil_and_gas_assets = Column(Float, comment="油气资产")  # 油气资产
    right_of_use_assets = Column(Float, comment="使用权资产")  # 使用权资产
    intangible_assets = Column(Float, comment="无形资产")  # 无形资产
    data_resources_intangible = Column(Float, comment="其中：数据资源")  # 其中：数据资源
    development_expenditure = Column(Float, comment="开发支出")  # 开发支出
    data_resources_development = Column(Float, comment="其中：数据资源")  # 其中：数据资源
    goodwill = Column(Float, comment="商誉")  # 商誉
    long_term_prepaid_expenses = Column(Float, comment="长期待摊费用")  # 长期待摊费用
    deferred_tax_assets = Column(Float, comment="递延所得税资产")  # 递延所得税资产
    other_non_current_assets = Column(Float, comment="其他非流动资产")  # 其他非流动资产
    total_non_current_assets = Column(Float, comment="非流动资产合计")  # 非流动资产合计
    total_assets = Column(Float, comment="资产总计")  # 资产总计

    # 流动负债
    short_term_borrowings = Column(Float, comment="短期借款")  # 短期借款
    trading_financial_liabilities = Column(Float, comment="交易性金融负债")  # 交易性金融负债
    derivative_financial_liabilities = Column(Float, comment="衍生金融负债")  # 衍生金融负债
    notes_payable = Column(Float, comment="应付票据")  # 应付票据
    accounts_payable = Column(Float, comment="应付账款")  # 应付账款
    advance_from_customers = Column(Float, comment="预收款项")  # 预收款项
    contract_liabilities = Column(Float, comment="合同负债")  # 合同负债
    employee_benefits_payable = Column(Float, comment="应付职工薪酬")  # 应付职工薪酬
    taxes_payable = Column(Float, comment="应交税费")  # 应交税费
    other_payables = Column(Float, comment="其他应付款")  # 其他应付款
    interest_payable = Column(Float, comment="其中：应付利息")  # 其中：应付利息
    dividend_payable = Column(Float, comment="应付股利")  # 应付股利
    liabilities_held_for_sale = Column(Float, comment="持有待售负债")  # 持有待售负债
    non_current_liabilities_due_within_one_year = Column(Float, comment="一年内到期的非流动负债")  # 一年内到期的非流动负债
    other_current_liabilities = Column(Float, comment="其他流动负债")  # 其他流动负债
    total_current_liabilities = Column(Float, comment="流动负债合计")  # 流动负债合计

    # 非流动负债
    long_term_borrowings = Column(Float, comment="长期借款")  # 长期借款
    bonds_payable = Column(Float, comment="应付债券")  # 应付债券
    preferred_stock_bonds = Column(Float, comment="其中：优先股")  # 其中：优先股
    perpetual_bonds = Column(Float, comment="永续债")  # 永续债
    lease_liabilities = Column(Float, comment="租赁负债")  # 租赁负债
    long_term_payables = Column(Float, comment="长期应付款")  # 长期应付款
    long_term_employee_benefits_payable = Column(Float, comment="长期应付职工薪酬")  # 长期应付职工薪酬
    estimated_liabilities = Column(Float, comment="预计负债")  # 预计负债
    deferred_income = Column(Float, comment="递延收益")  # 递延收益
    deferred_tax_liabilities = Column(Float, comment="递延所得税负债")  # 递延所得税负债
    other_non_current_liabilities = Column(Float, comment="其他非流动负债")  # 其他非流动负债
    total_non_current_liabilities = Column(Float, comment="非流动负债合计")  # 非流动负债合计
    total_liabilities = Column(Float, comment="负债合计")  # 负债合计

    # 所有者权益
    paid_in_capital = Column(Float, comment="实收资本（或股本）")  # 实收资本（或股本）
    other_equity_instruments = Column(Float, comment="其他权益工具")  # 其他权益工具
    preferred_stock_equity = Column(Float, comment="其中：优先股")  # 其中：优先股
    perpetual_bonds_equity = Column(Float, comment="永续债")  # 永续债
    capital_reserve = Column(Float, comment="资本公积")  # 资本公积
    treasury_stock = Column(Float, comment="减：库存股")  # 减：库存股
    other_comprehensive_income = Column(Float, comment="其他综合收益")  # 其他综合收益
    special_reserve = Column(Float, comment="专项储备")  # 专项储备
    surplus_reserve = Column(Float, comment="盈余公积")  # 盈余公积
    retained_earnings = Column(Float, comment="未分配利润")  # 未分配利润
    total_owners_equity = Column(Float, comment="所有者权益（或股东权益）合计")  # 所有者权益（或股东权益）合计
    total_liabilities_and_owners_equity = Column(Float, comment="负债和所有者权益（或股东权益）总计")  # 负债和所有者权益（或股东权益）总计


class ConsolidatedIncomeStatement(Base):
    """
    合并利润表 ORM 模型
    用于存储合并利润表的所有财务指标
    """
    __tablename__ = 'consolidated_income_statement'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)

    # 营业收入与成本
    total_operating_revenue = Column(Float, comment="一、营业总收入")  # 一、营业总收入
    operating_revenue = Column(Float, comment="其中：营业收入")  # 其中：营业收入
    interest_income = Column(Float, comment="利息收入")  # 利息收入
    earned_premium = Column(Float, comment="已赚保费")  # 已赚保费
    commission_and_fee_income = Column(Float, comment="手续费及佣金收入")  # 手续费及佣金收入
    total_operating_costs = Column(Float, comment="二、营业总成本")  # 二、营业总成本
    operating_costs = Column(Float, comment="其中：营业成本")  # 其中：营业成本
    interest_expense = Column(Float, comment="利息支出")  # 利息支出
    commission_and_fee_expense = Column(Float, comment="手续费及佣金支出")  # 手续费及佣金支出
    surrender_value = Column(Float, comment="退保金")  # 退保金
    claims_expenses_net = Column(Float, comment="赔付支出净额")  # 赔付支出净额
    net_withdrawal_of_insurance_contract_reserves = Column(Float, comment="提取保险责任准备金净额")  # 提取保险责任准备金净额
    policyholder_dividend_expense = Column(Float, comment="保单红利支出")  # 保单红利支出
    reinsurance_expense = Column(Float, comment="分保费用")  # 分保费用
    taxes_and_surcharges = Column(Float, comment="税金及附加")  # 税金及附加
    selling_expenses = Column(Float, comment="销售费用")  # 销售费用
    administrative_expenses = Column(Float, comment="管理费用")  # 管理费用
    research_and_development_expenses = Column(Float, comment="研发费用")  # 研发费用
    financial_expenses = Column(Float, comment="财务费用")  # 财务费用
    interest_expense_detail = Column(Float, comment="其中：利息费用")  # 其中：利息费用
    interest_income_detail = Column(Float, comment="利息收入")  # 利息收入

    # 其他收益与损益
    other_income = Column(Float, comment="加：其他收益")  # 加：其他收益
    investment_income = Column(Float, comment="投资收益（损失以"-"号填列）")  # 投资收益
    investment_income_from_associates = Column(Float, comment="其中：对联营企业和合营企业的投资收益")  # 其中：对联营企业和合营企业的投资收益
    financial_asset_derecognition_income = Column(Float, comment="以摊余成本计量的金融资产终止确认收益")  # 以摊余成本计量的金融资产终止确认收益
    exchange_gains = Column(Float, comment="汇兑收益（损失以"-"号填列）")  # 汇兑收益
    net_hedge_gain = Column(Float, comment="净敞口套期收益（损失以"-"号填列）")  # 净敞口套期收益
    fair_value_change_income = Column(Float, comment="公允价值变动收益（损失以"-"号填列）")  # 公允价值变动收益
    credit_impairment_loss = Column(Float, comment="信用减值损失（损失以"-"号填列）")  # 信用减值损失
    asset_impairment_loss = Column(Float, comment="资产减值损失（损失以"-"号填列）")  # 资产减值损失
    asset_disposal_income = Column(Float, comment="资产处置收益（损失以"-"号填列）")  # 资产处置收益
    operating_profit = Column(Float, comment="三、营业利润（亏损以"-"号填列）")  # 三、营业利润
    non_operating_income = Column(Float, comment="加：营业外收入")  # 加：营业外收入
    non_operating_expenses = Column(Float, comment="减：营业外支出")  # 减：营业外支出
    total_profit = Column(Float, comment="四、利润总额（亏损总额以"-"号填列）")  # 四、利润总额
    income_tax_expense = Column(Float, comment="减：所得税费用")  # 减：所得税费用
    net_profit = Column(Float, comment="五、净利润（净亏损以"-"号填列）")  # 五、净利润

    # 按经营持续性分类
    continuing_operation_net_profit = Column(Float, comment="1.持续经营净利润（净亏损以"-"号填列）")  # 1.持续经营净利润
    discontinued_operation_net_profit = Column(Float, comment="2.终止经营净利润（净亏损以"-"号填列）")  # 2.终止经营净利润

    # 按所有权归属分类
    net_profit_attributable_to_parent = Column(Float, comment="1.归属于母公司股东的净利润（净亏损以"-"号填列）")  # 1.归属于母公司股东的净利润
    minority_interest_net_profit = Column(Float, comment="2.少数股东损益（净亏损以"-"号填列）")  # 2.少数股东损益

    # 其他综合收益
    other_comprehensive_income_after_tax = Column(Float, comment="六、其他综合收益的税后净额")  # 六、其他综合收益的税后净额
    other_comprehensive_income_attributable_to_parent = Column(Float, comment="（一）归属母公司所有者的其他综合收益的税后净额")  # （一）归属母公司所有者的其他综合收益的税后净额
    oci_not_recognized_in_profit = Column(Float, comment="1．不能重分类进损益的其他综合收益")  # 1．不能重分类进损益的其他综合收益
    defined_benefit_plan_change = Column(Float, comment="（1）重新计量设定受益计划变动额")  # （1）重新计量设定受益计划变动额
    equity_method_oci_not_transfer = Column(Float, comment="（2）权益法下不能转损益的其他综合收益")  # （2）权益法下不能转损益的其他综合收益
    other_equity_instrument_fv_change = Column(Float, comment="（3）其他权益工具投资公允价值变动")  # （3）其他权益工具投资公允价值变动
    entity_credit_risk_fv_change = Column(Float, comment="（4）企业自身信用风险公允价值变动")  # （4）企业自身信用风险公允价值变动
    oci_recognized_in_profit = Column(Float, comment="2．将重分类进损益的其他综合收益")  # 2．将重分类进损益的其他综合收益
    equity_method_oci_transfer = Column(Float, comment="（1）权益法下可转损益的其他综合收益")  # （1）权益法下可转损益的其他综合收益
    other_debt_investment_fv_change = Column(Float, comment="（2）其他债权投资公允价值变动")  # （2）其他债权投资公允价值变动
    financial_asset_reclassification_oci = Column(Float, comment="（3）金融资产重分类计入其他综合收益的金额")  # （3）金融资产重分类计入其他综合收益的金额
    other_debt_investment_impairment = Column(Float, comment="（4）其他债权投资信用减值准备")  # （4）其他债权投资信用减值准备
    cash_flow_hedge_reserve = Column(Float, comment="（5）现金流量套期储备")  # （5）现金流量套期储备
    foreign_currency_translation = Column(Float, comment="（6）外币财务报表折算差额")  # （6）外币财务报表折算差额
    other_oci = Column(Float, comment="（7）其他")  # （7）其他
    oci_attributable_to_minority = Column(Float, comment="（二）归属于少数股东的其他综合收益的税后净额")  # （二）归属于少数股东的其他综合收益的税后净额

    # 综合收益与每股收益
    total_comprehensive_income = Column(Float, comment="七、综合收益总额")  # 七、综合收益总额
    comprehensive_income_attributable_to_parent = Column(Float, comment="（一）归属于母公司所有者的综合收益总额")  # （一）归属于母公司所有者的综合收益总额
    comprehensive_income_attributable_to_minority = Column(Float, comment="（二）归属于少数股东的综合收益总额")  # （二）归属于少数股东的综合收益总额
    basic_eps = Column(Float, comment="（一）基本每股收益(元/股)")  # （一）基本每股收益
    diluted_eps = Column(Float, comment="（二）稀释每股收益(元/股)")  # （二）稀释每股收益


class ParentCompanyIncomeStatement(Base):
    """
    母公司利润表 ORM 模型
    用于存储母公司利润表的所有财务指标
    """
    __tablename__ = 'parent_company_income_statement'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)

    # 营业收入与成本
    operating_revenue = Column(Float, comment="一、营业收入")  # 一、营业收入
    operating_costs = Column(Float, comment="减：营业成本")  # 减：营业成本
    taxes_and_surcharges = Column(Float, comment="税金及附加")  # 税金及附加
    selling_expenses = Column(Float, comment="销售费用")  # 销售费用
    administrative_expenses = Column(Float, comment="管理费用")  # 管理费用
    research_and_development_expenses = Column(Float, comment="研发费用")  # 研发费用
    financial_expenses = Column(Float, comment="财务费用")  # 财务费用
    interest_expense = Column(Float, comment="其中：利息费用")  # 其中：利息费用
    interest_income = Column(Float, comment="利息收入")  # 利息收入

    # 其他收益与损益
    other_income = Column(Float, comment="加：其他收益")  # 加：其他收益
    investment_income = Column(Float, comment="投资收益（损失以"-"号填列）")  # 投资收益
    investment_income_from_associates = Column(Float, comment="其中：对联营企业和合营企业的投资收益")  # 其中：对联营企业和合营企业的投资收益
    financial_asset_derecognition_income = Column(Float, comment="以摊余成本计量的金融资产终止确认收益")  # 以摊余成本计量的金融资产终止确认收益
    net_hedge_gain = Column(Float, comment="净敞口套期收益（损失以"-"号填列）")  # 净敞口套期收益
    fair_value_change_income = Column(Float, comment="公允价值变动收益（损失以"-"号填列）")  # 公允价值变动收益
    credit_impairment_loss = Column(Float, comment="信用减值损失（损失以"-"号填列）")  # 信用减值损失
    asset_impairment_loss = Column(Float, comment="资产减值损失（损失以"-"号填列）")  # 资产减值损失
    asset_disposal_income = Column(Float, comment="资产处置收益（损失以"-"号填列）")  # 资产处置收益
    operating_profit = Column(Float, comment="二、营业利润（亏损以"-"号填列）")  # 二、营业利润
    non_operating_income = Column(Float, comment="加：营业外收入")  # 加：营业外收入
    non_operating_expenses = Column(Float, comment="减：营业外支出")  # 减：营业外支出
    total_profit = Column(Float, comment="三、利润总额（亏损总额以"-"号填列）")  # 三、利润总额
    income_tax_expense = Column(Float, comment="减：所得税费用")  # 减：所得税费用
    net_profit = Column(Float, comment="四、净利润（净亏损以"-"号填列）")  # 四、净利润
    continuing_operation_net_profit = Column(Float, comment="（一）持续经营净利润（净亏损以"-"号填列）")  # （一）持续经营净利润
    discontinued_operation_net_profit = Column(Float, comment="（二）终止经营净利润（净亏损以"-"号填列）")  # （二）终止经营净利润

    # 其他综合收益
    other_comprehensive_income_after_tax = Column(Float, comment="五、其他综合收益的税后净额")  # 五、其他综合收益的税后净额
    oci_not_recognized_in_profit = Column(Float, comment="（一）不能重分类进损益的其他综合收益")  # （一）不能重分类进损益的其他综合收益
    defined_benefit_plan_change = Column(Float, comment="1.重新计量设定受益计划变动额")  # 1.重新计量设定受益计划变动额
    equity_method_oci_not_transfer = Column(Float, comment="2.权益法下不能转损益的其他综合收益")  # 2.权益法下不能转损益的其他综合收益
    other_equity_instrument_fv_change = Column(Float, comment="3.其他权益工具投资公允价值变动")  # 3.其他权益工具投资公允价值变动
    entity_credit_risk_fv_change = Column(Float, comment="4.企业自身信用风险公允价值变动")  # 4.企业自身信用风险公允价值变动
    oci_recognized_in_profit = Column(Float, comment="（二）将重分类进损益的其他综合收益")  # （二）将重分类进损益的其他综合收益
    equity_method_oci_transfer = Column(Float, comment="1.权益法下可转损益的其他综合收益")  # 1.权益法下可转损益的其他综合收益
    other_debt_investment_fv_change = Column(Float, comment="2.其他债权投资公允价值变动")  # 2.其他债权投资公允价值变动
    financial_asset_reclassification_oci = Column(Float, comment="3.金融资产重分类计入其他综合收益的金额")  # 3.金融资产重分类计入其他综合收益的金额
    other_debt_investment_impairment = Column(Float, comment="4.其他债权投资信用减值准备")  # 4.其他债权投资信用减值准备
    cash_flow_hedge_reserve = Column(Float, comment="5.现金流量套期储备")  # 5.现金流量套期储备
    foreign_currency_translation = Column(Float, comment="6.外币财务报表折算差额")  # 6.外币财务报表折算差额
    other_oci = Column(Float, comment="7.其他")  # 7.其他
    total_comprehensive_income = Column(Float, comment="六、综合收益总额")  # 六、综合收益总额
    basic_eps = Column(Float, comment="（一）基本每股收益(元/股)")  # （一）基本每股收益
    diluted_eps = Column(Float, comment="（二）稀释每股收益(元/股)")  # （二）稀释每股收益


class ConsolidatedCashFlowStatement(Base):
    """
    合并现金流量表 ORM 模型
    用于存储合并现金流量表的所有财务指标
    """
    __tablename__ = 'consolidated_cash_flow_statement'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)

    # 经营活动产生的现金流量
    cash_from_sales = Column(Float, comment="销售商品、提供劳务收到的现金")  # 销售商品、提供劳务收到的现金
    deposit_from_customers = Column(Float, comment="客户存款和同业存放款项净增加额")  # 客户存款和同业存放款项净增加额
    borrowing_from_central_bank = Column(Float, comment="向中央银行借款净增加额")  # 向中央银行借款净增加额
    borrowing_from_financial_institutions = Column(Float, comment="向其他金融机构拆入资金净增加额")  # 向其他金融机构拆入资金净增加额
    premium_from_insurance = Column(Float, comment="收到原保险合同保费取得的现金")  # 收到原保险合同保费取得的现金
    net_cash_from_reinsurance = Column(Float, comment="收到再保业务现金净额")  # 收到再保业务现金净额
    policyholder_deposits = Column(Float, comment="保户储金及投资款净增加额")  # 保户储金及投资款净增加额
    interest_and_commission_received = Column(Float, comment="收取利息、手续费及佣金的现金")  # 收取利息、手续费及佣金的现金
    borrowed_funds = Column(Float, comment="拆入资金净增加额")  # 拆入资金净增加额
    repurchase_agreement_funds = Column(Float, comment="回购业务资金净增加额")  # 回购业务资金净增加额
    net_cash_from_securities_trading = Column(Float, comment="代理买卖证券收到的现金净额")  # 代理买卖证券收到的现金净额
    tax_refund = Column(Float, comment="收到的税费返还")  # 收到的税费返还
    other_cash_from_operations = Column(Float, comment="收到其他与经营活动有关的现金")  # 收到其他与经营活动有关的现金
    operating_cash_inflows = Column(Float, comment="经营活动现金流入小计")  # 经营活动现金流入小计
    cash_for_goods = Column(Float, comment="购买商品、接受劳务支付的现金")  # 购买商品、接受劳务支付的现金
    loans_to_customers = Column(Float, comment="客户贷款及垫款净增加额")  # 客户贷款及垫款净增加额
    deposits_with_central_bank = Column(Float, comment="存放中央银行和同业款项净增加额")  # 存放中央银行和同业款项净增加额
    cash_for_claims = Column(Float, comment="支付原保险合同赔付款项的现金")  # 支付原保险合同赔付款项的现金
    lending_funds = Column(Float, comment="拆出资金净增加额")  # 拆出资金净增加额
    interest_and_commission_paid = Column(Float, comment="支付利息、手续费及佣金的现金")  # 支付利息、手续费及佣金的现金
    policyholder_dividend_paid = Column(Float, comment="支付保单红利的现金")  # 支付保单红利的现金
    cash_to_employees = Column(Float, comment="支付给职工及为职工支付的现金")  # 支付给职工及为职工支付的现金
    taxes_paid = Column(Float, comment="支付的各项税费")  # 支付的各项税费
    other_cash_for_operations = Column(Float, comment="支付其他与经营活动有关的现金")  # 支付其他与经营活动有关的现金
    operating_cash_outflows = Column(Float, comment="经营活动现金流出小计")  # 经营活动现金流出小计
    net_cash_from_operations = Column(Float, comment="经营活动产生的现金流量净额")  # 经营活动产生的现金流量净额

    # 投资活动产生的现金流量
    cash_from_investment_disposal = Column(Float, comment="收回投资收到的现金")  # 收回投资收到的现金
    investment_income_received = Column(Float, comment="取得投资收益收到的现金")  # 取得投资收益收到的现金
    cash_from_fixed_asset_disposal = Column(Float, comment="处置固定资产、无形资产和其他长期资产收回的现金净额")  # 处置固定资产、无形资产和其他长期资产收回的现金净额
    cash_from_subsidiary_disposal = Column(Float, comment="处置子公司及其他营业单位收到的现金净额")  # 处置子公司及其他营业单位收到的现金净额
    other_cash_from_investing = Column(Float, comment="收到其他与投资活动有关的现金")  # 收到其他与投资活动有关的现金
    investing_cash_inflows = Column(Float, comment="投资活动现金流入小计")  # 投资活动现金流入小计
    cash_for_fixed_assets = Column(Float, comment="购建固定资产、无形资产和其他长期资产支付的现金")  # 购建固定资产、无形资产和其他长期资产支付的现金
    cash_for_investments = Column(Float, comment="投资支付的现金")  # 投资支付的现金
    pledged_loans = Column(Float, comment="质押贷款净增加额")  # 质押贷款净增加额
    cash_for_subsidiary_acquisition = Column(Float, comment="取得子公司及其他营业单位支付的现金净额")  # 取得子公司及其他营业单位支付的现金净额
    other_cash_for_investing = Column(Float, comment="支付其他与投资活动有关的现金")  # 支付其他与投资活动有关的现金
    investing_cash_outflows = Column(Float, comment="投资活动现金流出小计")  # 投资活动现金流出小计
    net_cash_from_investing = Column(Float, comment="投资活动产生的现金流量净额")  # 投资活动产生的现金流量净额

    # 筹资活动产生的现金流量
    cash_from_capital_contribution = Column(Float, comment="吸收投资收到的现金")  # 吸收投资收到的现金
    capital_contribution_from_minority = Column(Float, comment="其中：子公司吸收少数股东投资收到的现金")  # 其中：子公司吸收少数股东投资收到的现金
    cash_from_borrowing = Column(Float, comment="取得借款收到的现金")  # 取得借款收到的现金
    other_cash_from_financing = Column(Float, comment="收到其他与筹资活动有关的现金")  # 收到其他与筹资活动有关的现金
    financing_cash_inflows = Column(Float, comment="筹资活动现金流入小计")  # 筹资活动现金流入小计
    cash_for_debt_repayment = Column(Float, comment="偿还债务支付的现金")  # 偿还债务支付的现金
    cash_for_dividend_and_interest = Column(Float, comment="分配股利、利润或偿付利息支付的现金")  # 分配股利、利润或偿付利息支付的现金
    dividend_to_minority = Column(Float, comment="其中：子公司支付给少数股东的股利、利润")  # 其中：子公司支付给少数股东的股利、利润
    other_cash_for_financing = Column(Float, comment="支付其他与筹资活动有关的现金")  # 支付其他与筹资活动有关的现金
    financing_cash_outflows = Column(Float, comment="筹资活动现金流出小计")  # 筹资活动现金流出小计
    net_cash_from_financing = Column(Float, comment="筹资活动产生的现金流量净额")  # 筹资活动产生的现金流量净额

    # 现金及现金等价物
    exchange_rate_effect = Column(Float, comment="四、汇率变动对现金及现金等价物的影响")  # 四、汇率变动对现金及现金等价物的影响
    net_increase_in_cash = Column(Float, comment="五、现金及现金等价物净增加额")  # 五、现金及现金等价物净增加额
    beginning_cash = Column(Float, comment="加：期初现金及现金等价物余额")  # 加：期初现金及现金等价物余额
    ending_cash = Column(Float, comment="六、期末现金及现金等价物余额")  # 六、期末现金及现金等价物余额


class ParentCompanyCashFlowStatement(Base):
    """
    母公司现金流量表 ORM 模型
    用于存储母公司现金流量表的所有财务指标
    """
    __tablename__ = 'parent_company_cash_flow_statement'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)

    # 经营活动产生的现金流量
    cash_from_sales = Column(Float, comment="销售商品、提供劳务收到的现金")  # 销售商品、提供劳务收到的现金
    tax_refund = Column(Float, comment="收到的税费返还")  # 收到的税费返还
    other_cash_from_operations = Column(Float, comment="收到其他与经营活动有关的现金")  # 收到其他与经营活动有关的现金
    operating_cash_inflows = Column(Float, comment="经营活动现金流入小计")  # 经营活动现金流入小计
    cash_for_goods = Column(Float, comment="购买商品、接受劳务支付的现金")  # 购买商品、接受劳务支付的现金
    cash_to_employees = Column(Float, comment="支付给职工及为职工支付的现金")  # 支付给职工及为职工支付的现金
    taxes_paid = Column(Float, comment="支付的各项税费")  # 支付的各项税费
    other_cash_for_operations = Column(Float, comment="支付其他与经营活动有关的现金")  # 支付其他与经营活动有关的现金
    operating_cash_outflows = Column(Float, comment="经营活动现金流出小计")  # 经营活动现金流出小计
    net_cash_from_operations = Column(Float, comment="经营活动产生的现金流量净额")  # 经营活动产生的现金流量净额

    # 投资活动产生的现金流量
    cash_from_investment_disposal = Column(Float, comment="收回投资收到的现金")  # 收回投资收到的现金
    investment_income_received = Column(Float, comment="取得投资收益收到的现金")  # 取得投资收益收到的现金
    cash_from_fixed_asset_disposal = Column(Float, comment="处置固定资产、无形资产和其他长期资产收回的现金净额")  # 处置固定资产、无形资产和其他长期资产收回的现金净额
    cash_from_subsidiary_disposal = Column(Float, comment="处置子公司及其他营业单位收到的现金净额")  # 处置子公司及其他营业单位收到的现金净额
    other_cash_from_investing = Column(Float, comment="收到其他与投资活动有关的现金")  # 收到其他与投资活动有关的现金
    investing_cash_inflows = Column(Float, comment="投资活动现金流入小计")  # 投资活动现金流入小计
    cash_for_fixed_assets = Column(Float, comment="购建固定资产、无形资产和其他长期资产支付的现金")  # 购建固定资产、无形资产和其他长期资产支付的现金
    cash_for_investments = Column(Float, comment="投资支付的现金")  # 投资支付的现金
    cash_for_subsidiary_acquisition = Column(Float, comment="取得子公司及其他营业单位支付的现金净额")  # 取得子公司及其他营业单位支付的现金净额
    other_cash_for_investing = Column(Float, comment="支付其他与投资活动有关的现金")  # 支付其他与投资活动有关的现金
    investing_cash_outflows = Column(Float, comment="投资活动现金流出小计")  # 投资活动现金流出小计
    net_cash_from_investing = Column(Float, comment="投资活动产生的现金流量净额")  # 投资活动产生的现金流量净额

    # 筹资活动产生的现金流量
    cash_from_capital_contribution = Column(Float, comment="吸收投资收到的现金")  # 吸收投资收到的现金
    cash_from_borrowing = Column(Float, comment="取得借款收到的现金")  # 取得借款收到的现金
    other_cash_from_financing = Column(Float, comment="收到其他与筹资活动有关的现金")  # 收到其他与筹资活动有关的现金
    financing_cash_inflows = Column(Float, comment="筹资活动现金流入小计")  # 筹资活动现金流入小计
    cash_for_debt_repayment = Column(Float, comment="偿还债务支付的现金")  # 偿还债务支付的现金
    cash_for_dividend_and_interest = Column(Float, comment="分配股利、利润或偿付利息支付的现金")  # 分配股利、利润或偿付利息支付的现金
    other_cash_for_financing = Column(Float, comment="支付其他与筹资活动有关的现金")  # 支付其他与筹资活动有关的现金
    financing_cash_outflows = Column(Float, comment="筹资活动现金流出小计")  # 筹资活动现金流出小计
    net_cash_from_financing = Column(Float, comment="筹资活动产生的现金流量净额")  # 筹资活动产生的现金流量净额

    # 现金及现金等价物
    exchange_rate_effect = Column(Float, comment="四、汇率变动对现金及现金等价物的影响")  # 四、汇率变动对现金及现金等价物的影响
    net_increase_in_cash = Column(Float, comment="五、现金及现金等价物净增加额")  # 五、现金及现金等价物净增加额
    beginning_cash = Column(Float, comment="加：期初现金及现金等价物余额")  # 加：期初现金及现金等价物余额
    ending_cash = Column(Float, comment="六、期末现金及现金等价物余额")  # 六、期末现金及现金等价物余额 


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
