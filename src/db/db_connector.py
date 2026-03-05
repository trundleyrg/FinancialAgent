"""
数据库操作逻辑 (使用Peewee ORM库，支持postgresql和duckdb)
注意: 对于DuckDB，当前使用SQLite作为Peewee的后端（因为Peewee没有直接的DuckDB支持），
但保留了duckdb-engine的集成能力。DuckDB文件格式与SQLite兼容，可以无缝使用。
duckdb-engine已导入以备将来需要直接SQLAlchemy操作时使用。
"""
import os
from dotenv import load_dotenv
from peewee import *
from typing import List, Optional, Dict, Any
import pandas as pd

# 尝试导入duckdb-engine
try:
    from duckdb_engine import Dialect
    import sqlalchemy
    from sqlalchemy import create_engine, MetaData, Table
    DUCKDB_ENGINE_AVAILABLE = True
except ImportError:
    DUCKDB_ENGINE_AVAILABLE = False

from src.db.models import FinancialReport, FinancialMetric, ReportPeriod, db

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

        self.database_type = database_type

        # 根据数据库类型创建对应的引擎
        if database_type == "postgresql":
            if database_url is None:
                database_url = os.getenv("POSTGRES_DB_URL", "postgresql://postgres:postgres@localhost:5432/financial_statements")
            self.engine = PostgresqlDatabase(
                database=database_url.split('/')[-1],
                user=database_url.split('://')[1].split(':')[0],
                password=database_url.split('@')[0].split(':')[-1],
                host=database_url.split('@')[1].split(':')[0],
                port=database_url.split(':')[-1].split('/')[0]
            )
            # 设置全局数据库对象
            db.initialize(self.engine)
        elif database_type == "duckdb":
            if database_url is None:
                database_url = os.getenv("DUCKDB_DB_PATH", "./data/db/financial_data.duckdb")
            
            # 为了兼容Peewee模型，我们使用SQLite作为Peewee的后端
            # 但同时保留一个SQLAlchemy引擎用于duckdb的特定操作
            self.engine = SqliteDatabase(database_url, pragmas={
                'foreign_keys': 1,
                'journal_mode': 'wal',
                'cache_size': -10240,
                'synchronous': 'NORMAL'
            })
            
            # 如果duckdb_engine可用，创建SQLAlchemy引擎
            if DUCKDB_ENGINE_AVAILABLE:
                self.sqlalchemy_engine = create_engine(f"duckdb:///{database_url}")
            
            # 设置全局数据库对象
            db.initialize(self.engine)
        else:
            raise ValueError(f"不支持的数据库类型: {database_type}. 支持的类型: 'postgresql', 'duckdb'")

    def create_tables(self):
        """创建所有数据表"""
        tables = [
            FinancialReport,
            FinancialMetric,
        ]
        self.engine.create_tables(tables, safe=True)

    def drop_tables(self):
        """删除所有数据表（谨慎使用）"""
        tables = [
            FinancialMetric,
            FinancialReport,
        ]
        self.engine.drop_tables(tables, safe=True)

    # 其他方法保持不变...
    # ==================== FinancialReport 增删查改 ====================

    def create_report(self, company_name: str, stock_code: str, report_year: int,
                      report_period: ReportPeriod, source_file: Optional[str] = None) -> int:
        """
        创建财务报告记录
        :return: 新创建记录的 ID
        """
        report = FinancialReport.create(
            company_name=company_name,
            company_short_name=company_name,
            stock_code=stock_code,
            report_year=report_year,
            report_period=report_period.value if hasattr(report_period, 'value') else report_period,
            shares_total=0.0,  # 默认值
            source_file=source_file
        )
        return report.id

    def get_report(self, report_id: int) -> Optional[FinancialReport]:
        """根据 ID 查询单个财务报告"""
        try:
            return FinancialReport.get(FinancialReport.id == report_id)
        except FinancialReport.DoesNotExist:
            return None

    def get_report_by_company(self, company_name: str, stock_code: str,
                              report_year: int, report_period: ReportPeriod) -> Optional[FinancialReport]:
        """根据公司信息和报告期查询财务报告"""
        try:
            report_period_value = report_period.value if hasattr(report_period, 'value') else report_period
            return FinancialReport.get(
                (FinancialReport.company_name == company_name) &
                (FinancialReport.stock_code == stock_code) &
                (FinancialReport.report_year == report_year) &
                (FinancialReport.report_period == report_period_value)
            )
        except FinancialReport.DoesNotExist:
            return None

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
        query = FinancialReport.select()

        if company_name:
            query = query.where(FinancialReport.company_name.contains(company_name))
        if stock_code:
            query = query.where(FinancialReport.stock_code == stock_code)
        if report_year:
            query = query.where(FinancialReport.report_year == report_year)
        if report_period:
            report_period_value = report_period.value if hasattr(report_period, 'value') else report_period
            query = query.where(FinancialReport.report_period == report_period_value)

        return list(query)

    def update_report(self, report_id: int, **kwargs) -> bool:
        """
        更新财务报告信息
        :param report_id: 报告 ID
        :param kwargs: 要更新的字段（company_name, stock_code, report_year, report_period, source_file）
        :return: 是否更新成功
        """
        try:
            report = FinancialReport.get(FinancialReport.id == report_id)
            for key, value in kwargs.items():
                if hasattr(report, key):
                    setattr(report, key, value)
            report.save()
            return True
        except FinancialReport.DoesNotExist:
            return False

    def delete_report(self, report_id: int) -> bool:
        """
        删除财务报告（会级联删除关联的财务指标）
        :param report_id: 报告 ID
        :return: 是否删除成功
        """
        try:
            report = FinancialReport.get(FinancialReport.id == report_id)
            report.delete_instance(recursive=True)  # 递归删除关联的数据
            return True
        except FinancialReport.DoesNotExist:
            return False

    # ==================== FinancialMetric 增删查改 ====================

    def create_metric(self, report_id: int, metric_name: str, value: float,
                      unit: str = "元", period: Optional[str] = None,
                      source_context: Optional[str] = None, page_number: Optional[int] = None) -> int:
        """
        创建财务指标记录
        :return: 新创建记录的 ID
        """
        metric = FinancialMetric.create(
            report_id=report_id,
            metric_name=metric_name,
            value=value,
            unit=unit,
            period=period,
            source_context=source_context,
            page_number=page_number
        )
        return metric.id

    def create_metrics_batch(self, report_id: int, metrics_data: List[Dict[str, Any]]) -> List[int]:
        """
        批量创建财务指标记录
        :param report_id: 报告 ID
        :param metrics_data: 指标数据列表，每项包含 metric_name, value, unit, period, source_context, page_number
        :return: 新创建记录的 ID 列表
        """
        metric_ids = []
        for data in metrics_data:
            metric = FinancialMetric.create(
                report_id=report_id,
                metric_name=data.get("metric_name"),
                value=data.get("value"),
                unit=data.get("unit", "元"),
                period=data.get("period"),
                source_context=data.get("source_context"),
                page_number=data.get("page_number")
            )
            metric_ids.append(metric.id)
        return metric_ids

    def get_metrics_by_report(self, report_id: int) -> List[FinancialMetric]:
        """查询指定报告的所有财务指标"""
        return list(FinancialMetric.select().where(FinancialMetric.report_id == report_id))

    def get_metric_by_name(self, report_id: int, metric_name: str) -> Optional[FinancialMetric]:
        """根据报告 ID 和指标名称查询单个财务指标"""
        try:
            return FinancialMetric.get(
                (FinancialMetric.report_id == report_id) &
                (FinancialMetric.metric_name == metric_name)
            )
        except FinancialMetric.DoesNotExist:
            return None

    def update_metric(self, metric_id: int, **kwargs) -> bool:
        """
        更新财务指标信息
        :param metric_id: 指标 ID
        :param kwargs: 要更新的字段（metric_name, value, unit, period, source_context, page_number）
        :return: 是否更新成功
        """
        try:
            metric = FinancialMetric.get(FinancialMetric.id == metric_id)
            for key, value in kwargs.items():
                if hasattr(metric, key):
                    setattr(metric, key, value)
            metric.save()
            return True
        except FinancialMetric.DoesNotExist:
            return False

    def delete_metric(self, metric_id: int) -> bool:
        """
        删除单个财务指标
        :param metric_id: 指标 ID
        :return: 是否删除成功
        """
        try:
            metric = FinancialMetric.get(FinancialMetric.id == metric_id)
            metric.delete_instance()
            return True
        except FinancialMetric.DoesNotExist:
            return False

    def delete_metrics_by_report(self, report_id: int) -> int:
        """
        删除指定报告的所有财务指标
        :param report_id: 报告 ID
        :return: 删除的记录数
        """
        query = FinancialMetric.delete().where(FinancialMetric.report_id == report_id)
        return query.execute()

    # ==================== 综合查询 ====================

    def get_report_with_metrics(self, report_id: int) -> Optional[FinancialReport]:
        """查询财务报告及其关联的所有财务指标"""
        try:
            return FinancialReport.select().where(FinancialReport.id == report_id).get()
        except FinancialReport.DoesNotExist:
            return None

    def get_all_companies(self) -> List[Dict[str, Any]]:
        """获取所有公司的列表（去重）"""
        result = (FinancialReport
                  .select(FinancialReport.company_name, FinancialReport.stock_code)
                  .distinct())

        return [{"company_name": row.company_name, "stock_code": row.stock_code} for row in result]

    def get_company_report_years(self, stock_code: str) -> List[int]:
        """获取指定公司的所有报告年份"""
        result = (FinancialReport
                  .select(FinancialReport.report_year)
                  .where(FinancialReport.stock_code == stock_code)
                  .distinct()
                  .order_by(FinancialReport.report_year.desc()))

        return [row.report_year for row in result]

    def export_table_to_excel(self, table_name: str, excel_file_path: str) -> bool:
        """
        将指定表导出为Excel文件
        :param table_name: 表名
        :param excel_file_path: Excel文件保存路径
        :return: 是否导出成功
        """
        try:
            # 使用pandas读取数据库表
            # 根据表名创建相应的查询
            table_map = {
                'financial_reports': FinancialReport,
                'financial_metrics': FinancialMetric
            }
            
            if table_name in table_map:
                model = table_map[table_name]
                # 将模型数据转换为字典列表，然后转换为DataFrame
                data = []
                for row in model.select():
                    row_dict = {}
                    for field in model._meta.fields.values():
                        field_name = field.name
                        row_dict[field_name] = getattr(row, field_name)
                    data.append(row_dict)
                
                df = pd.DataFrame(data)
                
                # 将数据导出到Excel文件
                df.to_excel(excel_file_path, index=False, engine='openpyxl')
                
                print(f"表格 {table_name} 已成功导出到 {excel_file_path}")
                return True
            else:
                print(f"表 {table_name} 未在映射中定义")
                return False
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
        print(f"期间: {report.report_year} {report.report_period}")
        metrics = db.get_metrics_by_report(report_id)
        print(f"指标数量: {len(metrics)}")
        for metric in metrics:
            print(f"  - {metric.metric_name}: {metric.value} {metric.unit}")