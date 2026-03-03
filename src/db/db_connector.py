"""
数据库操作逻辑 (使用SQLAlchemy库，支持postgresql和duckdb)
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import pandas as pd

from src.db.models import Base, FinancialReport, FinancialMetric, ReportPeriod

# 加载环境变量
load_dotenv()


class DatabaseConnector:
    """数据库连接器，提供增删查改操作，支持 PostgreSQL 和 DuckDB"""

    def __init__(self, database_type: str = None, database_url: str = None):
        """
        初始化数据库连接
        :param database_type: 数据库类型 ('postgresql' 或 'duckdb')，如果为 None，则从环境变量读取
        :param database_url: 数据库连接字符串，如果为 None，则根据数据库类型使用默认值
        """
        if database_type is None:
            database_type = os.getenv("DATABASE", "duckdb").lower()
        
        if database_url is None:
            if database_type == "postgresql":
                database_url = os.getenv("POSTGRES_DB_URL", "postgresql://postgres:postgres@localhost:5432/financial_statements")
            elif database_type == "duckdb":
                database_url = os.getenv("DUCKDB_DB_PATH", "./data/db/financial_data.duckdb")
                database_url = f"duckdb:///{database_url}"
            else:
                raise ValueError(f"不支持的数据库类型: {database_type}. 支持的类型: 'postgresql', 'duckdb'")
        
        self.database_type = database_type
        if database_type == "duckdb":
            # 为DuckDB配置特殊的参数
            from duckdb_engine import Dialect
            # DuckDB不支持SERIAL类型，需要特殊处理
            self.engine = create_engine(database_url, echo=False)
        else:
            self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self):
        """创建所有数据表"""
        if self.database_type == "duckdb":
            # DuckDB不支持SERIAL类型，需要手动创建表结构
            from sqlalchemy import text
            with self.get_session() as session:
                # 创建枚举类型
                try:
                    session.execute(text("CREATE TYPE reportperiod AS ENUM ('Q1', 'H1', 'Q3', 'FY');"))
                except:
                    # 如果类型已存在则跳过
                    session.rollback()
                
                # 手动创建表（不依赖SQLAlchemy的autoincrement）
                tables_sql = [
                    """CREATE TABLE IF NOT EXISTS financial_reports (
                        id INTEGER PRIMARY KEY,
                        company_name VARCHAR(255) NOT NULL,
                        stock_code VARCHAR(20) NOT NULL,
                        report_year INTEGER NOT NULL,
                        report_period reportperiod NOT NULL,
                        shares_total FLOAT NOT NULL,
                        source_file VARCHAR(500),
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );""",
                    """CREATE TABLE IF NOT EXISTS financial_metrics (
                        id INTEGER PRIMARY KEY,
                        report_id INTEGER,
                        metric_name VARCHAR(100) NOT NULL,
                        value FLOAT NOT NULL,
                        unit VARCHAR(20),
                        period VARCHAR(50),
                        source_context TEXT,
                        page_number INTEGER,
                        FOREIGN KEY (report_id) REFERENCES financial_reports(id)
                    );""",
                    """CREATE TABLE IF NOT EXISTS consolidated_balance_sheet (
                        id INTEGER PRIMARY KEY,
                        company_name VARCHAR(255) NOT NULL,
                        stock_code VARCHAR(20) NOT NULL,
                        report_year INTEGER NOT NULL,
                        report_period reportperiod NOT NULL,
                        monetary_funds FLOAT COMMENT '货币资金',
                        reserve_for_settlement FLOAT COMMENT '结算备付金',
                        funds_lent_out FLOAT COMMENT '拆出资金',
                        trading_financial_assets FLOAT COMMENT '交易性金融资产',
                        derivative_financial_assets FLOAT COMMENT '衍生金融资产',
                        notes_receivable FLOAT COMMENT '应收票据',
                        accounts_receivable FLOAT COMMENT '应收账款',
                        financing_receivables FLOAT COMMENT '应收款项融资',
                        prepayments FLOAT COMMENT '预付款项',
                        premiums_receivable FLOAT COMMENT '应收保费',
                        reinsurance_receivables FLOAT COMMENT '应收分保账款',
                        reinsurance_contract_reserves_receivable FLOAT COMMENT '应收分保合同准备金',
                        other_receivables FLOAT COMMENT '其他应收款',
                        interest_receivable FLOAT COMMENT '其中：应收利息',
                        dividend_receivable FLOAT COMMENT '应收股利',
                        buy_back_securities_financial_assets FLOAT COMMENT '买入返售金融资产',
                        inventory FLOAT COMMENT '存货',
                        data_resources_inventory FLOAT COMMENT '其中：数据资源',
                        contract_assets FLOAT COMMENT '合同资产',
                        assets_held_for_sale FLOAT COMMENT '持有待售资产',
                        non_current_assets_due_within_one_year FLOAT COMMENT '一年内到期的非流动资产',
                        other_current_assets FLOAT COMMENT '其他流动资产',
                        total_current_assets FLOAT COMMENT '流动资产合计',
                        loans_and_advances_granted FLOAT COMMENT '发放贷款和垫款',
                        debt_investments FLOAT COMMENT '债权投资',
                        other_debt_investments FLOAT COMMENT '其他债权投资',
                        long_term_receivables FLOAT COMMENT '长期应收款',
                        long_term_equity_investments FLOAT COMMENT '长期股权投资',
                        other_equity_instrument_investments FLOAT COMMENT '其他权益工具投资',
                        other_non_current_financial_assets FLOAT COMMENT '其他非流动金融资产',
                        investment_real_estate FLOAT COMMENT '投资性房地产',
                        fixed_assets FLOAT COMMENT '固定资产',
                        construction_in_progress FLOAT COMMENT '在建工程',
                        productive_biological_assets FLOAT COMMENT '生产性生物资产',
                        oil_and_gas_assets FLOAT COMMENT '油气资产',
                        right_of_use_assets FLOAT COMMENT '使用权资产',
                        intangible_assets FLOAT COMMENT '无形资产',
                        data_resources_intangible FLOAT COMMENT '其中：数据资源',
                        development_expenditure FLOAT COMMENT '开发支出',
                        data_resources_development FLOAT COMMENT '其中：数据资源',
                        goodwill FLOAT COMMENT '商誉',
                        long_term_prepaid_expenses FLOAT COMMENT '长期待摊费用',
                        deferred_tax_assets FLOAT COMMENT '递延所得税资产',
                        other_non_current_assets FLOAT COMMENT '其他非流动资产',
                        total_non_current_assets FLOAT COMMENT '非流动资产合计',
                        total_assets FLOAT COMMENT '资产总计',
                        short_term_borrowings FLOAT COMMENT '短期借款',
                        borrowings_from_central_bank FLOAT COMMENT '向中央银行借款',
                        funds_borrowed FLOAT COMMENT '拆入资金',
                        trading_financial_liabilities FLOAT COMMENT '交易性金融负债',
                        derivative_financial_liabilities FLOAT COMMENT '衍生金融负债',
                        notes_payable FLOAT COMMENT '应付票据',
                        accounts_payable FLOAT COMMENT '应付账款',
                        advance_from_customers FLOAT COMMENT '预收款项',
                        contract_liabilities FLOAT COMMENT '合同负债',
                        sell_repurchase_securities_funds FLOAT COMMENT '卖出回购金融资产款',
                        deposits_and_interbank_placement FLOAT COMMENT '吸收存款及同业存放',
                        proxy_trading_securities_funds FLOAT COMMENT '代理买卖证券款',
                        proxy_underwriting_securities_funds FLOAT COMMENT '代理承销证券款',
                        employee_benefits_payable FLOAT COMMENT '应付职工薪酬',
                        taxes_payable FLOAT COMMENT '应交税费',
                        other_payables FLOAT COMMENT '其他应付款',
                        interest_payable FLOAT COMMENT '其中：应付利息',
                        dividend_payable FLOAT COMMENT '应付股利',
                        commission_and_brokerage_payable FLOAT COMMENT '应付手续费及佣金',
                        reinsurance_payables FLOAT COMMENT '应付分保账款',
                        liabilities_held_for_sale FLOAT COMMENT '持有待售负债',
                        non_current_liabilities_due_within_one_year FLOAT COMMENT '一年内到期的非流动负债',
                        other_current_liabilities FLOAT COMMENT '其他流动负债',
                        total_current_liabilities FLOAT COMMENT '流动负债合计',
                        insurance_contract_reserves FLOAT COMMENT '保险合同准备金',
                        long_term_borrowings FLOAT COMMENT '长期借款',
                        bonds_payable FLOAT COMMENT '应付债券',
                        preferred_stock_bonds FLOAT COMMENT '其中：优先股',
                        perpetual_bonds FLOAT COMMENT '永续债',
                        lease_liabilities FLOAT COMMENT '租赁负债',
                        long_term_payables FLOAT COMMENT '长期应付款',
                        long_term_employee_benefits_payable FLOAT COMMENT '长期应付职工薪酬',
                        estimated_liabilities FLOAT COMMENT '预计负债',
                        deferred_income FLOAT COMMENT '递延收益',
                        deferred_tax_liabilities FLOAT COMMENT '递延所得税负债',
                        other_non_current_liabilities FLOAT COMMENT '其他非流动负债',
                        total_non_current_liabilities FLOAT COMMENT '非流动负债合计',
                        total_liabilities FLOAT COMMENT '负债合计',
                        paid_in_capital FLOAT COMMENT '实收资本',
                        other_equity_instruments FLOAT COMMENT '其他权益工具',
                        preferred_stock_equity FLOAT COMMENT '其中：优先股（权益）',
                        perpetual_bonds_equity FLOAT COMMENT '永续债（权益）',
                        capital_reserve FLOAT COMMENT '资本公积',
                        treasury_stock FLOAT COMMENT '减：库存股',
                        other_comprehensive_income FLOAT COMMENT '其他综合收益',
                        special_reserve FLOAT COMMENT '专项储备',
                        surplus_reserve FLOAT COMMENT '盈余公积',
                        general_risk_reserve FLOAT COMMENT '一般风险准备',
                        retained_earnings FLOAT COMMENT '未分配利润',
                        total_equity_attributable_to_parent_company FLOAT COMMENT '归属于母公司所有者权益',
                        minority_interest FLOAT COMMENT '少数股东权益',
                        total_owners_equity FLOAT COMMENT '所有者权益',
                        total_liabilities_and_owners_equity FLOAT COMMENT '负债和所有者权益'
                    );""",
                    # 这里可以继续添加其他表的创建语句...
                ]
                
                for sql in tables_sql:
                    try:
                        session.execute(text(sql))
                    except Exception as e:
                        print(f"创建表时出错: {e}")
                        session.rollback()
                
                session.commit()
        else:
            Base.metadata.create_all(self.engine)

    def drop_tables(self):
        """删除所有数据表（谨慎使用）"""
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def get_session(self):
        """获取数据库会话（上下文管理器）"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== FinancialReport 增删查改 ====================

    def create_report(self, company_name: str, stock_code: str, report_year: int,
                      report_period: ReportPeriod, source_file: Optional[str] = None) -> int:
        """
        创建财务报告记录
        :return: 新创建记录的 ID
        """
        with self.get_session() as session:
            report = FinancialReport(
                company_name=company_name,
                stock_code=stock_code,
                report_year=report_year,
                report_period=report_period,
                source_file=source_file
            )
            session.add(report)
            session.flush()
            return report.id

    def get_report(self, report_id: int) -> Optional[FinancialReport]:
        """根据 ID 查询单个财务报告"""
        with self.get_session() as session:
            return session.query(FinancialReport).filter(FinancialReport.id == report_id).first()

    def get_report_by_company(self, company_name: str, stock_code: str,
                              report_year: int, report_period: ReportPeriod) -> Optional[FinancialReport]:
        """根据公司信息和报告期查询财务报告"""
        with self.get_session() as session:
            return session.query(FinancialReport).filter(
                FinancialReport.company_name == company_name,
                FinancialReport.stock_code == stock_code,
                FinancialReport.report_year == report_year,
                FinancialReport.report_period == report_period
            ).first()

    def list_reports(self, company_name: Optional[str] = None,
                     stock_code: Optional[str] = None,
                     report_year: Optional[int] = None,
                     report_period: Optional[ReportPeriod] = None) -> List[FinancialReport]:
        """
        查询财务报告列表（支持条件过滤）
        :param company_name: 公司名称（模糊匹配）
        :param stock_code: 股票代码（精确匹配）
        :param report_year: 报告年份
        :param report_period: 报告周期
        :return: 财务报告列表
        """
        with self.get_session() as session:
            query = session.query(FinancialReport)

            if company_name:
                if self.database_type == "postgresql":
                    # PostgreSQL 使用 ilike 进行不区分大小写的匹配
                    query = query.filter(FinancialReport.company_name.ilike(f"%{company_name}%"))
                else:
                    # DuckDB 使用 LIKE 和 UPPER 进行不区分大小写的匹配
                    query = query.filter(FinancialReport.company_name.like(f"%{company_name.lower()}%"))
            if stock_code:
                query = query.filter(FinancialReport.stock_code == stock_code)
            if report_year:
                query = query.filter(FinancialReport.report_year == report_year)
            if report_period:
                query = query.filter(FinancialReport.report_period == report_period)

            return query.all()

    def update_report(self, report_id: int, **kwargs) -> bool:
        """
        更新财务报告信息
        :param report_id: 报告 ID
        :param kwargs: 要更新的字段（company_name, stock_code, report_year, report_period, source_file）
        :return: 是否更新成功
        """
        with self.get_session() as session:
            report = session.query(FinancialReport).filter(FinancialReport.id == report_id).first()
            if not report:
                return False

            for key, value in kwargs.items():
                if hasattr(report, key):
                    setattr(report, key, value)
            return True

    def delete_report(self, report_id: int) -> bool:
        """
        删除财务报告（会级联删除关联的财务指标）
        :param report_id: 报告 ID
        :return: 是否删除成功
        """
        with self.get_session() as session:
            report = session.query(FinancialReport).filter(FinancialReport.id == report_id).first()
            if not report:
                return False
            session.delete(report)
            return True

    # ==================== FinancialMetric 增删查改 ====================

    def create_metric(self, report_id: int, metric_name: str, value: float,
                      unit: str = "元", period: Optional[str] = None,
                      source_context: Optional[str] = None, page_number: Optional[int] = None) -> int:
        """
        创建财务指标记录
        :return: 新创建记录的 ID
        """
        with self.get_session() as session:
            metric = FinancialMetric(
                report_id=report_id,
                metric_name=metric_name,
                value=value,
                unit=unit,
                period=period,
                source_context=source_context,
                page_number=page_number
            )
            session.add(metric)
            session.flush()
            return metric.id

    def create_metrics_batch(self, report_id: int, metrics_data: List[Dict[str, Any]]) -> List[int]:
        """
        批量创建财务指标记录
        :param report_id: 报告 ID
        :param metrics_data: 指标数据列表，每项包含 metric_name, value, unit, period, source_context, page_number
        :return: 新创建记录的 ID 列表
        """
        with self.get_session() as session:
            metrics = []
            for data in metrics_data:
                metric = FinancialMetric(
                    report_id=report_id,
                    metric_name=data.get("metric_name"),
                    value=data.get("value"),
                    unit=data.get("unit", "元"),
                    period=data.get("period"),
                    source_context=data.get("source_context"),
                    page_number=data.get("page_number")
                )
                metrics.append(metric)

            session.add_all(metrics)
            session.flush()
            return [m.id for m in metrics]

    def get_metrics_by_report(self, report_id: int) -> List[FinancialMetric]:
        """查询指定报告的所有财务指标"""
        with self.get_session() as session:
            return session.query(FinancialMetric).filter(
                FinancialMetric.report_id == report_id
            ).all()

    def get_metric_by_name(self, report_id: int, metric_name: str) -> Optional[FinancialMetric]:
        """根据报告 ID 和指标名称查询单个财务指标"""
        with self.get_session() as session:
            return session.query(FinancialMetric).filter(
                FinancialMetric.report_id == report_id,
                FinancialMetric.metric_name == metric_name
            ).first()

    def update_metric(self, metric_id: int, **kwargs) -> bool:
        """
        更新财务指标信息
        :param metric_id: 指标 ID
        :param kwargs: 要更新的字段（metric_name, value, unit, period, source_context, page_number）
        :return: 是否更新成功
        """
        with self.get_session() as session:
            metric = session.query(FinancialMetric).filter(FinancialMetric.id == metric_id).first()
            if not metric:
                return False

            for key, value in kwargs.items():
                if hasattr(metric, key):
                    setattr(metric, key, value)
            return True

    def delete_metric(self, metric_id: int) -> bool:
        """
        删除单个财务指标
        :param metric_id: 指标 ID
        :return: 是否删除成功
        """
        with self.get_session() as session:
            metric = session.query(FinancialMetric).filter(FinancialMetric.id == metric_id).first()
            if not metric:
                return False
            session.delete(metric)
            return True

    def delete_metrics_by_report(self, report_id: int) -> int:
        """
        删除指定报告的所有财务指标
        :param report_id: 报告 ID
        :return: 删除的记录数
        """
        with self.get_session() as session:
            count = session.query(FinancialMetric).filter(
                FinancialMetric.report_id == report_id
            ).delete()
            return count

    # ==================== 综合查询 ====================

    def get_report_with_metrics(self, report_id: int) -> Optional[FinancialReport]:
        """查询财务报告及其关联的所有财务指标"""
        with self.get_session() as session:
            return session.query(FinancialReport).filter(
                FinancialReport.id == report_id
            ).first()

    def get_all_companies(self) -> List[Dict[str, Any]]:
        """获取所有公司的列表（去重）"""
        with self.get_session() as session:
            result = session.query(
                FinancialReport.company_name,
                FinancialReport.stock_code
            ).distinct().all()

            return [{"company_name": row[0], "stock_code": row[1]} for row in result]

    def get_company_report_years(self, stock_code: str) -> List[int]:
        """获取指定公司的所有报告年份"""
        with self.get_session() as session:
            result = session.query(FinancialReport.report_year).filter(
                FinancialReport.stock_code == stock_code
            ).distinct().order_by(FinancialReport.report_year.desc()).all()

            return [row[0] for row in result]

    def export_table_to_excel(self, table_name: str, excel_file_path: str) -> bool:
        """
        将指定表导出为Excel文件
        :param table_name: 表名
        :param excel_file_path: Excel文件保存路径
        :return: 是否导出成功
        """
        try:
            # 使用pandas读取数据库表
            query = f"SELECT * FROM {table_name}"
            df = pd.read_sql_query(query, self.engine)
            
            # 将数据导出到Excel文件
            df.to_excel(excel_file_path, index=False, engine='openpyxl')
            
            print(f"表格 {table_name} 已成功导出到 {excel_file_path}")
            return True
        except Exception as e:
            print(f"导出表格 {table_name} 时出错: {str(e)}")
            return False


# ============ 全局单例 ============
_db_connector: Optional[DatabaseConnector] = None


def get_db(database_type: str = None, database_url: str = None) -> DatabaseConnector:
    """获取数据库连接器单例"""
    global _db_connector
    if _db_connector is None:
        _db_connector = DatabaseConnector(database_type, database_url)
        _db_connector.create_tables()
    return _db_connector


# ============ 使用示例 ============
if __name__ == "__main__":
    # 创建数据库连接 - 默认使用 DuckDB
    db = get_db()

    # 创建测试数据
    report_id = db.create_report(
        company_name="测试公司",
        stock_code="000001",
        report_year=2024,
        report_period=ReportPeriod.FY,
        source_file="./test.pdf"
    )
    print(f"创建报告 ID: {report_id}")

    # 批量创建指标
    metrics_data = [
        {"metric_name": "营业收入", "value": 1000000000, "unit": "元", "page_number": 10},
        {"metric_name": "净利润", "value": 150000000, "unit": "元", "page_number": 12},
    ]
    metric_ids = db.create_metrics_batch(report_id, metrics_data)
    print(f"创建指标 IDs: {metric_ids}")

    # 查询报告及指标
    report = db.get_report_with_metrics(report_id)
    if report:
        print(f"\n报告: {report.company_name} ({report.stock_code})")
        print(f"期间: {report.report_year} {report.report_period.value}")
        print(f"指标数量: {len(report.metrics)}")
        for metric in report.metrics:
            print(f"  - {metric.metric_name}: {metric.value} {metric.unit}")
